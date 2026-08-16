# LinkPlease Instagram Automation Engine

A high-reliability, production-grade comment-to-DM automation engine built for the LinkPlease Tech Intern Assignment. The system reliably handles hostile, unreliable upstream mock platform conditions—including network failures, 429 rate limits, out-of-order deliveries, duplicate events, and asynchronous DM delivery drops.

---

## 1. Architectural Overview

```
                                  +---------------------------------------------+
                                  |              Client / Webhook               |
                                  +---------------------------------------------+
                                                         |
                                       (HMAC-SHA256 Sig Verification)
                                                         v
+---------------------------------------------------------------------------------------------------------+
|                                              FastAPI Server                                             |
|                                                                                                         |
|  +---------------------------+  +---------------------------+  +-------------------------------------+  |
|  |     POST /rules           |  |     POST /webhook         |  |     GET /stats                      |  |
|  |  (Keyword & DM Template)  |  |  (Fast ACK <= 5ms)        |  |  (Real-time DB query: sent/failed/  |  |
|  +-------------+-------------+  +-------------+-------------+  |   queued/duplicates_blocked)        |  |
|                |                              |                +-------------------------------------+  |
+----------------|------------------------------|---------------------------------------------------------+
                 |                              |
                 v                              v
+---------------------------------------------------------------------------------------------------------+
|                                  SQLite Database (WAL Mode Enabled)                                     |
|                                                                                                         |
|  - rules: (rule_id PK, keyword, dm_message, created_at)                                                 |
|  - events: (event_id PRIMARY KEY, event_type, comment_id, post_id, user_id, text, sent_at, received_at) |
|  - deleted_comments: (comment_id PRIMARY KEY, deleted_at)                                               |
|  - processed_user_rules: (rule_id, user_id PRIMARY KEY, first_comment_id, processed_at)                 |
|  - duplicate_blocks: (id PK, rule_id, user_id, comment_id, blocked_at)                                  |
|  - jobs: (id PK, job_id UNIQUE, rule_id, user_id, comment_id, message, status, dm_id, retries, ...)     |
+---------------------------------------------------------------------------------------------------------+
                                                ^               ^
                                                |               |
                         +----------------------+               +----------------------+
                         | (Fetch runnable jobs)                                       | (Poll pending status)
                         v                                                             v
+-------------------------------------------------------------+  +----------------------------------------+
|                      DM Sender Worker                       |  |        Delivery Status Reconciler      |
|                                                             |  |                                        |
|  - Strict Rate Limiter: <= 10 reqs / 60s (Sliding Window)   |  |  - Polls GET /v1/dm/{dm_id}            |
|  - Pre-dispatch deleted comment check                       |  |  - Reads do NOT count against rate lim |
|  - POST /v1/dm/send with deterministic Idempotency-Key      |  |  - On 'delivered' -> mark sent         |
|  - 429 -> Parse Retry-After & pause worker                  |  |  - On 'failed' -> reschedule retry     |
|  - 500 -> Exponential backoff (2^n)                         |  |  - Max retries exceeded -> mark failed |
|  - 400 -> Mark terminal failed immediately                  |  +----------------------------------------+
+-------------------------------------------------------------+
```

---

## 2. Tech Stack

- **Language:** Python 3.11+
- **Web Framework:** [FastAPI](https://fastapi.tiangolo.com/) with [Uvicorn](https://www.uvicorn.org/) (Asynchronous, type-safe, sub-millisecond route latency)
- **Database:** SQLite with Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) and strict database constraints
- **HTTP Client:** [httpx](https://www.python-httpx.org/) (Async connection pooling)
- **Testing:** [pytest](https://pytest.org/), `pytest-asyncio`, `pytest-mock`
- **Deployment:** Docker & Render Web Service

---

## 3. Key Design Decisions & Strategies

### A. Non-Blocking Fast Webhook Ingestion (<5ms)
Webhooks must return HTTP 200 within 5 seconds. Our webhook handler:
1. Validates the raw HMAC-SHA256 signature in constant time (`hmac.compare_digest`).
2. Inserts the event atomically into the `events` table (`event_id` PRIMARY KEY).
3. Evaluates active keyword rules and queues DM dispatch jobs into the `jobs` table.
4. Returns HTTP 200 immediately with the ingested event details.

### B. Strict Rule + User Deduplication
The specification dictates: *"The same user never gets DMed twice for the same rule, no matter how many times they comment."*
- Uniqueness is tracked durably in `processed_user_rules` keyed on `(rule_id, user_id)`.
- If the user comments a second time, the database constraint raises an integrity error.
- The system catches the error, writes an audit record to `duplicate_blocks`, and skips job creation.
- `GET /stats` accurately counts blocked duplicates directly from the database ledger.

### C. Strict Rate Limiting (<= 10 Requests per Rolling 60s)
The upstream PseudoGram API enforces a hard quota of 10 mutating requests per rolling 60 seconds:
- Implemented as an asynchronous sliding-window token bucket in `app/rate_limiter.py`.
- Timestamps of recent requests are kept in a double-ended queue.
- If 10 requests were dispatched in the past 60s, the worker sleeps until the oldest timestamp exits the 60s window.
- Reads (`GET /v1/dm/{dm_id}`) do **not** count against the rate limit and are polled independently.

### D. Resilient Retry Strategy
- **HTTP 429 (Rate Limited):** Extracts the `Retry-After` header value, calls `api_rate_limiter.pause(retry_after + 1.0)`, and reschedules the job for `now + retry_after + 1.0`.
- **HTTP 500 / 502 / 503 / 504 (Server Errors):** Increments `retries` count and applies exponential backoff (`delay = min(60.0, 2 ** retries)`).
- **HTTP 400 (Invalid Request):** Identifies permanent client payload errors and marks the job as `failed` immediately without wasted retries.
- **Max Retries:** Capped at `MAX_RETRIES = 5` before marking the job as permanently `failed`.

### E. Delivery Reconciliation (Part C)
`POST /v1/dm/send` returns `HTTP 202 Accepted` (`status = 'queued'`). Approximately 15% of accepted DMs subsequently fail in the mock API's internal pipeline.
- The `_reconciliation_loop` queries `GET /v1/dm/{dm_id}`.
- If `status == 'delivered'`: job transitions to `status = 'delivered'` and is counted under `sent`.
- If `status == 'failed'`: job is automatically re-queued for sending with backoff.

### F. Sensible `comment.deleted` Handling (Part C)
- When a `comment.deleted` event is received, `comment_id` is registered in `deleted_comments`.
- Any existing `status = 'queued'` jobs for that comment are immediately updated to `cancelled_deleted`.
- If a deletion arrives before the creation event (out-of-order delivery), the subsequent `comment.created` event detects the deletion entry and skips job creation.

---

## 4. API Endpoints Contract

### `POST /rules`
Creates a new keyword rule.
- **Request:**
  ```json
  {
    "keyword": "PRICE",
    "dm_message": "Here's the price list: https://example.com/pricing"
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "rule_id": "rule_017d70a5bf4e",
    "keyword": "PRICE",
    "dm_message": "Here's the price list: https://example.com/pricing"
  }
  ```

### `POST /webhook`
Ingests comment events.
- **Header:** `X-PseudoGram-Signature: sha256=<hex_hmac>`
- **Request:**
  ```json
  {
    "event_id": "evt_01J8ZQ4K2N7RXA",
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
  ```
- **Response (200 OK):**
  ```json
  {
    "status": "received",
    "event_id": "evt_01J8ZQ4K2N7RXA",
    "result": {
      "status": "processed",
      "jobs_created": 1,
      "duplicates_blocked": 0
    }
  }
  ```

### `GET /stats`
Returns live system metrics calculated from the database.
- **Response (200 OK):**
  ```json
  {
    "sent": 142,
    "failed": 3,
    "queued": 8,
    "duplicates_blocked": 57
  }
  ```

### `GET /health`
Returns health check and timestamp for deployment monitoring.
- **Response (200 OK):**
  ```json
  {
    "status": "healthy",
    "service": "linkplease-automation",
    "timestamp": 1786905390.933
  }
  ```

---

## 5. Local Setup & Running

### Prerequisites
- Python 3.10+
- Git

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/karthikeyareddy07/linkplease-intern-assignment.git
   cd linkplease-intern-assignment
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment configuration:
   ```bash
   cp .env.example .env
   ```
   Add your `PSEUDOGRAM_API_KEY` into `.env`.

### Run the Server
```bash
uvicorn app.main:app --reload --port 8000
```
Interactive Swagger API docs will be available at `http://127.0.0.1:8000/docs`.

---

## 6. Running Tests

Run the complete automated test suite with pytest:
```bash
pytest -v
```

Run specific test suites:
```bash
# Test rule creation
pytest tests/test_rules.py -v

# Test webhook signature and deduplication
pytest tests/test_webhook.py -v

# Test user+rule deduplication
pytest tests/test_deduplication.py -v

# Test rate limiting
pytest tests/test_rate_limiter.py -v

# Test worker retry logic and reconciliation
pytest tests/test_worker.py -v
```

---

## 7. Load Simulation (500 Events / 10s)

### Run Local Simulation
```bash
python scripts/simulate.py
```

### Run Remote Simulation Against Deployed Render Service
```bash
python scripts/simulate.py --remote https://your-render-app.onrender.com <PSEUDOGRAM_API_KEY>
```

---

## 8. Deployment on Render

1. Push your repository to GitHub.
2. In Render, create a **New Web Service** connected to your repository.
3. Configuration:
   - **Environment:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
4. Set Environment Variables:
   - `PSEUDOGRAM_API_KEY`: Your PseudoGram API Key
   - `PSEUDOGRAM_BASE_URL`: `https://pseudogram-api.onrender.com`
   - `DATABASE_PATH`: `linkplease.db`
