"""FastAPI Application Entry Point."""
import hmac
import hashlib
import json
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import db
from app.models import RuleCreateRequest, RuleResponse, StatsResponse, HealthResponse
from app.worker import worker


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


@app.get("/", response_model=HealthResponse)
async def root():
    """Root status endpoint."""
    return HealthResponse(
        status="healthy",
        service="linkplease-automation",
        timestamp=time.time()
    )


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
