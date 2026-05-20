from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class StoredMessage:
    id: str
    thread_id: str
    history_id: str
    from_addr: str
    from_name: str
    to_addrs: list[str]
    cc_addrs: list[str]
    subject: str
    date: datetime
    snippet: str
    labels: list[str]
    is_unread: bool
    is_sent: bool
    body_text: str | None = None
    fetched_body_at: datetime | None = None


@dataclass(frozen=True)
class StoredThread:
    id: str
    subject: str
    snippet: str
    last_message_at: datetime
    message_count: int


@dataclass(frozen=True)
class SyncState:
    account_email: str | None
    last_history_id: str | None
    last_full_sync_at: datetime | None
    last_incremental_sync_at: datetime | None


@dataclass(frozen=True)
class SearchHit:
    message_id: str
    thread_id: str
    subject: str
    snippet: str
    from_addr: str
    from_name: str
    date: datetime


@dataclass(frozen=True)
class SyncReport:
    upserted: int = 0
    deleted: int = 0
    skipped: int = 0
    new_history_id: str | None = None
    errors: list[str] = field(default_factory=list)
