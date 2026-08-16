import hmac
import hashlib
import json
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db import db
from app.config import settings


def make_signature(body_bytes: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.mark.asyncio
async def test_webhook_fast_response_and_signature():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a rule first
        await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Price list here"})

        payload = {
            "event_id": "evt_test_001",
            "event_type": "comment.created",
            "sent_at": "2026-08-10T09:14:22.481Z",
            "data": {
                "comment_id": "cmt_9f2a7c",
                "post_id": "post_44de1b",
                "text": "PRICE please 🙏",
                "created_at": "2026-08-10T09:14:21.900Z",
                "from": {
                    "user_id": "usr_3b91fe",
                    "username": "arjun.shoots"
                }
            }
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        valid_sig = make_signature(body_bytes, settings.pseudogram_api_key)

        # 1. Test with valid signature
        resp = await client.post(
            "/webhook",
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-PseudoGram-Signature": valid_sig}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        assert data["event_id"] == "evt_test_001"

        # Verify job was created in DB
        queued_jobs = await db.get_queued_jobs()
        assert len(queued_jobs) == 1
        assert queued_jobs[0]["user_id"] == "usr_3b91fe"
        assert queued_jobs[0]["comment_id"] == "cmt_9f2a7c"


@pytest.mark.asyncio
async def test_webhook_invalid_signature_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "event_id": "evt_test_bad_sig",
            "event_type": "comment.created",
            "sent_at": "2026-08-10T09:14:22.481Z",
            "data": {
                "comment_id": "cmt_123",
                "text": "PRICE",
                "from": {"user_id": "usr_1"}
            }
        }
        body_bytes = json.dumps(payload).encode("utf-8")

        # Fake/Invalid signature
        resp = await client.post(
            "/webhook",
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-PseudoGram-Signature": "sha256=invalid_hex_signature"}
        )
        assert resp.status_code == 401
        assert "Invalid webhook signature" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_event_deduplication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Price list here"})

        payload = {
            "event_id": "evt_duplicate_001",
            "event_type": "comment.created",
            "sent_at": "2026-08-10T09:14:22.481Z",
            "data": {
                "comment_id": "cmt_dup_1",
                "text": "PRICE please",
                "from": {"user_id": "usr_unique_1", "username": "user1"}
            }
        }

        # First delivery of event
        resp1 = await client.post("/webhook", json=payload)
        assert resp1.status_code == 200
        assert resp1.json()["result"]["status"] == "processed"

        # Redelivery of same event_id
        resp2 = await client.post("/webhook", json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["result"]["status"] == "duplicate_event"

        # Ensure only 1 job was created in DB
        queued_jobs = await db.get_queued_jobs()
        assert len(queued_jobs) == 1
