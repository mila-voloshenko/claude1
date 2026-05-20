"""Hard guardrail: the codebase must never call Gmail's send endpoints.

This test scans every .py file under src/ for any reference to Gmail send-message
methods. If you have a legitimate reason to allowlist a specific match, list it
in `ALLOWLIST` with a justification comment — and expect a serious review.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

FORBIDDEN_PATTERNS = [
    re.compile(r"\.messages\(\)\.send\b"),
    re.compile(r"users\.messages\.send\b"),
    re.compile(r"['\"]gmail\.send['\"]"),
    re.compile(r"['\"]https://www\.googleapis\.com/auth/gmail\.send['\"]"),
]

ALLOWLIST: set[tuple[str, int]] = set()


def test_no_gmail_send_references() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if (str(path), lineno) in ALLOWLIST:
                continue
            for pattern in FORBIDDEN_PATTERNS:
                if pattern.search(line):
                    rel = path.relative_to(SRC.parent)
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Forbidden Gmail send reference(s) found. The mail assistant must never "
        "send messages — drafts only.\n" + "\n".join(offenders)
    )
