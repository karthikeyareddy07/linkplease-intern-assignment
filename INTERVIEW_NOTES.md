# INTERVIEW_NOTES.md — Technical Guide & Interview Preparation

This document serves as your personal cheat sheet for explaining the design, architecture, and code decisions during your interview for the LinkPlease Tech Intern position.

---

## 1. Executive Summary (The 30-Second Pitch)

> *"I built a resilient, event-driven Instagram comment-to-DM automation engine in Python with FastAPI and SQLite. It treats the upstream mock API as completely hostile and unreliable. Webhooks respond in under 5ms, events and duplicate comments are deduplicated durably at the database level, requests are strictly throttled through a sliding-window rate limiter ensuring we never exceed 10 requests per minute, and accepted DMs are polled and reconciled in the background to handle the upstream API's 15% post-acceptance failure rate."*

---

## 2. Core Architectural Concepts

### A. Request Flow
1. **Webhook Ingestion:** Webhook hits `POST /webhook`.
2. **Signature Verification:** Validates `X-PseudoGram-Signature` via constant-time HMAC-SHA256 comparison.
3. **Atomic Deduplication:** Ingests `event_id` into the `events` table (ON CONFLICT IGNORE).
4. **Keyword Matching:** Evaluates active rules using word-boundary regex (`(?<!\w)PRICE(?!\w)`).
5. **Durable User+Rule Locking:** Attempts atomic insert into `processed_user_rules` (`PRIMARY KEY (rule_id, user_id)`). If duplicate, logs to `duplicate_blocks` and stops. If new, inserts job into `jobs` table (`status = 'queued'`).
6. **Instant Response:** Returns HTTP 200 within 5ms.
7. **Background Worker:**
   - Pre-dispatch check on `deleted_comments`.
   - Acquires token from `RateLimiter` (<= 10 requests per 60s).
   - Calls `POST /v1/dm/send` with deterministic `Idempotency-Key`.
   - Moves job to `accepted` on HTTP 202.
8. **Delivery Reconciliation:**
   - Reconciler polls `GET /v1/dm/{dm_id}` (reads do not consume rate limit).
   - If `delivered`: marks job `delivered` (`sent` counter increments).
   - If `failed`: re-queues job with exponential backoff up to `max_retries = 5`.

---

## 3. Deep Dive into Technical Questions

### Q1: How do you guarantee that the same user never receives two DMs for the same rule?
* **Answer:** *"We enforce uniqueness at the database level rather than using in-memory caches or sets. The `processed_user_rules` table uses a composite primary key `(rule_id, user_id)`. When a comment arrives, we attempt an atomic insert. The first comment succeeds and queues the DM. Any subsequent comments from the same user under that rule trigger an `sqlite3.IntegrityError`, which we catch and log into an audit table (`duplicate_blocks`). This guarantees zero duplicates even under concurrent webhook delivery across multiple processes."*

### Q2: Why did you use `user_id` instead of `username`?
* **Answer:** *"Instagram usernames are mutable—users can change their handles at any time, but `user_id` is an immutable, unique platform identifier. Keying deduplication on `username` would fail if a user updated their handle."*

### Q3: How is rate limiting implemented?
* **Answer:** *"The mock API allows strictly 10 requests per rolling 60 seconds. We implemented an asynchronous sliding-window token bucket in `app/rate_limiter.py`. Before making any mutating request (`POST /v1/dm/send`), the worker calls `await rate_limiter.acquire()`. If 10 requests have been made in the last 60 seconds, it calculates the exact time until the oldest request leaves the 60-second window and sleeps asynchronously. Additionally, if a 429 response is encountered, it pauses the rate limiter for the duration specified in the `Retry-After` header."*

### Q4: Why does `202 Accepted` not immediately count as `sent`?
* **Answer:** *"HTTP 202 indicates that the server accepted the job for processing, not that the DM reached the user's inbox. In the mock API, approximately 15% of accepted DMs fail asynchronously. Incrementing `sent` on 202 would report false statistics. We only transition the status to `delivered` (and increment `sent`) after polling `GET /v1/dm/{dm_id}` and receiving `status: delivered`."*

### Q5: How do you handle `comment.deleted` events?
* **Answer:** *"When a `comment.deleted` event arrives, we record the `comment_id` in the `deleted_comments` table and immediately cancel any pending jobs for that comment that are still in `status = 'queued'`. If a deletion event arrives out-of-order before the `comment.created` event, the creation handler checks `deleted_comments` first and skips job creation entirely."*

---

## 4. File-by-File Code Walkthrough

### `app/config.py`
- **Purpose:** Centralized, validated environment configuration using `pydantic-settings`.
- **Key Settings:** `pseudogram_api_key`, `pseudogram_base_url`, `rate_limit_requests` (10), `rate_limit_window_seconds` (60.0), `max_retries` (5).

### `app/models.py`
- **Purpose:** Pydantic schemas enforcing the exact API contracts specified in the prompt (`POST /rules`, `POST /webhook`, `GET /stats`, `GET /health`).

### `app/matcher.py`
- **Purpose:** Case-insensitive, boundary-aware keyword matching.
- **Key Logic:** Uses `(?<!\w)KEYWORD(?!\w)` regex to match `"price please"` and `"Can I get the price?"` while avoiding false positives like `"priceless"`.

### `app/db.py`
- **Purpose:** Thread-safe SQLite database manager running in WAL mode with connection busy timeouts and atomic transactions.
- **Key Tables:** `rules`, `events`, `deleted_comments`, `processed_user_rules`, `duplicate_blocks`, `jobs`.
- **Key Functions:** `process_webhook_event()`, `get_queued_jobs()`, `get_accepted_jobs()`, `update_job()`, `get_stats()`.

### `app/rate_limiter.py`
- **Purpose:** Thread-safe sliding-window rate limiter.
- **Key Functions:** `acquire()`, `pause(seconds)`.

### `app/client.py`
- **Purpose:** Async HTTP client using `httpx.AsyncClient` with reusable connection pools.
- **Key Functions:** `send_dm()` (includes `Idempotency-Key` header), `get_dm_status()`.

### `app/worker.py`
- **Purpose:** Autonomous background worker running two concurrent loops:
  1. `_dispatch_loop`: Polls queued jobs, acquires rate limit tokens, handles 429/500/400 responses.
  2. `_reconciliation_loop`: Polls accepted DMs for terminal delivery confirmation and re-queues drops.

### `app/main.py`
- **Purpose:** FastAPI entry point exposing routes and signature verification middleware.

---

## 5. Tradeoffs & Future Work (For Loom / Interview)

### Tradeoff Made & What Was Given Up:
> *"I chose an embedded SQLite database in WAL mode over an external distributed Redis/PostgreSQL setup. This allowed the entire engine to be completely self-contained, zero-dependency, and instantly runnable with atomic ACID guarantees. The tradeoff is that horizontal scaling across multiple container instances is constrained by SQLite's single-file write lock."*

### What I Would Do Differently With One More Week:
> *"With one more week, I would introduce a distributed Redis message broker with Celery/RQ or BullMQ and a PostgreSQL backend. This would enable multi-instance horizontal scaling, priority queueing (prioritizing fresh comments over retry backlogs), and Redis-backed distributed token buckets."*
