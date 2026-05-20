from __future__ import annotations

import re
from datetime import UTC, datetime
from importlib import resources

from mail_assistant.store.db import Database

MIGRATION_PATTERN = re.compile(r"^(\d{4})_.+\.sql$")


def _discover_migrations() -> list[tuple[int, str, str]]:
    pkg = resources.files("mail_assistant.store.migrations")
    found: list[tuple[int, str, str]] = []
    for entry in pkg.iterdir():
        m = MIGRATION_PATTERN.match(entry.name)
        if not m:
            continue
        version = int(m.group(1))
        found.append((version, entry.name, entry.read_text(encoding="utf-8")))
    found.sort(key=lambda x: x[0])
    return found


def _applied_versions(db: Database) -> set[int]:
    try:
        rows = db.conn.execute("SELECT version FROM _migrations").fetchall()
    except Exception:
        return set()
    return {int(r["version"]) for r in rows}


def apply_migrations(db: Database) -> list[int]:
    """Apply any pending migrations. Returns the list of versions applied this call."""
    applied = _applied_versions(db)
    applied_now: list[int] = []
    for version, _name, sql in _discover_migrations():
        if version in applied:
            continue
        db.conn.executescript(sql)
        db.conn.execute(
            "INSERT INTO _migrations (version, applied_at) VALUES (?, ?)",
            (version, datetime.now(UTC).isoformat()),
        )
        applied_now.append(version)
    return applied_now
