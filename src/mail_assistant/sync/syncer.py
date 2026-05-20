from __future__ import annotations

from datetime import UTC, datetime
from email.utils import formataddr, getaddresses, parseaddr

from mail_assistant.google_apis.gmail_client import GmailClient
from mail_assistant.store import messages as messages_repo
from mail_assistant.store import sync_state
from mail_assistant.store.db import Database
from mail_assistant.store.models import StoredMessage, SyncReport


class SyncError(Exception):
    pass


def _parse_internal_date(internal_date: str | int) -> datetime:
    ms = int(internal_date)
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _parse_addresses(header_value: str) -> list[str]:
    """Parse a To/Cc header into normalized 'Name <addr>' strings."""
    if not header_value:
        return []
    return [formataddr((name, addr)) for name, addr in getaddresses([header_value]) if addr]


def _gmail_payload_to_stored(payload: dict) -> StoredMessage:
    """Convert a raw Gmail message dict (format=full) into a StoredMessage.

    body_text is left None — bodies are fetched lazily.
    """
    headers = {h["name"]: h["value"] for h in payload.get("payload", {}).get("headers", [])}
    from_raw = headers.get("From", "")
    from_name, from_addr = parseaddr(from_raw)
    labels: list[str] = list(payload.get("labelIds", []))
    return StoredMessage(
        id=payload["id"],
        thread_id=payload["threadId"],
        history_id=str(payload.get("historyId", "")),
        from_addr=from_addr,
        from_name=from_name,
        to_addrs=_parse_addresses(headers.get("To", "")),
        cc_addrs=_parse_addresses(headers.get("Cc", "")),
        subject=headers.get("Subject", ""),
        date=_parse_internal_date(payload.get("internalDate", "0")),
        snippet=payload.get("snippet", ""),
        labels=labels,
        is_unread="UNREAD" in labels,
        is_sent="SENT" in labels,
    )


def initial_sync(db: Database, gmail: GmailClient, days: int = 30) -> SyncReport:
    profile = gmail.get_profile()
    account_email = profile["emailAddress"]
    history_id = str(profile["historyId"])

    query = f"newer_than:{days}d -in:spam -in:trash"
    ids = list(gmail.iter_message_ids(query))
    upserted = 0
    errors: list[str] = []
    affected_threads: set[str] = set()

    for mid in ids:
        try:
            payload = gmail.get_message_metadata(mid)
        except Exception as e:
            errors.append(f"{mid}: {e}")
            continue
        stored = _gmail_payload_to_stored(payload)
        messages_repo.upsert_messages(db, [stored])
        affected_threads.add(stored.thread_id)
        upserted += 1

    for tid in affected_threads:
        messages_repo.upsert_thread_summary(db, tid)

    sync_state.set_after_full_sync(db, account_email, history_id)
    return SyncReport(
        upserted=upserted,
        deleted=0,
        skipped=0,
        new_history_id=history_id,
        errors=errors,
    )


def incremental_sync(db: Database, gmail: GmailClient) -> SyncReport:
    state = sync_state.get(db)
    if not state.last_history_id:
        raise SyncError("No sync baseline. Run `mail-assistant sync init` first.")

    changed_ids: set[str] = set()
    deleted_ids: set[str] = set()
    history_too_old = False

    try:
        for record in gmail.iter_history(state.last_history_id):
            for added in record.get("messagesAdded", []):
                changed_ids.add(added["message"]["id"])
            for deleted in record.get("messagesDeleted", []):
                deleted_ids.add(deleted["message"]["id"])
            for la in record.get("labelsAdded", []):
                changed_ids.add(la["message"]["id"])
            for lr in record.get("labelsRemoved", []):
                changed_ids.add(lr["message"]["id"])
    except Exception as e:
        # Gmail purges history older than ~7 days; signal a re-baseline need.
        msg = str(e).lower()
        if "history" in msg or "404" in msg or "410" in msg:
            history_too_old = True
        else:
            raise

    if history_too_old:
        raise SyncError(
            "Gmail history is too old to incrementally resume. "
            "Run `mail-assistant sync init` to re-baseline."
        )

    changed_ids -= deleted_ids
    affected_threads: set[str] = set()
    errors: list[str] = []
    upserted = 0

    for mid in changed_ids:
        try:
            payload = gmail.get_message_metadata(mid)
        except Exception as e:
            errors.append(f"{mid}: {e}")
            continue
        stored = _gmail_payload_to_stored(payload)
        messages_repo.upsert_messages(db, [stored])
        affected_threads.add(stored.thread_id)
        upserted += 1

    deleted = messages_repo.delete_messages(db, deleted_ids)

    for tid in affected_threads:
        messages_repo.upsert_thread_summary(db, tid)

    new_history_id = str(gmail.get_profile()["historyId"])
    sync_state.set_after_incremental_sync(db, new_history_id)

    return SyncReport(
        upserted=upserted,
        deleted=deleted,
        skipped=0,
        new_history_id=new_history_id,
        errors=errors,
    )


def fetch_body_if_missing(db: Database, gmail: GmailClient, message_id: str) -> str:
    """Return body_text, fetching from Gmail and caching if not yet stored."""
    existing = messages_repo.get_message(db, message_id)
    if existing is None:
        raise SyncError(f"Message {message_id} is not in the local store.")
    if existing.body_text is not None:
        return existing.body_text
    body = gmail.get_body(message_id)
    messages_repo.set_body(db, message_id, body, datetime.now(UTC))
    return body
