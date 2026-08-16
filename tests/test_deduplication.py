import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db import db


@pytest.mark.asyncio
async def test_same_user_multiple_comments_same_rule():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create single rule for PRICE
        await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Pricing details"})

        # User 1 comments first time
        evt1 = {
            "event_id": "evt_u1_c1",
            "event_type": "comment.created",
            "data": {
                "comment_id": "cmt_1",
                "text": "PRICE please",
                "from": {"user_id": "usr_karthik", "username": "karthik"}
            }
        }
        resp1 = await client.post("/webhook", json=evt1)
        assert resp1.status_code == 200
        assert resp1.json()["result"]["jobs_created"] == 1
        assert resp1.json()["result"]["duplicates_blocked"] == 0

        # User 1 comments second time on a different post with different comment_id
        evt2 = {
            "event_id": "evt_u1_c2",
            "event_type": "comment.created",
            "data": {
                "comment_id": "cmt_2",
                "text": "what is the price?",
                "from": {"user_id": "usr_karthik", "username": "karthik_changed_name"}
            }
        }
        resp2 = await client.post("/webhook", json=evt2)
        assert resp2.status_code == 200
        assert resp2.json()["result"]["jobs_created"] == 0
        assert resp2.json()["result"]["duplicates_blocked"] == 1

        # User 1 comments third time
        evt3 = {
            "event_id": "evt_u1_c3",
            "event_type": "comment.created",
            "data": {
                "comment_id": "cmt_3",
                "text": "PRICE",
                "from": {"user_id": "usr_karthik"}
            }
        }
        resp3 = await client.post("/webhook", json=evt3)
        assert resp3.status_code == 200
        assert resp3.json()["result"]["jobs_created"] == 0
        assert resp3.json()["result"]["duplicates_blocked"] == 1

        # Verify stats reflect 2 duplicate blocks and 1 queued job
        stats = (await client.get("/stats")).json()
        assert stats["duplicates_blocked"] == 2
        assert stats["queued"] == 1


@pytest.mark.asyncio
async def test_different_users_matching_same_rule():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Pricing details"})

        # User A
        await client.post("/webhook", json={
            "event_id": "evt_a",
            "event_type": "comment.created",
            "data": {"comment_id": "cmt_a", "text": "price", "from": {"user_id": "usr_a"}}
        })

        # User B
        await client.post("/webhook", json={
            "event_id": "evt_b",
            "event_type": "comment.created",
            "data": {"comment_id": "cmt_b", "text": "price", "from": {"user_id": "usr_b"}}
        })

        stats = (await client.get("/stats")).json()
        assert stats["queued"] == 2
        assert stats["duplicates_blocked"] == 0


@pytest.mark.asyncio
async def test_same_user_matching_multiple_rules():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Rule 1: PRICE
        await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Price list"})
        # Rule 2: DISCOUNT
        await client.post("/rules", json={"keyword": "DISCOUNT", "dm_message": "Discount coupon"})

        # User comments text containing BOTH keywords
        await client.post("/webhook", json={
            "event_id": "evt_multi_1",
            "event_type": "comment.created",
            "data": {
                "comment_id": "cmt_multi",
                "text": "What is the PRICE and do you have a DISCOUNT?",
                "from": {"user_id": "usr_multi"}
            }
        })

        # Both rules should trigger once for this user
        stats = (await client.get("/stats")).json()
        assert stats["queued"] == 2
        assert stats["duplicates_blocked"] == 0

        # If user comments again with PRICE only -> PRICE is blocked as duplicate
        await client.post("/webhook", json={
            "event_id": "evt_multi_2",
            "event_type": "comment.created",
            "data": {
                "comment_id": "cmt_multi_2",
                "text": "PRICE please",
                "from": {"user_id": "usr_multi"}
            }
        })

        stats2 = (await client.get("/stats")).json()
        assert stats2["queued"] == 2
        assert stats2["duplicates_blocked"] == 1
