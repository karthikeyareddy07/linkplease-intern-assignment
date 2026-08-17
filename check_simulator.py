#!/usr/bin/env python
"""Check simulator status and retrieve results."""
import httpx
import time
import json

API_KEY = "a2FydGhpa2V5YXJlZGR5X2dvbGFtYXJpQHNybWFwLmVkdS5pbg.6ea8df416bbfa38fbf6d"
RUN_ID = "run_9f4caa6a14d6"
BASE_URL = "https://linkplease-intern-assignment-n1vf.onrender.com"

headers = {"X-API-Key": API_KEY}

print("=" * 80)
print("CHECKING SIMULATOR STATUS")
print("=" * 80)
print(f"Run ID: {RUN_ID}\n")

# Check status
for attempt in range(120):  # Check for 6 minutes
    try:
        response = httpx.get(
            f"https://pseudogram-api.onrender.com/v1/simulate/{RUN_ID}",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            status = data.get("status")
            progress = data.get("progress", {})
            events_sent = progress.get("events_sent", 0)
            events_total = progress.get("events_total", 500)
            
            pct = int((events_sent / events_total * 100)) if events_total > 0 else 0
            print(f"[{attempt+1:3d}/120] Status: {status:12s} | Progress: {events_sent:3d}/{events_total:3d} ({pct:3d}%)", end="\r")
            
            if status in ["completed", "finished"]:
                print(f"\n✓ Simulator completed!")
                break
    except Exception as e:
        print(f"[{attempt+1:3d}/120] Status check error: {str(e)[:50]}", end="\r")
    
    time.sleep(3)

print("\n" + "=" * 80)
print("RETRIEVING OFFICIAL TRUTH")
print("=" * 80)

try:
    response = httpx.get(
        f"https://pseudogram-api.onrender.com/v1/simulate/{RUN_ID}/truth",
        headers=headers,
        timeout=15
    )
    if response.status_code == 200:
        truth = response.json()
        print("✓ Official Truth Retrieved:\n")
        print(json.dumps(truth, indent=2))
        
        # Extract key metrics
        print("\nKey Metrics from Truth:")
        print(f"  sent: {truth.get('sent', 0)}")
        print(f"  failed: {truth.get('failed', 0)}")
        print(f"  duplicates: {truth.get('duplicates', 0)}")
    else:
        print(f"✗ Error: HTTP {response.status_code}")
        print(response.text[:500])
except Exception as e:
    print(f"✗ Exception: {e}")

print("\n" + "=" * 80)
print("RETRIEVING APPLICATION STATS")
print("=" * 80)

time.sleep(15)  # Give app time to process
try:
    response = httpx.get(f"{BASE_URL}/stats", timeout=10)
    if response.status_code == 200:
        stats = response.json()
        print("✓ Application Stats:\n")
        print(json.dumps(stats, indent=2))
    else:
        print(f"✗ Error: HTTP {response.status_code}")
except Exception as e:
    print(f"✗ Exception: {e}")
