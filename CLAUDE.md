# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Local Gmail secretary (see `goal.txt`). Sorts, summarises, drafts replies, and produces a daily briefing — but **never sends or deletes**. Writes only to Gmail Drafts and to labels/archive/snooze with explicit user confirmation. Runs entirely on the user's Windows machine; the only network egress is Gmail/Calendar APIs and the Claude API.

## Hard guardrail — no sending

The codebase MUST NEVER call `users.messages.send` (or its client equivalents) and MUST NOT request the `gmail.send` OAuth scope. `tests/test_no_send.py` enforces this by greppping `src/` — keep that test green. If you ever genuinely need to allowlist a match, justify it in the test's `ALLOWLIST` set and expect a serious review.

## Stack & decisions (locked in 2026-05-20)

- **Runtime**: Python 3.14 (pinned via `.python-version`), managed by `uv`.
- **Layout**: src layout — `src/mail_assistant/{gmail,store,analysis,drafts,briefing,web,config}/`.
- **Config**: `pydantic-settings`, prefix `MAIL_ASSISTANT_`, reads `.env` (see `.env.example`).
- **Providers**: Gmail-first via Google OAuth **desktop-app** client (loopback redirect — no public domain). Outlook later behind an adapter in `gmail/` (will be renamed when that lands).
- **Storage**: SQLite + FTS5 (not yet scaffolded).
- **Web UI**: FastAPI on `127.0.0.1` (not yet scaffolded).
- **LLM**: Claude API. Use prompt caching for long threads + sent-style profile.
- **Secrets**: `keyring` → Windows Credential Manager for OAuth refresh tokens (not yet scaffolded).
- **Scheduler**: Windows Task Scheduler for the daily briefing.

## Common commands

All commands assume you are at the repo root.

```powershell
uv sync                          # install runtime + dev deps into .venv
uv run mail-assistant            # run the entry point (currently a stub)
uv run pytest                    # run all tests
uv run pytest tests/test_no_send.py -v   # run a single test file
uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy                      # type-check (strict)
```

If `uv` is not on PATH (winget install may not refresh the current shell), it lives at:
`C:\Users\volos\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`

## Notes for future Claude sessions

- `goal.txt` is the product spec. Treat it as authoritative when scoping new features.
- `PHASE0.md` is a user-side checklist (looks hook-generated). Don't write to it unless asked.
- The package directory `mail_assistant/gmail/` is named after the first provider; expect a future rename when Outlook lands. Don't introduce hard dependencies on the name yet.
- Adding a new Gmail API call? Double-check it isn't on the "send" path before importing it.
