"""POST /api/subscriptions and DELETE /api/subscriptions/{token}."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from gct.database import get_db
from gct.models import Subscription
from gct.schemas.api import SubscriptionRequest, SubscriptionResponse, UnsubscribeResponse

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# ── In-memory rate limiter ────────────────────────────────────────────────────
# Simple token bucket: tracks timestamps of recent requests per IP.
# Replace with Redis (e.g. using `limits` library) in production.
_RATE_LIMIT_WINDOW_SECONDS = 3600  # 1 hour
_RATE_LIMIT_MAX = 5  # 5 requests per IP per hour
_ip_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    """Raise HTTP 429 if the IP has exceeded the subscription rate limit."""
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    timestamps = [t for t in _ip_timestamps[ip] if t > cutoff]
    _ip_timestamps[ip] = timestamps
    if len(timestamps) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: max {_RATE_LIMIT_MAX} subscription requests "
                f"per hour per IP. Try again later."
            ),
        )
    _ip_timestamps[ip].append(now)


@router.post(
    "",
    response_model=SubscriptionResponse,
    summary="Email digest signup",
    status_code=200,
)
def create_subscription(
    body: SubscriptionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    """Subscribe an email address to the going-concern digest.

    - Validates email format (RFC 5322).
    - Idempotent: returns ``already_subscribed=true`` for existing emails.
    - Creates a Subscription row with ``confirmed=false``.
    - Does NOT send a confirmation email (wired up in Prompt 8 / Phase 2).
    - Rate-limited: 5 requests per IP per hour.
    """
    # Validate email format using Pydantic EmailStr
    from pydantic import validate_email as _validate_email
    try:
        _, normalized_email = _validate_email(body.email)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid email address")

    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    existing = db.execute(
        select(Subscription).where(Subscription.email == normalized_email)
    ).scalar_one_or_none()

    if existing is not None:
        return SubscriptionResponse(
            ok=True,
            message="You are already subscribed.",
            subscription_id=existing.id,
            already_subscribed=True,
        )

    sub = Subscription(
        id=uuid.uuid4(),
        email=normalized_email,
        confirmed=False,
        confirmation_token=str(uuid.uuid4()),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    return SubscriptionResponse(
        ok=True,
        message="Check your inbox to confirm your subscription.",
        subscription_id=sub.id,
        already_subscribed=False,
    )


@router.delete(
    "/{token}",
    response_model=UnsubscribeResponse,
    summary="Unsubscribe via confirmation token",
)
def unsubscribe(
    token: str,
    db: Session = Depends(get_db),
) -> UnsubscribeResponse:
    """Unsubscribe using the token from the confirmation/unsubscribe email."""
    from datetime import datetime

    sub = db.execute(
        select(Subscription).where(Subscription.confirmation_token == token)
    ).scalar_one_or_none()

    if sub is None:
        raise HTTPException(status_code=404, detail="Unsubscribe token not found or already used")

    sub.unsubscribed_at = datetime.utcnow()
    db.commit()

    return UnsubscribeResponse(ok=True, message="You have been unsubscribed successfully.")
