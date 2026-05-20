from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mail_assistant.store import messages as messages_repo
from mail_assistant.store import search as search_repo
from mail_assistant.store import sync_state
from mail_assistant.store.db import Database
from mail_assistant.store.migrations import apply_migrations
from mail_assistant.store.models import StoredMessage


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "test.db")
    apply_migrations(d)
    return d


def _make_message(
    mid: str,
    *,
    thread_id: str = "t1",
    subject: str = "Hello",
    body: str | None = None,
    is_unread: bool = True,
    is_sent: bool = False,
    date: datetime | None = None,
    from_addr: str = "alice@example.com",
    from_name: str = "Alice",
    labels: list[str] | None = None,
) -> StoredMessage:
    return StoredMessage(
        id=mid,
        thread_id=thread_id,
        history_id="100",
        from_addr=from_addr,
        from_name=from_name,
        to_addrs=["bob@example.com"],
        cc_addrs=[],
        subject=subject,
        date=date or datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        snippet="snippet",
        labels=labels or ["INBOX", "UNREAD"],
        is_unread=is_unread,
        is_sent=is_sent,
        body_text=body,
    )


# ---------- migrations ----------


def test_migrations_apply_once(tmp_path: Path) -> None:
    d = Database(tmp_path / "m.db")
    applied = apply_migrations(d)
    assert applied == [1]


def test_migrations_idempotent(tmp_path: Path) -> None:
    d = Database(tmp_path / "m.db")
    apply_migrations(d)
    again = apply_migrations(d)
    assert again == []


def test_migrations_create_expected_tables(db: Database) -> None:
    rows = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert {"threads", "messages", "sync_state", "_migrations"} <= names
    assert "messages_fts" in names


# ---------- messages repo ----------


def test_upsert_and_get(db: Database) -> None:
    m = _make_message("m1")
    messages_repo.upsert_messages(db, [m])
    got = messages_repo.get_message(db, "m1")
    assert got is not None
    assert got.subject == "Hello"
    assert got.is_unread is True
    assert got.to_addrs == ["bob@example.com"]


def test_upsert_updates_existing(db: Database) -> None:
    messages_repo.upsert_messages(db, [_make_message("m1", subject="A")])
    messages_repo.upsert_messages(db, [_make_message("m1", subject="B")])
    got = messages_repo.get_message(db, "m1")
    assert got is not None and got.subject == "B"


def test_upsert_preserves_existing_body_when_new_is_none(db: Database) -> None:
    """A metadata-only upsert should NOT wipe a previously-fetched body."""
    messages_repo.upsert_messages(db, [_make_message("m1", body="full body text")])
    messages_repo.upsert_messages(db, [_make_message("m1", subject="updated", body=None)])
    got = messages_repo.get_message(db, "m1")
    assert got is not None
    assert got.subject == "updated"
    assert got.body_text == "full body text"


def test_list_unread(db: Database) -> None:
    messages_repo.upsert_messages(
        db,
        [
            _make_message("m1", is_unread=True),
            _make_message("m2", is_unread=False),
            _make_message("m3", is_unread=True),
        ],
    )
    unread = messages_repo.list_unread(db)
    assert {m.id for m in unread} == {"m1", "m3"}


def test_delete_messages(db: Database) -> None:
    messages_repo.upsert_messages(db, [_make_message("m1"), _make_message("m2")])
    n = messages_repo.delete_messages(db, ["m1"])
    assert n == 1
    assert messages_repo.get_message(db, "m1") is None
    assert messages_repo.get_message(db, "m2") is not None


def test_thread_summary(db: Database) -> None:
    messages_repo.upsert_messages(
        db,
        [
            _make_message(
                "m1", thread_id="t1", subject="First", date=datetime(2026, 5, 1, tzinfo=UTC)
            ),
            _make_message(
                "m2", thread_id="t1", subject="Latest", date=datetime(2026, 5, 20, tzinfo=UTC)
            ),
        ],
    )
    messages_repo.upsert_thread_summary(db, "t1")
    row = db.conn.execute("SELECT * FROM threads WHERE id = 't1'").fetchone()
    assert row["subject"] == "Latest"
    assert row["message_count"] == 2


# ---------- FTS5 search ----------


def test_search_finds_by_subject(db: Database) -> None:
    messages_repo.upsert_messages(
        db,
        [
            _make_message("m1", subject="Invoice for May"),
            _make_message("m2", subject="Vacation photos"),
        ],
    )
    hits = search_repo.search(db, "invoice")
    assert [h.message_id for h in hits] == ["m1"]


def test_search_finds_by_body(db: Database) -> None:
    messages_repo.upsert_messages(
        db,
        [_make_message("m1", subject="x", body="meet me at the railway station tomorrow")],
    )
    hits = search_repo.search(db, "railway")
    assert [h.message_id for h in hits] == ["m1"]


def test_search_finds_by_from_name(db: Database) -> None:
    messages_repo.upsert_messages(
        db,
        [_make_message("m1", from_name="Carol Specific", from_addr="c@example.com")],
    )
    hits = search_repo.search(db, "Specific")
    assert [h.message_id for h in hits] == ["m1"]


def test_search_no_matches(db: Database) -> None:
    messages_repo.upsert_messages(db, [_make_message("m1", subject="hello")])
    assert search_repo.search(db, "nonexistent_word_xyz") == []


def test_search_reflects_deletion(db: Database) -> None:
    messages_repo.upsert_messages(db, [_make_message("m1", subject="findme")])
    assert len(search_repo.search(db, "findme")) == 1
    messages_repo.delete_messages(db, ["m1"])
    assert search_repo.search(db, "findme") == []


# ---------- sync_state ----------


def test_sync_state_default(db: Database) -> None:
    state = sync_state.get(db)
    assert state.last_history_id is None
    assert state.account_email is None


def test_sync_state_set_full(db: Database) -> None:
    sync_state.set_after_full_sync(db, "user@example.com", "12345")
    state = sync_state.get(db)
    assert state.account_email == "user@example.com"
    assert state.last_history_id == "12345"
    assert state.last_full_sync_at is not None


def test_sync_state_incremental_preserves_account(db: Database) -> None:
    sync_state.set_after_full_sync(db, "user@example.com", "100")
    sync_state.set_after_incremental_sync(db, "200")
    state = sync_state.get(db)
    assert state.account_email == "user@example.com"
    assert state.last_history_id == "200"
    assert state.last_incremental_sync_at is not None
