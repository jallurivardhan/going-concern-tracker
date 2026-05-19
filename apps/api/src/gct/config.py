from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_dotenv() -> str:
    """Walk up from this file's directory to find the nearest .env file."""
    current = Path(__file__).resolve().parent
    for _ in range(8):
        candidate = current / ".env"
        if candidate.exists():
            return str(candidate)
        current = current.parent
    return ".env"  # fallback: let pydantic-settings look in cwd


class Settings(BaseSettings):
    """Application settings loaded from environment variables (and .env file)."""

    model_config = SettingsConfigDict(
        env_file=_find_dotenv(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────────────
    # Neon Postgres connection string; must include sslmode=require.
    database_url: str = Field(..., description="Neon Postgres connection string")

    # ── LLM (Tier 2) ────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(..., description="Anthropic API key")

    # ── Langfuse observability ───────────────────────────────────────────────
    langfuse_public_key: str = Field(..., description="Langfuse public key")
    langfuse_secret_key: str = Field(..., description="Langfuse secret key")
    # Reads from LANGFUSE_HOST or LANGFUSE_BASE_URL (the latter is the default
    # name used by Langfuse's own .env templates — we support both).
    langfuse_host: str = Field(
        default="https://us.cloud.langfuse.com",
        validation_alias=AliasChoices("langfuse_host", "langfuse_base_url"),
        description="Langfuse host URL",
    )

    # ── SEC EDGAR ingestion (Tier 1) ────────────────────────────────────────
    # Required by SEC fair-access policy: format "Company Name email@example.com"
    sec_user_agent_email: str = Field(
        ..., description="Contact email for SEC EDGAR User-Agent header"
    )
    # SEC publishes a 10 requests/second fair-use cap; stay at or below this.
    sec_rate_limit_rps: int = Field(
        default=10, description="Max requests per second to SEC EDGAR"
    )
    ingestion_data_dir: str = Field(
        default="./data/raw_filings",
        description="Directory for storing raw filing HTML files",
    )

    # ── Classifier (Tier 2) ──────────────────────────────────────────────────
    classifier_primary_model: str = Field(
        default="claude-haiku-4-5",
        description="Default Claude model for bulk classification",
    )
    classifier_fallback_model: str = Field(
        default="claude-sonnet-4-5",
        description="Higher-capability model used when primary reports low confidence",
    )
    classifier_confidence_threshold: float = Field(
        default=0.7,
        description="Below this confidence the classifier escalates to the fallback model",
    )
    classifier_max_retries: int = Field(
        default=3,
        description="Max Instructor retries on Pydantic validation failure",
    )

    # ── Application ──────────────────────────────────────────────────────────
    env: str = Field(default="development", description="Deployment environment")
    log_level: str = Field(default="INFO", description="Log level")

    # ── Frontend / CORS ───────────────────────────────────────────────────────
    # Override in production with the real Vercel/Netlify URL.
    frontend_url: str = Field(
        default="http://localhost:3000",
        description="Allowed frontend origin for CORS (override in production)",
    )

    # ── Subscriptions ─────────────────────────────────────────────────────────
    subscription_rate_limit_per_hour: int = Field(
        default=5,
        description="Max subscription POST requests per IP per hour (enforced in-memory; use Redis in production)",
    )


# Module-level singleton — imported by other modules
settings = Settings()  # type: ignore[call-arg]
