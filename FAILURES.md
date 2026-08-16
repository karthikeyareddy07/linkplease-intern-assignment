# FAILURES.md — System Failure Modes & Analysis

This document provides a realistic, transparent analysis of potential failure modes, edge cases, and architectural tradeoffs in the LinkPlease automation engine based on actual load testing and implementation realities.

---

### Failure 1 — Webhook Delivery Races Before SQLite Write Serialization
* **Condition:** Two identical webhook events (same `event_id` or same `(rule_id, user_id)`) arrive within a sub-millisecond window across parallel worker threads.
* **Why it happens:** In an in-memory or purely application-level check (`if user_id not in cache`), both requests read the table before either completes its insert transaction.
* **Impact:** Risk of duplicate DM dispatch or incorrect increment of `duplicates_blocked`.
* **Current Mitigation:** Mitigated via atomic SQLite database transactions using `INSERT INTO processed_user_rules (rule_id, user_id, ...)` backed by a compound `PRIMARY KEY (rule_id, user_id)`. The first transaction commits and the second fails with an `sqlite3.IntegrityError`, atomically recording a record in `duplicate_blocks`.
* **Remaining Limitation:** SQLite table-level / write locks during heavy write contention can cause busy timeout delays if webhook throughput exceeds 1,000 requests/second on a single disk thread.

---

### Failure 2 — Ephemeral Filesystem Reset on Free-Tier Container Restarts
* **Condition:** The Render free-tier container restarts or spins down after inactivity while queued jobs are waiting in `status = 'queued'` or `status = 'accepted'`.
* **Why it happens:** SQLite database files stored in local ephemeral container disk (`linkplease.db`) are wiped on container rebuilds or dynamic spin-downs unless a persistent volume or external database (e.g., PostgreSQL via `DATABASE_URL`) is attached.
* **Impact:** Queued DMs waiting on rate-limit intervals or retries would be permanently lost upon cold container restarts.
* **Current Mitigation:** Database schema and SQL transactions are designed for standard relational databases; setting `DATABASE_URL` allows instant plug-and-play with external PostgreSQL on production.
* **Remaining Limitation:** On local SQLite or free ephemeral Render containers without mounted persistent disks, pending jobs scheduled for future retry will be lost on container recreation.

---

### Failure 3 — Rate Limit Head-of-Line Blocking under High Ingestion Volume
* **Condition:** 500 comment events arrive within 10 seconds matching a rule, resulting in 500 queued DMs, while the mock API enforces a strict limit of 10 requests per rolling 60 seconds.
* **Why it happens:** At 10 requests / 60 seconds (1 request every 6.0 seconds), clearing a backlog of 500 queued DMs requires 50 minutes of continuous rate-limited dispatching (`500 / (10/60) = 3000s`).
* **Impact:** While no DMs are lost or dropped, commenters at the tail of the queue experience delivery latency of up to 50 minutes. `GET /stats` accurately reflects `queued: 450+` during this period.
* **Current Mitigation:** Sliding window rate limiter queues all valid jobs with deterministic FIFO ordering (`ORDER BY created_at ASC`), ensuring zero 429 violations and zero dropped messages.
* **Remaining Limitation:** The bottleneck is the upstream platform rate limit (10 req/min). To decrease latency without violating platform limits, priority queueing (e.g. prioritizing fresh comments over retries) or batched DM endpoints (if supported upstream) would be required.

---

### Failure 4 — Delayed `comment.deleted` Event After Mock API DM Dispatch
* **Condition:** A creator or user deletes their comment after the DM worker has called `POST /v1/dm/send` (receiving `202 Accepted`), but before the mock API finishes internal delivery (`status = 'delivered'`).
* **Why it happens:** The upstream mock API does not expose a DM cancellation endpoint (`DELETE /v1/dm/{dm_id}`). Once the mock API returns HTTP 202, the message is queued inside the mock API's internal delivery engine.
* **Impact:** The commenter still receives the DM even though they deleted their comment right after posting.
* **Current Mitigation:** We immediately check the `deleted_comments` registry prior to acquiring rate limit tokens and dispatching to `POST /v1/dm/send`, cancelling any pending queued jobs before dispatch.
* **Remaining Limitation:** Unresolvable without an upstream `DELETE /v1/dm/{dm_id}` cancellation API.

---

### Failure 5 — Asynchronous Mock API Delivery Failures Exhausting Max Retries
* **Condition:** A DM is accepted by the mock API with `HTTP 202 Accepted`, but the mock API's background delivery engine subsequently marks it as `status = 'failed'` (which happens ~15% of the time).
* **Why it happens:** Network drops, recipient privacy blocks, or mock API transient delivery drops.
* **Impact:** If the delivery status reconciler encounters continuous failures across 5 consecutive retry attempts, the job is marked `status = 'failed'`, incrementing the `failed` counter.
* **Current Mitigation:** Delivery status reconciler polls `GET /v1/dm/{dm_id}` without consuming rate limits, detects `status = 'failed'`, and automatically re-queues the job with exponential backoff up to `MAX_RETRIES = 5`.
* **Remaining Limitation:** If the failure is caused by permanent recipient restrictions (e.g., private account, blocked bot), retries will eventually exhaust and legitimately report `failed: 1` in `/stats`.
