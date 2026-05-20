from __future__ import annotations

from datetime import UTC, datetime

from mail_assistant.store.db import Database
from mail_assistant.store.models import SyncState


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def get(db: Database) -> SyncState:
    row = db.conn.execute("SELECT * FROM sync_state WHERE id = 1").fetchone()
    if row is None:
        return SyncState(None, None, None, None)
    return SyncState(
        account_email=row["account_email"],
        last_history_id=row["last_history_id"],
        last_full_sync_at=_parse_dt(row["last_full_sync_at"]),
        last_incremental_sync_at=_parse_dt(row["last_incremental_sync_at"]),
    )


def set_after_full_sync(db: Database, account_email: str, history_id: str) -> None:
    now = datetime.now(UTC).isoformat()
    with db.transaction() as c:
        c.execute(
            """
            UPDATE sync_state
            SET account_email = ?, last_history_id = ?, last_full_sync_at = ?
            WHERE id = 1
            """,
            (account_email, history_id, now),
        )


def set_after_incremental_sync(db: Database, history_id: str) -> None:
    now = datetime.now(UTC).isoformat()
    with db.transaction() as c:
        c.execute(
            """
            UPDATE sync_state
            SET last_history_id = ?, last_incremental_sync_at = ?
            WHERE id = 1
            """,
            (history_id, now),
        )
