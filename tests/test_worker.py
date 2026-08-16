import time
import pytest
from app.db import db
from app.worker import BackgroundWorker
from app.client import api_client


@pytest.mark.asyncio
async def test_worker_202_accepted_and_reconciliation_delivered(mocker):
    # Mock send_dm returning 202 Accepted
    mocker.patch.object(
        api_client,
        "send_dm",
        return_value=(202, {"dm_id": "dm_mock_123", "status": "queued"}, None)
    )

    # Mock get_dm_status returning delivered
    mocker.patch.object(
        api_client,
        "get_dm_status",
        return_value=(200, {"dm_id": "dm_mock_123", "status": "delivered", "recipient_user_id": "usr_1"})
    )

    # Create rule and event
    await db.create_rule(keyword="PRICE", dm_message="Price list")
    await db.process_webhook_event({
        "event_id": "evt_worker_1",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_w1",
            "text": "PRICE please",
            "from": {"user_id": "usr_1"}
        }
    })

    # Run one step of dispatch loop
    jobs = await db.get_queued_jobs()
    assert len(jobs) == 1

    # Simulate dispatch manually
    job = jobs[0]
    code, data, _ = await api_client.send_dm(job["user_id"], job["message"], job["comment_id"])
    assert code == 202
    await db.update_job(job["job_id"], status="accepted", dm_id=data["dm_id"])

    # Verify job is in accepted status
    accepted_jobs = await db.get_accepted_jobs()
    assert len(accepted_jobs) == 1
    assert accepted_jobs[0]["dm_id"] == "dm_mock_123"

    # Simulate reconciliation
    status_code, status_data = await api_client.get_dm_status(accepted_jobs[0]["dm_id"])
    assert status_code == 200
    assert status_data["status"] == "delivered"
    await db.update_job(job["job_id"], status="delivered")

    # Verify stats
    stats = await db.get_stats()
    assert stats["sent"] == 1
    assert stats["failed"] == 0
    assert stats["queued"] == 0


@pytest.mark.asyncio
async def test_worker_400_invalid_request_marks_failed(mocker):
    mocker.patch.object(
        api_client,
        "send_dm",
        return_value=(400, {"error": "invalid_request", "detail": "Malformed recipient"}, None)
    )

    await db.create_rule(keyword="PRICE", dm_message="Price list")
    await db.process_webhook_event({
        "event_id": "evt_w_400",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_400",
            "text": "PRICE",
            "from": {"user_id": "usr_400"}
        }
    })

    jobs = await db.get_queued_jobs()
    assert len(jobs) == 1
    job = jobs[0]

    # Process job as worker would on 400
    code, data, _ = await api_client.send_dm(job["user_id"], job["message"], job["comment_id"])
    assert code == 400
    await db.update_job(job["job_id"], status="failed", last_error=data.get("detail"))

    stats = await db.get_stats()
    assert stats["failed"] == 1
    assert stats["sent"] == 0
    assert stats["queued"] == 0


@pytest.mark.asyncio
async def test_worker_delivery_failure_reconciliation_retries(mocker):
    # 1. Mock initial send returning 202
    mocker.patch.object(
        api_client,
        "send_dm",
        return_value=(202, {"dm_id": "dm_fail_test", "status": "queued"}, None)
    )

    # 2. Mock reconciliation returning failed (15% mock API drop)
    mocker.patch.object(
        api_client,
        "get_dm_status",
        return_value=(200, {"dm_id": "dm_fail_test", "status": "failed"})
    )

    await db.create_rule(keyword="PRICE", dm_message="Price list")
    await db.process_webhook_event({
        "event_id": "evt_recon_fail",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_recon_fail",
            "text": "PRICE",
            "from": {"user_id": "usr_recon_fail"}
        }
    })

    jobs = await db.get_queued_jobs()
    job = jobs[0]
    await db.update_job(job["job_id"], status="accepted", dm_id="dm_fail_test")

    # Reconciliation poll sees status failed -> re-queues job for retry
    accepted_jobs = await db.get_accepted_jobs()
    assert len(accepted_jobs) == 1
    now = time.time()
    await db.update_job(
        accepted_jobs[0]["job_id"],
        status="queued",
        dm_id=None,
        retries=1,
        next_retry_at=now,
        last_error="Delivery failed on mock API, re-queued"
    )

    # Verify job is queued again for retry
    requeued = await db.get_queued_jobs()
    assert len(requeued) == 1
    assert requeued[0]["retries"] == 1
