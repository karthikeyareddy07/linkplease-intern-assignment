import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_create_rule_success():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "keyword": "PRICE",
            "dm_message": "Here's the price list: https://example.com/pricing"
        }
        response = await client.post("/rules", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "rule_id" in data
        assert data["keyword"] == "PRICE"
        assert data["dm_message"] == payload["dm_message"]


@pytest.mark.asyncio
async def test_create_rule_empty_keyword_or_message():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Empty keyword
        resp = await client.post("/rules", json={"keyword": "   ", "dm_message": "test"})
        assert resp.status_code in (400, 422)

        # Empty message
        resp2 = await client.post("/rules", json={"keyword": "PRICE", "dm_message": "   "})
        assert resp2.status_code in (400, 422)


@pytest.mark.asyncio
async def test_list_rules():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/rules", json={"keyword": "PRICE", "dm_message": "Price list"})
        await client.post("/rules", json={"keyword": "DISCOUNT", "dm_message": "10% off"})

        resp = await client.get("/rules")
        assert resp.status_code == 200
        rules = resp.json()
        assert len(rules) == 2
        keywords = [r["keyword"] for r in rules]
        assert "PRICE" in keywords
        assert "DISCOUNT" in keywords
