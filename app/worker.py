"""Background Worker for Rate-Limited DM Dispatching, Retries, and Delivery Reconciliation."""
import asyncio
import logging
import time
from typing import Optional
from app.config import settings
from app.db import db
from app.rate_limiter import api_rate_limiter
from app.client import api_client

logger = logging.getLogger("linkplease.worker")


class BackgroundWorker:
    def __init__(self):
        self._running = False
        self._dispatch_task: Optional[asyncio.Task] = None
        self._reconciliation_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start background worker tasks."""
        if self._running:
            return
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        self._reconciliation_task = asyncio.create_task(self._reconciliation_loop())
        logger.info("Background worker started.")

    async def stop(self):
        """Gracefully stop background worker tasks."""
        self._running = False
        if self._dispatch_task:
            self._dispatch_task.cancel()
        if self._reconciliation_task:
            self._reconciliation_task.cancel()
        await asyncio.gather(
            self._dispatch_task,
            self._reconciliation_task,
            return_exceptions=True
        )
        await api_client.close()
        logger.info("Background worker stopped.")

    async def _dispatch_loop(self):
        """Continuously process queued DM jobs while respecting strict rate limits."""
        while self._running:
            try:
                now = time.time()
                # Fetch up to 5 queued jobs that are ready to send/retry
                jobs = await db.get_queued_jobs(limit=5, now_ts=now)

                if not jobs:
                    await asyncio.sleep(settings.worker_poll_interval_seconds)
                    continue

                for job in jobs:
                    if not self._running:
                        break

                    job_id = job["job_id"]
                    comment_id = job["comment_id"]
                    user_id = job["user_id"]
                    message = job["message"]
                    rule_id = job["rule_id"]
                    retries = job["retries"]

                    # 1. Check if comment was deleted before sending
                    if await db.is_comment_deleted(comment_id):
                        await db.update_job(job_id=job_id, status="cancelled_deleted", last_error="Comment deleted before dispatch")
                        continue

                    # 2. Acquire strict rate limit token (<= 10 reqs / 60s)
                    await api_rate_limiter.acquire()

                    # 3. Deterministic Idempotency Key
                    idempotency_key = f"{rule_id}_{user_id}_{comment_id}"

                    # 4. Dispatch DM to mock API
                    status_code, data, retry_after = await api_client.send_dm(
                        recipient_user_id=user_id,
                        message=message,
                        comment_id=comment_id,
                        idempotency_key=idempotency_key
                    )

                    now = time.time()

                    if status_code == 202:
                        # Accepted by mock API -> transition to accepted state for delivery polling
                        dm_id = data.get("dm_id")
                        await db.update_job(
                            job_id=job_id,
                            status="accepted",
                            dm_id=dm_id,
                            last_error=None
                        )

                    elif status_code == 429:
                        # Rate limited: respect Retry-After header
                        delay = retry_after if (retry_after is not None and retry_after > 0) else 60.0
                        api_rate_limiter.pause(delay + 1.0)
                        await db.update_job(
                            job_id=job_id,
                            status="queued",
                            next_retry_at=now + delay + 1.0,
                            last_error=f"HTTP 429 Rate Limited (Retry-After: {delay}s)"
                        )

                    elif status_code == 400:
                        # Permanent client failure: do NOT retry
                        detail = data.get("detail", "invalid_request")
                        await db.update_job(
                            job_id=job_id,
                            status="failed",
                            last_error=f"HTTP 400 Invalid Request: {detail}"
                        )

                    elif status_code in (500, 502, 503, 504):
                        # Transient server failure: exponential backoff
                        new_retries = retries + 1
                        if new_retries >= settings.max_retries:
                            await db.update_job(
                                job_id=job_id,
                                status="failed",
                                retries=new_retries,
                                last_error=f"HTTP {status_code} Max retries ({settings.max_retries}) exceeded"
                            )
                        else:
                            backoff_seconds = min(60.0, float(2 ** new_retries))
                            await db.update_job(
                                job_id=job_id,
                                status="queued",
                                retries=new_retries,
                                next_retry_at=now + backoff_seconds,
                                last_error=f"HTTP {status_code} transient error, retrying in {backoff_seconds}s"
                            )

                    elif 401 <= status_code < 500:
                        # Other 4xx errors (e.g. 401 Unauthorized, 403 Forbidden)
                        await db.update_job(
                            job_id=job_id,
                            status="failed",
                            last_error=f"HTTP {status_code} Fatal Client Error: {data}"
                        )

                    else:
                        # Unexpected status code: retry with backoff
                        new_retries = retries + 1
                        if new_retries >= settings.max_retries:
                            await db.update_job(
                                job_id=job_id,
                                status="failed",
                                retries=new_retries,
                                last_error=f"HTTP {status_code} unexpected response, max retries reached"
                            )
                        else:
                            backoff_seconds = min(60.0, float(2 ** new_retries))
                            await db.update_job(
                                job_id=job_id,
                                status="queued",
                                retries=new_retries,
                                next_retry_at=now + backoff_seconds,
                                last_error=f"HTTP {status_code} unexpected response, retrying"
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in dispatch loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _reconciliation_loop(self):
        """
        Periodically poll mock API for delivery status on accepted DMs.
        Reads do NOT count against rate limit.
        """
        while self._running:
            try:
                # Fetch accepted jobs awaiting terminal status confirmation
                accepted_jobs = await db.get_accepted_jobs(limit=15)

                if not accepted_jobs:
                    await asyncio.sleep(settings.reconciliation_interval_seconds)
                    continue

                for job in accepted_jobs:
                    if not self._running:
                        break

                    job_id = job["job_id"]
                    dm_id = job["dm_id"]
                    retries = job["retries"]

                    if not dm_id:
                        continue

                    status_code, data = await api_client.get_dm_status(dm_id)
                    now = time.time()

                    if status_code == 200:
                        dm_status = data.get("status")

                        if dm_status == "delivered":
                            # Terminal success confirmed by mock API
                            await db.update_job(
                                job_id=job_id,
                                status="delivered",
                                last_error=None
                            )

                        elif dm_status == "failed":
                            # DM failed after initial 202 acceptance (~15% drop rate in mock API)
                            new_retries = retries + 1
                            if new_retries >= settings.max_retries:
                                await db.update_job(
                                    job_id=job_id,
                                    status="failed",
                                    retries=new_retries,
                                    last_error="Delivery failed on mock API after acceptance (max retries reached)"
                                )
                            else:
                                # Re-queue the job to retry sending
                                backoff_seconds = min(60.0, float(2 ** new_retries))
                                await db.update_job(
                                    job_id=job_id,
                                    status="queued",
                                    dm_id=None,
                                    retries=new_retries,
                                    next_retry_at=now + backoff_seconds,
                                    last_error=f"Delivery failed on mock API, re-queued attempt {new_retries}"
                                )

                        elif dm_status == "queued":
                            # Still processing inside mock API
                            pass

                    elif status_code == 404:
                        # DM ID not found on mock API, treat as failed delivery
                        new_retries = retries + 1
                        if new_retries >= settings.max_retries:
                            await db.update_job(
                                job_id=job_id,
                                status="failed",
                                retries=new_retries,
                                last_error="DM not found on mock API (404)"
                            )
                        else:
                            await db.update_job(
                                job_id=job_id,
                                status="queued",
                                dm_id=None,
                                retries=new_retries,
                                next_retry_at=now + (2.0 ** new_retries),
                                last_error="DM 404 on status check, re-queued"
                            )

                await asyncio.sleep(settings.reconciliation_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reconciliation loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)


# Global worker instance
worker = BackgroundWorker()
