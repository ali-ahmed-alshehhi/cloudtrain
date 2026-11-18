"""Idempotency: sending the same create request twice (same Idempotency-Key) creates it only once.

The first answer is saved with the key. A repeat returns that saved answer. Reusing a key for a
DIFFERENT request is a mistake by the caller and gets 409.
"""

import hashlib
import json

from sqlalchemy.orm import Session

from app.common import ApiError
from app.db import IdempotencyRecord


def fingerprint(method: str, path: str, body: dict) -> str:
    """A short code that is the same only for exactly the same request."""
    text = method + " " + path + " " + json.dumps(body, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def saved_answer(session: Session, user_id: str, key: str, request_fingerprint: str) -> dict | None:
    record = session.get(IdempotencyRecord, (user_id, key))
    if record is None:
        return None
    if record.request_fingerprint != request_fingerprint:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was already used for another request"
        )
    return record.response_body


def remember(session: Session, user_id: str, key: str, request_fingerprint: str, body: dict) -> None:
    """Save the answer in the same transaction as the work, so both are kept or neither is."""
    session.add(
        IdempotencyRecord(
            user_id=user_id,
            key=key,
            request_fingerprint=request_fingerprint,
            status_code=201,
            response_body=body,
        )
    )
