#!/usr/bin/env python
"""Verify deployed endpoints and run official simulator test."""
import httpx
import json
import time
import os

os.chdir(r"c:\Users\NAGAVENI\.gemini\antigravity-ide\scratch\linkplease-intern-assignment")

# Configuration
BASE_URL = "https://linkplease-intern-assignment-n1vf.onrender.com"
PSEUDOGRAM_API_URL = "https://pseudogram-api.onrender.com"
API_KEY = "a2FydGhpa2V5YXJlZGR5X2dvbGFtYXJpQHNybWFwLmVkdS5pbg.6ea8df416bbfa38fbf6d"

def test_endpoints():
    """Test all deployed endpoints."""
    print("\n" + "=" * 80)
    print("DEPLOYED ENDPOINT VERIFICATION")
    print("=" * 80)
    
    endpoints = ["/health", "/stats", "/rules", "/docs", "/"]
    
    for endpoint in endpoints:
        url = BASE_URL + endpoint
        try:
            response = httpx.get(url, timeout=15.0, follow_redirects=True)
            status_marker = "✓" if response.status_code == 200 else "⚠"
            print(f"{status_marker} {endpoint:20} → HTTP {response.status_code}")
            
            if response.status_code == 200 and endpoint in ["/health", "/stats", "/rules"]:
                try:
                    data = response.json()
                    json_str = json.dumps(data, indent=2)
                    preview = json_str[:150].replace("\n", " ")
                    print(f"  {preview}...")
                except:
                    print(f"  (Response received)")
        except Exception as e:
            print(f"✗ {endpoint:20} → ERROR: {str(e)[:80]}")
    
    print("=" * 80)

def get_initial_stats():
    """Get initial stats before simulation."""
    print("\n[1/6] Retrieving initial stats...")
    try:
        response = httpx.get(f"{BASE_URL}/stats", timeout=10)
        if response.status_code == 200:
            stats = response.json()
            print(f"Initial stats: {stats}")
            return stats
    except Exception as e:
        print(f"Error getting stats: {e}")
    return None

def run_simulator():
    """Run the official 500-event simulator."""
    print("\n[2/6] Starting official PseudoGram 500-event simulator...")
    print(f"Target: {BASE_URL}/webhook")
    print("Events: 500 | Duration: 10 seconds")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "webhook_url": f"{BASE_URL}/webhook",
        "count": 500,
        "duration_seconds": 10
    }
    
    try:
        response = httpx.post(
            f"{PSEUDOGRAM_API_URL}/v1/simulate/start",
            json=payload,
            headers=headers,
            timeout=30.0
        )
        
        if response.status_code in [200, 201, 202]:
            data = response.json()
            run_id = data.get("run_id")
            print(f"✓ Simulator started")
            print(f"  Run ID: {run_id}")
            print(f"  Status: {data.get('status', 'unknown')}")
            return run_id
        else:
            print(f"✗ Error starting simulator: HTTP {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"✗ Exception: {e}")
        return None

def wait_for_simulator(run_id, max_wait=60):
    """Wait for simulator to complete."""
    print(f"\n[3/6] Waiting for simulator to complete (max {max_wait}s)...")
    headers = {"X-API-Key": API_KEY}
    
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            response = httpx.get(
                f"{PSEUDOGRAM_API_URL}/v1/simulate/{run_id}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                print(f"  Status: {status}...", end="\r")
                
                if status in ["completed", "finished"]:
                    print(f"\n✓ Simulator completed!")
                    return data
        except Exception as e:
            print(f"  Check error: {e}")
        
        time.sleep(2)
    
    print(f"\n✗ Simulator did not complete within {max_wait} seconds")
    return None

def get_official_truth(run_id):
    """Retrieve the official truth data."""
    print(f"\n[4/6] Retrieving official truth for run {run_id}...")
    headers = {"X-API-Key": API_KEY}
    
    try:
        response = httpx.get(
            f"{PSEUDOGRAM_API_URL}/v1/simulate/{run_id}/truth",
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            truth = response.json()
            print(f"✓ Official truth retrieved")
            
            # Extract key statistics
            sent_count = truth.get("sent", 0)
            failed_count = truth.get("failed", 0)
            duplicates_count = truth.get("duplicates", 0)
            
            print(f"  Official Truth Statistics:")
            print(f"    - Sent (delivered): {sent_count}")
            print(f"    - Failed: {failed_count}")
            print(f"    - Duplicates: {duplicates_count}")
            
            return truth
        else:
            print(f"✗ Error retrieving truth: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"✗ Exception: {e}")
        return None

def get_final_stats():
    """Get final stats from application."""
    print(f"\n[5/6] Retrieving final application stats...")
    
    # Wait a bit for processing
    print("  (Waiting 5 seconds for background processing...)")
    time.sleep(5)
    
    try:
        response = httpx.get(f"{BASE_URL}/stats", timeout=10)
        if response.status_code == 200:
            stats = response.json()
            print(f"✓ Application stats retrieved")
            print(f"  sent: {stats.get('sent', 0)}")
            print(f"  failed: {stats.get('failed', 0)}")
            print(f"  queued: {stats.get('queued', 0)}")
            print(f"  duplicates_blocked: {stats.get('duplicates_blocked', 0)}")
            return stats
        else:
            print(f"✗ Error: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"✗ Exception: {e}")
        return None

def compare_results(truth, app_stats):
    """Compare official truth with application stats."""
    print(f"\n[6/6] Comparing official truth vs. application stats...")
    print("=" * 80)
    
    if not truth or not app_stats:
        print("✗ Cannot compare: missing data")
        return False
    
    # Extract values
    truth_sent = truth.get("sent", 0)
    truth_failed = truth.get("failed", 0)
    truth_dupes = truth.get("duplicates", 0)
    
    app_sent = app_stats.get("sent", 0)
    app_failed = app_stats.get("failed", 0)
    app_queued = app_stats.get("queued", 0)
    app_dupes = app_stats.get("duplicates_blocked", 0)
    
    issues = []
    
    # Check sent count
    if app_sent == truth_sent:
        print(f"✓ SENT: {app_sent} == {truth_sent} (MATCH)")
    else:
        print(f"✗ SENT: {app_sent} != {truth_sent} (MISMATCH)")
        issues.append(f"sent count mismatch: {app_sent} vs {truth_sent}")
    
    # Check failed count
    if app_failed == truth_failed:
        print(f"✓ FAILED: {app_failed} == {truth_failed} (MATCH)")
    else:
        print(f"✗ FAILED: {app_failed} != {truth_failed} (MISMATCH)")
        issues.append(f"failed count mismatch: {app_failed} vs {truth_failed}")
    
    # Check duplicates
    if app_dupes == truth_dupes:
        print(f"✓ DUPLICATES: {app_dupes} == {truth_dupes} (MATCH)")
    else:
        print(f"✗ DUPLICATES: {app_dupes} != {truth_dupes} (MISMATCH)")
        issues.append(f"duplicates mismatch: {app_dupes} vs {truth_dupes}")
    
    # Check queued (should be 0 or minimal)
    if app_queued == 0:
        print(f"✓ QUEUED: {app_queued} == 0 (NO BACKLOG)")
    else:
        print(f"⚠ QUEUED: {app_queued} > 0 (jobs still processing)")
    
    # Check total
    total_expected = truth_sent + truth_failed + truth_dupes
    total_actual = app_sent + app_failed + app_dupes
    
    if total_expected == total_actual:
        print(f"✓ TOTAL: {total_actual} == {total_expected} (MATCH)")
    else:
        print(f"✗ TOTAL: {total_actual} != {total_expected} (MISMATCH)")
        issues.append(f"total mismatch: {total_actual} vs {total_expected}")
    
    print("=" * 80)
    
    if issues:
        print("\n❌ VERIFICATION FAILED - Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("\n✅ VERIFICATION PASSED - All metrics match!")
        return True

def main():
    """Run full verification flow."""
    print("\n" + "█" * 80)
    print("█ LINKPLEASE ASSIGNMENT - OFFICIAL VERIFICATION TEST")
    print("█" * 80)
    
    # Step 1: Test endpoints
    test_endpoints()
    
    # Step 2: Get initial stats
    initial_stats = get_initial_stats()
    
    # Step 3-6: Run simulator and compare
    run_id = run_simulator()
    
    if run_id:
        simulator_result = wait_for_simulator(run_id, max_wait=120)
        
        if simulator_result:
            truth = get_official_truth(run_id)
            final_stats = get_final_stats()
            
            if truth and final_stats:
                success = compare_results(truth, final_stats)
                
                if success:
                    print("\n" + "█" * 80)
                    print("█ ✅ OFFICIAL TEST PASSED - READY FOR SUBMISSION")
                    print("█" * 80)
                    return 0
                else:
                    print("\n" + "█" * 80)
                    print("█ ❌ OFFICIAL TEST FAILED - ISSUES DETECTED")
                    print("█" * 80)
                    return 1
    
    print("\n❌ Test execution incomplete")
    return 1

if __name__ == "__main__":
    exit(main())
