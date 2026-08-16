import asyncio
import time
import pytest
from app.db import db
from app.worker import BackgroundWorker
from app.client import api_client
from app.rate_limiter import api_rate_limiter


@pytest.mark.asyncio
async def test_worker_500_retry_then_succeed(mocker):
    call_count = 0

    async def mock_send(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First attempt: 500 error
            return 500, {"error": "internal_error"}, None
        # Second attempt: 202 Accepted
        return 202, {"dm_id": "dm_500_success", "status": "queued"}, None

    mocker.patch.object(api_client, "send_dm", side_effect=mock_send)
    mocker.patch.object(
        api_client,
        "get_dm_status",
        return_value=(200, {"dm_id": "dm_500_success", "status": "delivered"})
    )

    await db.create_rule(keyword="PRICE", dm_message="Price list")
    await db.process_webhook_event({
        "event_id": "evt_500_retry",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_500",
            "text": "PRICE",
            "from": {"user_id": "usr_500"}
        }
    })

    worker = BackgroundWorker()

    # Step 1: Initial dispatch fails with 500
    jobs = await db.get_queued_jobs()
    assert len(jobs) == 1
    job = jobs[0]

    code, data, _ = await api_client.send_dm(job["user_id"], job["message"], job["comment_id"])
    assert code == 500
    # Simulate backoff update
    await db.update_job(job["job_id"], status="queued", retries=1, next_retry_at=time.time())

    # Step 2: Next retry succeeds with 202
    retry_jobs = await db.get_queued_jobs()
    assert len(retry_jobs) == 1
    code2, data2, _ = await api_client.send_dm(retry_jobs[0]["user_id"], retry_jobs[0]["message"], retry_jobs[0]["comment_id"])
    assert code2 == 202
    await db.update_job(retry_jobs[0]["job_id"], status="accepted", dm_id=data2["dm_id"])

    # Step 3: Reconcile delivery
    accepted = await db.get_accepted_jobs()
    assert len(accepted) == 1
    st_code, st_data = await api_client.get_dm_status(accepted[0]["dm_id"])
    assert st_data["status"] == "delivered"
    await db.update_job(accepted[0]["job_id"], status="delivered")

    # Step 4: Verify Stats
    stats = await db.get_stats()
    assert stats["sent"] == 1
    assert stats["failed"] == 0
    assert stats["queued"] == 0


@pytest.mark.asyncio
async def test_worker_429_rate_limited_retry_after(mocker):
    mocker.patch.object(
        api_client,
        "send_dm",
        return_value=(429, {"error": "rate_limited"}, 3)
    )

    await db.create_rule(keyword="PRICE", dm_message="Price list")
    await db.process_webhook_event({
        "event_id": "evt_429",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_429",
            "text": "PRICE",
            "from": {"user_id": "usr_429"}
        }
    })

    jobs = await db.get_queued_jobs()
    job = jobs[0]

    code, data, retry_after = await api_client.send_dm(job["user_id"], job["message"], job["comment_id"])
    assert code == 429
    assert retry_after == 3

    api_rate_limiter.pause(retry_after + 1)
    now = time.time()
    await db.update_job(
        job["job_id"],
        status="queued",
        next_retry_at=now + retry_after + 1,
        last_error="HTTP 429 Rate Limited"
    )

    # Job is waiting on retry delay so get_queued_jobs(now_ts=now) should not return it yet
    pending_now = await db.get_queued_jobs(now_ts=now)
    assert len(pending_now) == 0

    # But at now + 5, it should be ready
    pending_later = await db.get_queued_jobs(now_ts=now + 5)
    assert len(pending_later) == 1
