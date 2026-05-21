from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from mail_assistant.analysis.categories import Category, Classification
from mail_assistant.store.db import Database
from mail_assistant.store.messages import row_to_message
from mail_assistant.store.models import StoredMessage


@dataclass(frozen=True)
class StoredClassification:
    message_id: str
    category: Category
    confidence: float
    reason: str
    classified_at: datetime
    model: str


def upsert(db: Database, message_id: str, classification: Classification, model: str) -> None:
    with db.transaction() as c:
        c.execute(
            """
            INSERT INTO message_classifications
                (message_id, category, confidence, reason, classified_at, model)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                category = excluded.category,
                confidence = excluded.confidence,
                reason = excluded.reason,
                classified_at = excluded.classified_at,
                model = excluded.model
            """,
            (
                message_id,
                classification.category.value,
                classification.confidence,
                classification.reason,
                datetime.now(UTC).isoformat(),
                model,
            ),
        )


def get(db: Database, message_id: str) -> StoredClassification | None:
    row = db.conn.execute(
        "SELECT * FROM message_classifications WHERE message_id = ?", (message_id,)
    ).fetchone()
    if row is None:
        return None
    return StoredClassification(
        message_id=row["message_id"],
        category=Category(row["category"]),
        confidence=float(row["confidence"]),
        reason=row["reason"],
        classified_at=datetime.fromisoformat(row["classified_at"]),
        model=row["model"],
    )


def list_unclassified(db: Database, limit: int = 100) -> list[StoredMessage]:
    rows = db.conn.execute(
        """
        SELECT m.* FROM messages m
        LEFT JOIN message_classifications c ON c.message_id = m.id
        WHERE c.message_id IS NULL
        ORDER BY m.date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [row_to_message(r) for r in rows]


def list_by_category(
    db: Database, category: Category, limit: int = 50
) -> list[tuple[StoredMessage, StoredClassification]]:
    rows = db.conn.execute(
        """
        SELECT m.*,
               c.category AS c_category, c.confidence AS c_confidence,
               c.reason AS c_reason, c.classified_at AS c_classified_at,
               c.model AS c_model
        FROM messages m
        JOIN message_classifications c ON c.message_id = m.id
        WHERE c.category = ?
        ORDER BY m.date DESC
        LIMIT ?
        """,
        (category.value, limit),
    ).fetchall()
    out: list[tuple[StoredMessage, StoredClassification]] = []
    for r in rows:
        msg = row_to_message(r)
        clf = StoredClassification(
            message_id=r["id"],
            category=Category(r["c_category"]),
            confidence=float(r["c_confidence"]),
            reason=r["c_reason"],
            classified_at=datetime.fromisoformat(r["c_classified_at"]),
            model=r["c_model"],
        )
        out.append((msg, clf))
    return out


def count_by_category(db: Database) -> dict[Category, int]:
    rows = db.conn.execute(
        "SELECT category, COUNT(*) AS n FROM message_classifications GROUP BY category"
    ).fetchall()
    return {Category(r["category"]): int(r["n"]) for r in rows}
