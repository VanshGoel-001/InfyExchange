"""Idempotency keys: a retried write answers with the first result instead of doing the work twice.

The SPA sends an `Idempotency-Key` header with the four writes that create something (a listing, a need,
an enquiry, a chat message). `begin` claims the key inside the request's own transaction and `finish`
records what was created before the commit, so the key and the result are saved together or not at all.
A request that fails therefore frees its key and a retry really runs. A request without the header
behaves exactly as before.

On PostgreSQL a duplicate that arrives while the first is still running waits on the unique index, then
finds the saved result. The "still processing" answer covers the listing upload, which commits twice.
"""

import re
from datetime import datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.idempotency_key import IdempotencyKey
from app.models.user import User

HEADER = "Idempotency-Key"

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

# A claim with no result after this long belongs to a request that died; the next attempt takes it over.
PENDING_SECONDS = 120


class Idempotency:
    """`replay_id` is set when this key already produced a result: return that instead of creating again."""

    def __init__(
        self,
        db: Session,
        record: IdempotencyKey | None = None,
        replay_id: int | None = None,
    ):
        self._db = db
        self._record = record
        self.replay_id = replay_id

    def finish(self, resource_id: int) -> None:
        """Save what was created. Call it before the commit that saves the work."""
        if self._record is not None:
            self._record.resource_id = resource_id

    def release(self) -> None:
        """Forget the key, because the work was undone and a retry has to be able to run."""
        if self._record is not None:
            self._db.delete(self._record)
            self._record = None


def already_done() -> HTTPException:
    """For a replay whose result has since been removed."""
    return HTTPException(
        status_code=409,
        detail="This was already submitted and has since been removed.",
    )


def _still_running() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail="Your earlier attempt is still being processed. Wait a moment, then try again.",
    )


def begin(db: Session, request: Request, user: User, scope: str) -> Idempotency:
    key = request.headers.get(HEADER)

    if not key:
        return Idempotency(db)

    if not _KEY_PATTERN.fullmatch(key):
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must be 16 to 64 letters, digits, - or _.",
        )

    # Twice: if a simultaneous request claims the key first, the second pass finds its row.
    for _ in range(2):
        now = datetime.utcnow()

        row = db.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user.id,
                IdempotencyKey.key == key,
            )
        )

        if row is not None:
            if row.created_at <= now - timedelta(hours=settings.idempotency_key_hours):
                db.delete(row)
                db.flush()
            elif row.scope != scope:
                raise HTTPException(
                    status_code=422,
                    detail="This Idempotency-Key was already used for a different request.",
                )
            elif row.resource_id is not None:
                return Idempotency(db, replay_id=row.resource_id)
            elif row.created_at > now - timedelta(seconds=PENDING_SECONDS):
                raise _still_running()
            else:
                db.delete(row)
                db.flush()

        record = IdempotencyKey(
            user_id=user.id,
            key=key,
            scope=scope,
            created_at=now,
        )
        db.add(record)

        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            continue

        return Idempotency(db, record)

    raise _still_running()
