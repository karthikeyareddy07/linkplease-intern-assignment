"""Simulation and Verification Script for 500-Event Load Testing."""
import sys
import time
import json
import random
import hmac
import hashlib
import asyncio
from typing import Dict, Any, List
import httpx


def generate_mock_events(count: int = 500) -> List[Dict[str, Any]]:
    """Generate 500 realistic events with duplicates, out-of-order timestamps, and delete events."""
    events = []
    users = [f"usr_{i:04d}" for i in range(1, 150)]  # 150 unique users -> guarantees duplicate comments
    keywords = ["PRICE", "DISCOUNT", "HELLO", "UNMATCHED"]

    # Generate pool of comments
    for i in range(count):
        user_id = random.choice(users)
        comment_id = f"cmt_{i:05d}"
        post_id = f"post_{random.randint(1, 10)}"
        keyword = random.choice(keywords)
        text = f"Can I get the {keyword} please? 🙏 #{random.randint(1, 100)}"
        evt_id = f"evt_{i:05d}"

        # 8% chance of reusing a previous event_id (simulating duplicate webhook redelivery)
        if events and random.random() < 0.08:
            reused = random.choice(events)
            events.append(reused.copy())
            continue

        # 5% chance of comment.deleted event
        if random.random() < 0.05:
            events.append({
                "event_id": evt_id,
                "event_type": "comment.deleted",
                "sent_at": "2026-08-16T12:00:00.000Z",
                "data": {"comment_id": comment_id}
            })
        else:
            events.append({
                "event_id": evt_id,
                "event_type": "comment.created",
                "sent_at": "2026-08-16T12:00:00.000Z",
                "data": {
                    "comment_id": comment_id,
                    "post_id": post_id,
                    "text": text,
                    "created_at": "2026-08-16T12:00:00.000Z",
                    "from": {"user_id": user_id, "username": f"user_{user_id}"}
                }
            })

    # Shuffle events to simulate out-of-order network arrival
    random.shuffle(events)
    return events


async def run_local_simulation(app_url: str = "http://127.0.0.1:8000", api_key: str = ""):
    """Run local load test sending 500 events over 10 seconds."""
    print(f"[*] Starting local simulation against {app_url}...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Create rule
        rule_resp = await client.post(
            f"{app_url}/rules",
            json={"keyword": "PRICE", "dm_message": "Here is the price list: $99"}
        )
        print(f"[+] Created rule: {rule_resp.json()}")

        events = generate_mock_events(500)
        print(f"[+] Generated {len(events)} events. Firing across 10 seconds...")

        start_time = time.time()
        tasks = []

        async def send_event(evt):
            raw_body = json.dumps(evt).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if api_key:
                sig = hmac.new(api_key.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
                headers["X-PseudoGram-Signature"] = f"sha256={sig}"

            # Stagger over ~10 seconds
            delay = random.uniform(0.0, 10.0)
            await asyncio.sleep(delay)
            try:
                resp = await client.post(f"{app_url}/webhook", content=raw_body, headers=headers)
                return resp.status_code
            except Exception as e:
                return f"Err: {e}"

        results = await asyncio.gather(*[send_event(e) for e in events])
        elapsed = time.time() - start_time
        success_count = sum(1 for r in results if r == 200)

        print(f"[+] Dispatched 500 events in {elapsed:.2f}s. Webhook 200 responses: {success_count}/500")

        # Fetch stats
        stats_resp = await client.get(f"{app_url}/stats")
        print(f"[+] Final System /stats: {json.dumps(stats_resp.json(), indent=2)}")


async def run_remote_simulation(base_url: str, webhook_target_url: str, api_key: str):
    """Trigger the official PseudoGram /v1/simulate/start on deployed URL."""
    print(f"[*] Triggering PseudoGram simulator on {webhook_target_url}...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{base_url}/v1/simulate/start",
            json={
                "webhook_url": f"{webhook_target_url}/webhook",
                "count": 500,
                "duration_seconds": 10
            },
            headers={"X-API-Key": api_key}
        )
        print(f"[+] Simulator Start Response: {resp.status_code} {resp.text}")
        if resp.status_code != 200:
            return

        run_id = resp.json().get("run_id")
        print(f"[+] Simulation run_id: {run_id}. Waiting for simulation to finish...")
        await asyncio.sleep(15.0)

        truth_resp = await client.get(
            f"{base_url}/v1/simulate/{run_id}/truth",
            headers={"X-API-Key": api_key}
        )
        print(f"[+] Ground Truth Result: {truth_resp.status_code}")
        print(json.dumps(truth_resp.json(), indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--remote":
        target = sys.argv[2] if len(sys.argv) > 2 else "https://your-render-app.onrender.com"
        key = sys.argv[3] if len(sys.argv) > 3 else ""
        asyncio.run(run_remote_simulation("https://pseudogram-api.onrender.com", target, key))
    else:
        asyncio.run(run_local_simulation())
