# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Local Gmail secretary (see `goal.txt`). Sorts, summarises, drafts replies, and produces a daily briefing — but **never sends or deletes**. Writes only to Gmail Drafts and to labels/archive/snooze with explicit user confirmation. Runs entirely on the user's Windows machine; the only network egress is Gmail/Calendar APIs and the Claude API.

## Hard guardrail — no sending

The codebase MUST NEVER call `users.messages.send` (or its client equivalents) and MUST NOT request the `gmail.send` OAuth scope. `tests/test_no_send.py` enforces this by greppping `src/` — keep that test green. If you ever genuinely need to allowlist a match, justify it in the test's `ALLOWLIST` set and expect a serious review.

## Stack & decisions (locked in 2026-05-20)

- **Runtime**: Python 3.14 (pinned via `.python-version`), managed by `uv`.
- **Layout**: src layout — `src/mail_assistant/{google_apis,store,sync,analysis,drafts,briefing,web,config}/`. `google_apis/` holds both Gmail and Calendar (they share OAuth). `sync/` orchestrates between providers and `store/`. Future Outlook adapter lands as `outlook_apis/`.
- **Config**: `pydantic-settings`, prefix `MAIL_ASSISTANT_`, reads `.env` (see `.env.example`).
- **Providers**: Gmail-first via Google OAuth **desktop-app** client (loopback redirect — no public domain). Outlook later via a sibling `outlook_apis/` adapter.
- **Storage**: SQLite at `%USERPROFILE%\.mail_assistant\mail.db` (WAL mode). Schema in `store/migrations/*.sql`, applied via `apply_migrations()` on every CLI invocation. Raw `sqlite3` (no ORM). FTS5 contentless virtual table `messages_fts` kept in sync via triggers on `messages`. Body text is fetched lazily and `COALESCE`d on upsert so metadata-only refreshes don't wipe cached bodies.
- **Web UI**: FastAPI on `127.0.0.1` (not yet scaffolded).
- **LLM**: Claude API. Default model `claude-opus-4-7` (override via `MAIL_ASSISTANT_ANTHROPIC_MODEL`). Use `client.messages.parse()` with Pydantic schemas for structured outputs. Cache long system prompts with `cache_control: ephemeral`. Classifier uses `thinking: {type: "disabled"}` + `effort: "low"` (high volume, low per-call stakes); switch to adaptive thinking for harder per-thread tasks in later phases.
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
mail-assistant inbox unread [-n] # print N most recent unread (hits Gmail directly)
mail-assistant calendar today    # print today's events
mail-assistant sync init [-d 30] # full sync of last N days into local SQLite
mail-assistant sync update       # incremental sync via Gmail History API
mail-assistant search <query>    # FTS5 search over cached messages
mail-assistant classify run [-n] # classify up to N unclassified messages via Claude
mail-assistant classify counts   # count per category
mail-assistant classify show <category>  # list messages in a category
```

If `uv` is not on PATH (winget install may not refresh the current shell), it lives at:
`C:\Users\volos\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`

## OAuth quirk to remember

`gmail.readonly` is a Google **restricted** scope. While the OAuth consent screen sits in **Testing** status (where it will stay for personal use — verification is too heavy), refresh tokens issued to test users expire after **7 days**. `mail-assistant auth status` shows the remaining time; once it hits zero, re-run `mail-assistant auth` and grant again. This is the only routine maintenance the user has.

## Notes for future Claude sessions

- `goal.txt` is the product spec. Treat it as authoritative when scoping new features.
- `PHASE0.md` is a user-side checklist (looks hook-generated). Don't write to it unless asked.
- Adding a new Gmail API call? Double-check it isn't on the "send" path before importing it.
- The local SQLite DB lives in `%USERPROFILE%\.mail_assistant\mail.db` and contains the user's email content. It's their machine, but treat the file as sensitive (no logging dumps, no analytics).
- Gmail's `users.history.list` returns history only for ~7 days. If a user's `sync update` fails because the checkpoint is too old, `sync/syncer.py` raises `SyncError` with guidance to re-run `sync init`. Don't silently re-baseline — let the user see it.
- When extending the store schema, add a new `store/migrations/000N_*.sql` file. Migrations are forward-only and tracked in the `_migrations` table.
- LLM prompts live in `src/mail_assistant/analysis/prompts/*.md` and are loaded via `importlib.resources`. Keeping them in `.md` files (not Python literals) avoids line-length wars and makes the prompt easy to edit without touching code. The `prompts/` directory has an `__init__.py` so the build backend ships the files.
- Adding a new analysis feature that calls Claude? Always: (1) `cache_control: ephemeral` on the system prompt, (2) `output_format=PydanticModel` via `messages.parse()`, (3) handle `response.parsed_output is None` explicitly (the model can refuse). See `analysis/classifier.py` for the pattern.
