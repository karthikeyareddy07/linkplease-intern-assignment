"""Pydantic Models and Data Contracts."""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class RuleCreateRequest(BaseModel):
    keyword: str = Field(..., min_length=1, description="Keyword to match in comments")
    dm_message: str = Field(..., min_length=1, description="DM message to send when rule matches")


class RuleResponse(BaseModel):
    rule_id: str
    keyword: str
    dm_message: str


class CommentFrom(BaseModel):
    user_id: str
    username: Optional[str] = None


class CommentData(BaseModel):
    comment_id: str
    post_id: Optional[str] = None
    text: Optional[str] = None
    created_at: Optional[str] = None
    from_: Optional[CommentFrom] = Field(None, alias="from")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class WebhookPayload(BaseModel):
    event_id: str
    event_type: str = Field(..., description="Event type, e.g. comment.created or comment.deleted")
    sent_at: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "extra": "ignore"
    }


class StatsResponse(BaseModel):
    sent: int = Field(..., description="DMs confirmed as delivered by mock API")
    failed: int = Field(..., description="DMs given up after max retries")
    queued: int = Field(..., description="DMs currently waiting to send or waiting on retry")
    duplicates_blocked: int = Field(..., description="DMs correctly chosen not to send")


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: float
