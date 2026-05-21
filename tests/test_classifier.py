from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mail_assistant.analysis.categories import Category, Classification
from mail_assistant.analysis.classifier import (
    ClassifyReport,
    build_user_message,
    classify_pending,
)
from mail_assistant.analysis.llm import LLMClient, LLMConfigError
from mail_assistant.store import classifications as classifications_repo
from mail_assistant.store import messages as messages_repo
from mail_assistant.store.db import Database
from mail_assistant.store.migrations import apply_migrations
from mail_assistant.store.models import StoredMessage


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "test.db")
    apply_migrations(d)
    return d


def _make_message(mid: str, *, subject: str = "Hello", body: str | None = None) -> StoredMessage:
    return StoredMessage(
        id=mid,
        thread_id="t1",
        history_id="100",
        from_addr="alice@example.com",
        from_name="Alice",
        to_addrs=["bob@example.com"],
        cc_addrs=[],
        subject=subject,
        date=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        snippet="snippet text",
        labels=["INBOX", "UNREAD"],
        is_unread=True,
        is_sent=False,
        body_text=body,
    )


# ---------- LLMClient ----------


def test_llm_client_requires_api_key() -> None:
    with pytest.raises(LLMConfigError):
        LLMClient(api_key="")


def test_llm_client_stores_model() -> None:
    llm = LLMClient(api_key="sk-test-fake", model="claude-haiku-4-5")
    assert llm.model == "claude-haiku-4-5"


# ---------- build_user_message ----------


def test_build_user_message_includes_headers() -> None:
    msg = _make_message("m1", subject="Project update", body="Body text here")
    rendered = build_user_message(msg)
    assert "Alice" in rendered
    assert "alice@example.com" in rendered
    assert "Project update" in rendered
    assert "Body text here" in rendered


def test_build_user_message_handles_missing_body() -> None:
    msg = _make_message("m1", subject="No body yet", body=None)
    rendered = build_user_message(msg)
    assert "<body not yet fetched>" in rendered


# ---------- classifications repo ----------


def test_upsert_and_get(db: Database) -> None:
    msg = _make_message("m1")
    messages_repo.upsert_messages(db, [msg])
    clf = Classification(
        category=Category.URGENT, confidence=0.91, reason="Same-day deadline cited"
    )
    classifications_repo.upsert(db, "m1", clf, model="claude-opus-4-7")
    stored = classifications_repo.get(db, "m1")
    assert stored is not None
    assert stored.category == Category.URGENT
    assert stored.confidence == pytest.approx(0.91)
    assert stored.model == "claude-opus-4-7"


def test_upsert_replaces_existing(db: Database) -> None:
    msg = _make_message("m1")
    messages_repo.upsert_messages(db, [msg])
    first = Classification(category=Category.FYI, confidence=0.6, reason="r1")
    second = Classification(category=Category.URGENT, confidence=0.95, reason="r2")
    classifications_repo.upsert(db, "m1", first, model="claude-opus-4-7")
    classifications_repo.upsert(db, "m1", second, model="claude-opus-4-7")
    stored = classifications_repo.get(db, "m1")
    assert stored is not None and stored.category == Category.URGENT


def test_list_unclassified_excludes_classified(db: Database) -> None:
    messages_repo.upsert_messages(
        db, [_make_message("m1"), _make_message("m2"), _make_message("m3")]
    )
    classifications_repo.upsert(
        db,
        "m2",
        Classification(category=Category.FYI, confidence=0.7, reason="r"),
        model="claude-opus-4-7",
    )
    pending = classifications_repo.list_unclassified(db)
    assert {m.id for m in pending} == {"m1", "m3"}


def test_list_by_category(db: Database) -> None:
    messages_repo.upsert_messages(db, [_make_message("m1"), _make_message("m2")])
    classifications_repo.upsert(
        db,
        "m1",
        Classification(category=Category.URGENT, confidence=0.9, reason="r"),
        model="claude-opus-4-7",
    )
    classifications_repo.upsert(
        db,
        "m2",
        Classification(category=Category.FYI, confidence=0.6, reason="r"),
        model="claude-opus-4-7",
    )
    urgent = classifications_repo.list_by_category(db, Category.URGENT)
    assert len(urgent) == 1
    assert urgent[0][0].id == "m1"
    assert urgent[0][1].category == Category.URGENT


def test_count_by_category(db: Database) -> None:
    messages_repo.upsert_messages(db, [_make_message(f"m{i}") for i in range(3)])
    classifications_repo.upsert(
        db,
        "m0",
        Classification(category=Category.URGENT, confidence=0.9, reason="r"),
        model="x",
    )
    classifications_repo.upsert(
        db,
        "m1",
        Classification(category=Category.URGENT, confidence=0.9, reason="r"),
        model="x",
    )
    classifications_repo.upsert(
        db,
        "m2",
        Classification(category=Category.FYI, confidence=0.6, reason="r"),
        model="x",
    )
    counts = classifications_repo.count_by_category(db)
    assert counts[Category.URGENT] == 2
    assert counts[Category.FYI] == 1


# ---------- classify_pending orchestrator ----------


def test_classify_pending_uses_injected_classify_fn(db: Database) -> None:
    messages_repo.upsert_messages(db, [_make_message("m1"), _make_message("m2")])

    captured: list[str] = []

    def fake_classify(llm: LLMClient, msg: StoredMessage) -> Classification:
        captured.append(msg.id)
        return Classification(category=Category.FYI, confidence=0.8, reason="stub")

    llm = LLMClient(api_key="sk-test-fake", model="stub-model")
    report = classify_pending(db, llm, limit=10, classify_fn=fake_classify)

    assert report.classified == 2
    assert set(captured) == {"m1", "m2"}
    stored = classifications_repo.get(db, "m1")
    assert stored is not None
    assert stored.model == "stub-model"


def test_classify_pending_skips_already_classified(db: Database) -> None:
    messages_repo.upsert_messages(db, [_make_message("m1"), _make_message("m2")])
    classifications_repo.upsert(
        db,
        "m1",
        Classification(category=Category.SOCIAL, confidence=0.9, reason="r"),
        model="prev",
    )

    seen: list[str] = []

    def fake_classify(llm: LLMClient, msg: StoredMessage) -> Classification:
        seen.append(msg.id)
        return Classification(category=Category.FYI, confidence=0.7, reason="stub")

    llm = LLMClient(api_key="sk-test-fake")
    report = classify_pending(db, llm, classify_fn=fake_classify)
    assert seen == ["m2"]
    assert report.classified == 1


def test_classify_pending_continues_past_errors(db: Database) -> None:
    messages_repo.upsert_messages(db, [_make_message("m1"), _make_message("m2")])

    def flaky_classify(llm: LLMClient, msg: StoredMessage) -> Classification:
        if msg.id == "m1":
            raise RuntimeError("simulated failure")
        return Classification(category=Category.FYI, confidence=0.6, reason="ok")

    llm = LLMClient(api_key="sk-test-fake")
    report = classify_pending(db, llm, classify_fn=flaky_classify)
    assert report.classified == 1
    assert len(report.errors) == 1
    assert "m1" in report.errors[0]


def test_classify_pending_report_default() -> None:
    report = ClassifyReport()
    assert report.classified == 0
    assert report.errors == []
