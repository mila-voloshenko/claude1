from __future__ import annotations

from datetime import datetime

from mail_assistant.store.db import Database
from mail_assistant.store.models import SearchHit


def search(db: Database, query: str, limit: int = 25) -> list[SearchHit]:
    """FTS5 search against subject/snippet/from/body. `query` uses FTS5 syntax."""
    rows = db.conn.execute(
        """
        SELECT m.id, m.thread_id, m.subject, m.snippet, m.from_addr, m.from_name, m.date
        FROM messages_fts f
        JOIN messages m ON m.rowid = f.rowid
        WHERE messages_fts MATCH ?
        ORDER BY m.date DESC
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()
    return [
        SearchHit(
            message_id=r["id"],
            thread_id=r["thread_id"],
            subject=r["subject"],
            snippet=r["snippet"],
            from_addr=r["from_addr"],
            from_name=r["from_name"],
            date=datetime.fromisoformat(r["date"]),
        )
        for r in rows
    ]
