"""Idempotency: sending the same create request twice (same Idempotency-Key) creates it only once.

The first answer is saved with the key. A repeat returns that saved answer. Reusing a key for a
DIFFERENT request is a mistake by the caller and gets 409.
"""

import hashlib
import json
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import IdempotencyRecord
from app.errors import ApiError


def fingerprint(method: str, path: str, body: dict) -> str:
    """A short code that is the same only for exactly the same request."""
    text = method + " " + path + " " + json.dumps(body, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def saved_answer(
    session: Session, user_id: str, key: str, request_fingerprint: str
) -> tuple[int, dict] | None:
    record = session.get(IdempotencyRecord, (user_id, key))
    if record is None:
        return None
    if record.request_fingerprint != request_fingerprint:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was already used for another request"
        )
    return record.status_code, record.response_body


def create_once(
    session: Session,
    user_id: str,
    key: str | None,
    request_fingerprint: str,
    create: Callable[[], tuple[int, dict]],
) -> tuple[int, dict]:
    """Run `create` and commit, unless this key was already answered. Returns (status code, body)."""
    if key:
        answer = saved_answer(session, user_id, key, request_fingerprint)
        if answer:
            return answer

    status_code, body = create()
    if key:
        session.add(
            IdempotencyRecord(
                user_id=user_id,
                key=key,
                request_fingerprint=request_fingerprint,
                status_code=status_code,
                response_body=body,
            )
        )
    try:
        session.commit()
    except IntegrityError:
        # Two identical requests arrived at the same moment and the other one won: return its answer.
        session.rollback()
        answer = saved_answer(session, user_id, key, request_fingerprint) if key else None
        if answer:
            return answer
        raise ApiError(409, "CONFLICT", "This was created at the same moment by another request") from None
    return status_code, body
