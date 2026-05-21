from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from mail_assistant.store.db import Database
from mail_assistant.store.models import StoredMessage


def row_to_message(row: Any) -> StoredMessage:
    return StoredMessage(
        id=row["id"],
        thread_id=row["thread_id"],
        history_id=row["history_id"],
        from_addr=row["from_addr"],
        from_name=row["from_name"],
        to_addrs=json.loads(row["to_addrs"]),
        cc_addrs=json.loads(row["cc_addrs"]),
        subject=row["subject"],
        date=datetime.fromisoformat(row["date"]),
        snippet=row["snippet"],
        labels=json.loads(row["labels"]),
        is_unread=bool(row["is_unread"]),
        is_sent=bool(row["is_sent"]),
        body_text=row["body_text"],
        fetched_body_at=datetime.fromisoformat(row["fetched_body_at"])
        if row["fetched_body_at"]
        else None,
    )


def upsert_messages(db: Database, messages: Iterable[StoredMessage]) -> int:
    rows = [
        (
            m.id,
            m.thread_id,
            m.history_id,
            m.from_addr,
            m.from_name,
            json.dumps(m.to_addrs),
            json.dumps(m.cc_addrs),
            m.subject,
            m.date.isoformat(),
            m.snippet,
            json.dumps(m.labels),
            int(m.is_unread),
            int(m.is_sent),
            m.body_text,
            m.fetched_body_at.isoformat() if m.fetched_body_at else None,
        )
        for m in messages
    ]
    if not rows:
        return 0
    with db.transaction() as c:
        c.executemany(
            """
            INSERT INTO messages (
                id, thread_id, history_id, from_addr, from_name, to_addrs, cc_addrs,
                subject, date, snippet, labels, is_unread, is_sent, body_text, fetched_body_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                thread_id        = excluded.thread_id,
                history_id       = excluded.history_id,
                from_addr        = excluded.from_addr,
                from_name        = excluded.from_name,
                to_addrs         = excluded.to_addrs,
                cc_addrs         = excluded.cc_addrs,
                subject          = excluded.subject,
                date             = excluded.date,
                snippet          = excluded.snippet,
                labels           = excluded.labels,
                is_unread        = excluded.is_unread,
                is_sent          = excluded.is_sent,
                body_text        = COALESCE(excluded.body_text, messages.body_text),
                fetched_body_at  = COALESCE(excluded.fetched_body_at, messages.fetched_body_at)
            """,
            rows,
        )
    return len(rows)


_THREAD_SUMMARY_SQL = """
    INSERT INTO threads (id, subject, snippet, last_message_at, message_count)
    SELECT
        ?,
        COALESCE((SELECT subject FROM messages
                  WHERE thread_id = ? ORDER BY date DESC LIMIT 1), ''),
        COALESCE((SELECT snippet FROM messages
                  WHERE thread_id = ? ORDER BY date DESC LIMIT 1), ''),
        COALESCE((SELECT date FROM messages
                  WHERE thread_id = ? ORDER BY date DESC LIMIT 1), ''),
        (SELECT COUNT(*) FROM messages WHERE thread_id = ?)
    ON CONFLICT(id) DO UPDATE SET
        subject = excluded.subject,
        snippet = excluded.snippet,
        last_message_at = excluded.last_message_at,
        message_count = excluded.message_count
"""


def upsert_thread_summary(db: Database, thread_id: str) -> None:
    """Recompute the threads row from its messages. Called after upserts."""
    with db.transaction() as c:
        c.execute(_THREAD_SUMMARY_SQL, (thread_id,) * 5)


def delete_messages(db: Database, message_ids: Iterable[str]) -> int:
    ids = list(message_ids)
    if not ids:
        return 0
    with db.transaction() as c:
        cur = c.executemany("DELETE FROM messages WHERE id = ?", [(i,) for i in ids])
    return cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else len(ids)


def get_message(db: Database, message_id: str) -> StoredMessage | None:
    row = db.conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    return row_to_message(row) if row else None


def list_unread(db: Database, limit: int = 100) -> list[StoredMessage]:
    rows = db.conn.execute(
        "SELECT * FROM messages WHERE is_unread = 1 ORDER BY date DESC LIMIT ?", (limit,)
    ).fetchall()
    return [row_to_message(r) for r in rows]


def list_recent(db: Database, limit: int = 50) -> list[StoredMessage]:
    rows = db.conn.execute("SELECT * FROM messages ORDER BY date DESC LIMIT ?", (limit,)).fetchall()
    return [row_to_message(r) for r in rows]


def count_messages(db: Database) -> int:
    row = db.conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()
    return int(row["c"])


def set_body(db: Database, message_id: str, body_text: str, fetched_at: datetime) -> None:
    with db.transaction() as c:
        c.execute(
            "UPDATE messages SET body_text = ?, fetched_body_at = ? WHERE id = ?",
            (body_text, fetched_at.isoformat(), message_id),
        )
