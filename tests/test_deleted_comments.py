import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db import db


@pytest.mark.asyncio
async def test_comment_deleted_after_creation_cancels_queued_job():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Price list"})

        # 1. Comment created
        await client.post("/webhook", json={
            "event_id": "evt_c1",
            "event_type": "comment.created",
            "data": {
                "comment_id": "cmt_to_delete",
                "text": "PRICE please",
                "from": {"user_id": "usr_del_1"}
            }
        })

        # Verify job is queued
        queued_jobs = await db.get_queued_jobs()
        assert len(queued_jobs) == 1
        assert queued_jobs[0]["status"] == "queued"

        # 2. Comment deleted event arrives
        resp = await client.post("/webhook", json={
            "event_id": "evt_d1",
            "event_type": "comment.deleted",
            "data": {
                "comment_id": "cmt_to_delete"
            }
        })
        assert resp.status_code == 200

        # Verify job was cancelled
        queued_jobs_after = await db.get_queued_jobs()
        assert len(queued_jobs_after) == 0


@pytest.mark.asyncio
async def test_out_of_order_deleted_arriving_before_created():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Price list"})

        # 1. comment.deleted arrives FIRST (out of order delivery)
        resp_del = await client.post("/webhook", json={
            "event_id": "evt_early_delete",
            "event_type": "comment.deleted",
            "data": {
                "comment_id": "cmt_out_of_order"
            }
        })
        assert resp_del.status_code == 200

        # 2. comment.created arrives SECOND
        resp_create = await client.post("/webhook", json={
            "event_id": "evt_late_created",
            "event_type": "comment.created",
            "data": {
                "comment_id": "cmt_out_of_order",
                "text": "PRICE please",
                "from": {"user_id": "usr_out_of_order"}
            }
        })
        assert resp_create.status_code == 200
        assert resp_create.json()["result"]["status"] == "already_deleted"

        # Verify NO queued jobs were created
        queued_jobs = await db.get_queued_jobs()
        assert len(queued_jobs) == 0
