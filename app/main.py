"""FastAPI Application Entry Point."""
import os
import hmac
import hashlib
import json
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import db
from app.models import RuleCreateRequest, RuleResponse, StatsResponse, HealthResponse
from app.worker import worker


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables and start worker
    await db.init_db()
    await worker.start()
    yield
    # Shutdown: stop worker gracefully
    await worker.stop()


app = FastAPI(
    title="LinkPlease Instagram Automation API",
    description="High-reliability comment-to-DM automation engine for Instagram creators",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files if directory exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def verify_signature(raw_body: bytes, signature_header: str | None, api_key: str) -> bool:
    """Verify HMAC-SHA256 webhook signature using constant-time comparison."""
    if not signature_header or not api_key:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    expected_hex = signature_header[len(prefix):]
    computed_hex = hmac.new(
        key=api_key.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_hex, computed_hex)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for deployment monitoring."""
    return HealthResponse(
        status="healthy",
        service="linkplease-automation",
        timestamp=time.time()
    )


@app.get("/")
async def root(request: Request):
    """
    Root endpoint:
    - Serves the modern LinkPlease Dashboard UI for browsers.
    - Serves JSON HealthResponse for programmatic/API clients.
    """
    accept = request.headers.get("accept", "")
    index_file = STATIC_DIR / "index.html"
    
    if "text/html" in accept and index_file.exists():
        return FileResponse(str(index_file))
    elif not ("application/json" in accept) and index_file.exists():
        return FileResponse(str(index_file))
    
    return HealthResponse(
        status="healthy",
        service="linkplease-automation",
        timestamp=time.time()
    )


@app.get("/app", response_class=FileResponse)
@app.get("/dashboard", response_class=FileResponse)
async def dashboard_view():
    """Direct route to the LinkPlease SaaS Dashboard."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse("<h1>LinkPlease Dashboard</h1><p>Static assets loading...</p>")


@app.post("/rules", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(payload: RuleCreateRequest):
    """
    Create a new keyword-triggered automation rule.
    Returns HTTP 201 with rule details.
    """
    keyword = payload.keyword.strip()
    dm_message = payload.dm_message.strip()

    if not keyword or not dm_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="keyword and dm_message cannot be empty"
        )

    rule = await db.create_rule(keyword=keyword, dm_message=dm_message)
    return RuleResponse(
        rule_id=rule["rule_id"],
        keyword=rule["keyword"],
        dm_message=rule["dm_message"]
    )


@app.get("/rules")
async def list_rules():
    """List all configured rules."""
    rules = await db.get_all_rules()
    return rules


@app.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a rule from the dashboard."""
    success = await db.delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return {"status": "deleted", "rule_id": rule_id}


@app.post("/webhook", status_code=status.HTTP_200_OK)
async def handle_webhook(request: Request):
    """
    Webhook endpoint to ingest Instagram comment events.
    - Fast response (<5 seconds contract, typically <5ms).
    - Signature verification for security.
    - Asynchronous queuing of all matching rules and DM jobs.
    """
    raw_body = await request.body()
    signature_header = request.headers.get("X-PseudoGram-Signature")

    # Verify signature if provided or strictly required
    if signature_header:
        if not verify_signature(raw_body, signature_header, settings.pseudogram_api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
            )
    elif settings.require_webhook_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-PseudoGram-Signature header"
        )

    try:
        event_dict = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    # Ingest event atomically into database
    result = await db.process_webhook_event(event_dict)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "received",
            "event_id": event_dict.get("event_id"),
            "result": result
        }
    )


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get live automation stats directly from durable database state.
    Returns:
    {
        "sent": <confirmed delivered DMs>,
        "failed": <permanently failed DMs>,
        "queued": <jobs waiting to send or waiting on reconciliation>,
        "duplicates_blocked": <duplicate user+rule events prevented>
    }
    """
    stats = await db.get_stats()
    return StatsResponse(**stats)


@app.get("/api/comments")
async def get_comments():
    """Get real-time comments feed from database."""
    comments = await db.get_comments_feed(limit=50)
    return {"comments": comments}


@app.get("/api/activity")
async def get_activity():
    """Get chronological activity audit log."""
    activity = await db.get_recent_activity(limit=40)
    return {"activity": activity}


@app.get("/api/conversations")
async def get_conversations():
    """Get conversation threads grouped by user."""
    convos = await db.get_conversations(limit=50)
    return {"conversations": convos}


@app.post("/api/simulate-test")
async def simulate_test_comment(request: Request):
    """
    Simulate a live comment webhook locally to test rules in real-time.
    """
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    keyword = body.get("keyword", "PRICE")
    username = body.get("username", "creator.fan")
    user_id = body.get("user_id", f"usr_{uuid.uuid4().hex[:6]}")
    text = body.get("text", f"Can I get the {keyword} please? 🙏")

    mock_event = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": "comment.created",
        "sent_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "data": {
            "comment_id": f"cmt_{uuid.uuid4().hex[:8]}",
            "post_id": f"post_{uuid.uuid4().hex[:6]}",
            "text": text,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "from": {
                "user_id": user_id,
                "username": username
            }
        }
    }

    result = await db.process_webhook_event(mock_event)
    return {"status": "simulated", "event": mock_event, "result": result}

