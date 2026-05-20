# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Local Gmail secretary (see `goal.txt`). Sorts, summarises, drafts replies, and produces a daily briefing — but **never sends or deletes**. Writes only to Gmail Drafts and to labels/archive/snooze with explicit user confirmation. Runs entirely on the user's Windows machine; the only network egress is Gmail/Calendar APIs and the Claude API.

## Hard guardrail — no sending

The codebase MUST NEVER call `users.messages.send` (or its client equivalents) and MUST NOT request the `gmail.send` OAuth scope. `tests/test_no_send.py` enforces this by greppping `src/` — keep that test green. If you ever genuinely need to allowlist a match, justify it in the test's `ALLOWLIST` set and expect a serious review.

## Stack & decisions (locked in 2026-05-20)

- **Runtime**: Python 3.14 (pinned via `.python-version`), managed by `uv`.
- **Layout**: src layout — `src/mail_assistant/{google_apis,store,analysis,drafts,briefing,web,config}/`. `google_apis/` holds both Gmail and Calendar (they share OAuth). Future Outlook adapter lands as `outlook_apis/`.
- **Config**: `pydantic-settings`, prefix `MAIL_ASSISTANT_`, reads `.env` (see `.env.example`).
- **Providers**: Gmail-first via Google OAuth **desktop-app** client (loopback redirect — no public domain). Outlook later via a sibling `outlook_apis/` adapter.
- **Storage**: SQLite + FTS5 (not yet scaffolded).
- **Web UI**: FastAPI on `127.0.0.1` (not yet scaffolded).
- **LLM**: Claude API. Use prompt caching for long threads + sent-style profile.
- **Secrets**: `keyring` → Windows Credential Manager for OAuth refresh tokens. Single keyring entry: service `mail_assistant`, username `google-primary` (no multi-account yet).
- **Scheduler**: Windows Task Scheduler for the daily briefing.

## Common commands

All commands assume you are at the repo root.

```powershell
uv sync                                # install runtime + dev deps
uv run pytest                          # run all tests
uv run pytest tests/test_no_send.py -v # run a single test file
uv run ruff check .                    # lint
uv run ruff format .                   # format
uv run mypy                            # type-check
```

CLI surface (`uv run mail-assistant ...`):

```
mail-assistant auth              # run OAuth flow, store creds in Credential Manager
mail-assistant auth status       # which account, token age, days until refresh expiry
mail-assistant auth revoke       # delete local creds (server-side revoke via myaccount.google.com)
mail-assistant inbox unread [-n] # print N most recent unread messages
mail-assistant calendar today    # print today's events
```

If `uv` is not on PATH (winget install may not refresh the current shell), it lives at:
`C:\Users\volos\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`

## OAuth quirk to remember

`gmail.readonly` is a Google **restricted** scope. While the OAuth consent screen sits in **Testing** status (where it will stay for personal use — verification is too heavy), refresh tokens issued to test users expire after **7 days**. `mail-assistant auth status` shows the remaining time; once it hits zero, re-run `mail-assistant auth` and grant again. This is the only routine maintenance the user has.

## Notes for future Claude sessions

- `goal.txt` is the product spec. Treat it as authoritative when scoping new features.
- `PHASE0.md` is a user-side checklist (looks hook-generated). Don't write to it unless asked.
- Adding a new Gmail API call? Double-check it isn't on the "send" path before importing it.
