"""Mobile banking entry ticket (app ticket): the customer is already signed in to the bank app; when
they tap "AI wealth assistant",
the bank's back end issues a short-lived, one-time ticket; WealthPilot verifies it and creates its
own session, with no second password.

Format: base64url(payload JSON) + "." + base64url(HMAC-SHA256 signature)
Payload: iss issuer, aud audience, sub customer ID, iat / exp issued and expiry times, jti unique
ID, locale UI language

Checks: signature (constant-time comparison), issuer, audience, expiry (10 s clock skew allowed),
one-time use (jti stored in the database,
so reuse is rejected, across multiple instances too).

The demo uses a shared HMAC key; in production the bank usually signs with a private key (e.g. an
RS256 / ES256 JWT)
and WealthPilot holds only the public key, so even a compromised WealthPilot can't forge tickets.
"""

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import UsedAppTicket

ISSUER = "zhian-bank-app"
AUDIENCE = "wealthpilot"
CLOCK_SKEW = timedelta(seconds=10)


class TicketError(ValueError):
    """Invalid ticket. The reason goes only to the log; the frontend gets no details (to avoid
    helping attackers debug)."""


@dataclass(frozen=True)
class AppTicket:
    customer_id: str
    jti: str
    expires_at: datetime
    locale: str


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes) -> str:
    key = get_settings().app_ticket_secret.get_secret_value().encode()
    return _b64(hmac.new(key, payload, hashlib.sha256).digest())


def issue(customer_id: str, now: datetime, locale: str = "zh") -> str:
    """Issue a ticket. In production the bank's back end does this; here it serves the simulated
    bank (app/bank_sim) and tests."""
    ttl = get_settings().app_ticket_ttl_seconds
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": customer_id,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + ttl,
        "jti": secrets.token_hex(16),
        "locale": locale if locale in ("zh", "en") else "zh",
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"{_b64(body)}.{_sign(body)}"


def verify(token: str, now: datetime) -> AppTicket:
    try:
        body_part, signature = token.split(".")
        body = _unb64(body_part)
    except (ValueError, TypeError) as exc:
        raise TicketError("malformed") from exc
    if not hmac.compare_digest(signature, _sign(body)):
        raise TicketError("bad signature")
    try:
        payload = json.loads(body)
        issued = datetime.fromtimestamp(int(payload["iat"]), now.tzinfo)
        expires = datetime.fromtimestamp(int(payload["exp"]), now.tzinfo)
        ticket = AppTicket(
            customer_id=str(payload["sub"]),
            jti=str(payload["jti"]),
            expires_at=expires,
            locale=payload.get("locale", "zh"),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise TicketError("bad payload") from exc
    if payload.get("iss") != ISSUER or payload.get("aud") != AUDIENCE:
        raise TicketError("wrong issuer or audience")
    if now > expires + CLOCK_SKEW or issued > now + CLOCK_SKEW:
        raise TicketError("expired or not yet valid")
    return ticket


def consume(db: Session, ticket: AppTicket, now: datetime) -> None:
    """Mark the ticket as used; a second use of the same ticket hits a primary-key conflict and
    counts as a replay."""
    db.add(UsedAppTicket(jti=ticket.jti, used_at=now, expires_at=ticket.expires_at))
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise TicketError("replayed") from exc
