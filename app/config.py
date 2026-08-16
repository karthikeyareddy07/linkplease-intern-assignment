"""Application Configuration."""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    pseudogram_api_key: str = Field(
        default="",
        alias="PSEUDOGRAM_API_KEY",
        description="API key for PseudoGram Mock API"
    )
    pseudogram_base_url: str = Field(
        default="https://pseudogram-api.onrender.com",
        alias="PSEUDOGRAM_BASE_URL",
        description="Base URL for PseudoGram Mock API"
    )
    database_path: str = Field(
        default="linkplease.db",
        alias="DATABASE_PATH",
        description="Path to SQLite database file"
    )
    database_url: str = Field(
        default="",
        alias="DATABASE_URL",
        description="Optional full Database URL (e.g. Postgres on Render)"
    )
    port: int = Field(
        default=8000,
        alias="PORT",
        description="Port to listen on"
    )
    worker_poll_interval_seconds: float = Field(
        default=0.25,
        alias="WORKER_POLL_INTERVAL_SECONDS",
        description="Poll interval for background job queue"
    )
    reconciliation_interval_seconds: float = Field(
        default=1.0,
        alias="RECONCILIATION_INTERVAL_SECONDS",
        description="Poll interval for delivery status reconciliation"
    )
    max_retries: int = Field(
        default=5,
        alias="MAX_RETRIES",
        description="Maximum retry attempts for transient failures"
    )
    rate_limit_requests: int = Field(
        default=10,
        alias="RATE_LIMIT_REQUESTS",
        description="Allowed mutating requests per window"
    )
    rate_limit_window_seconds: float = Field(
        default=60.0,
        alias="RATE_LIMIT_WINDOW_SECONDS",
        description="Rolling window in seconds for rate limiter"
    )
    require_webhook_signature: bool = Field(
        default=False,
        alias="REQUIRE_WEBHOOK_SIGNATURE",
        description="Whether to reject webhook requests missing signature header"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


settings = Settings()
