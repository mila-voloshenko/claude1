from __future__ import annotations

from datetime import datetime, time
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mail_assistant.config.settings import Settings, load_settings
from mail_assistant.google_apis import auth as auth_mod
from mail_assistant.google_apis.calendar_client import CalendarClient
from mail_assistant.google_apis.gmail_client import GmailClient
from mail_assistant.store import search as search_repo
from mail_assistant.store.db import Database
from mail_assistant.store.migrations import apply_migrations
from mail_assistant.sync.syncer import (
    SyncError,
    incremental_sync,
    initial_sync,
)

app = typer.Typer(help="Local Gmail secretary — drafts, briefs, never sends.")
auth_app = typer.Typer(help="Manage Google OAuth credentials.")
inbox_app = typer.Typer(help="Inspect your Gmail inbox (read-only).")
calendar_app = typer.Typer(help="Inspect your Google Calendar (read-only).")
sync_app = typer.Typer(help="Sync your mailbox into the local SQLite cache.")
app.add_typer(auth_app, name="auth")
app.add_typer(inbox_app, name="inbox")
app.add_typer(calendar_app, name="calendar")
app.add_typer(sync_app, name="sync")

console = Console()


def _open_db(settings: Settings) -> Database:
    db = Database(settings.db_path)
    apply_migrations(db)
    return db


def _gmail_from_settings(settings: Settings) -> GmailClient:
    creds = auth_mod.get_credentials(settings.google_client_secret_file, interactive=False)
    return GmailClient(creds)


@auth_app.callback(invoke_without_command=True)
def _auth_default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _do_auth()


@auth_app.command("login")
def auth_login() -> None:
    """Run OAuth flow and store credentials in Windows Credential Manager."""
    _do_auth()


def _do_auth() -> None:
    settings = load_settings()
    try:
        creds = auth_mod.get_credentials(settings.google_client_secret_file, interactive=True)
    except auth_mod.AuthError as e:
        console.print(f"[red]Auth failed:[/red] {e}")
        raise typer.Exit(1) from e
    profile = GmailClient(creds).get_profile()
    console.print(f"[green]Authenticated[/green] as {profile['emailAddress']}")


@auth_app.command("status")
def auth_status() -> None:
    """Show whether a valid Google token is stored locally."""
    info = auth_mod.auth_status()
    if not info:
        console.print("[yellow]No stored credentials.[/yellow] Run `mail-assistant auth`.")
        raise typer.Exit(1)
    remaining = float(info["refresh_expires_in_days"])
    color = "green" if remaining > 2 else "yellow" if remaining > 0 else "red"
    console.print(f"Account:    {info['account_email']}")
    console.print(f"Issued:     {info['issued_at']}")
    console.print(f"Age:        {info['age_days']} days")
    console.print(f"Refresh in: [{color}]{remaining} days[/{color}]")
    if remaining <= 0:
        console.print(
            "[red]Refresh token likely expired. Run `mail-assistant auth` to sign in.[/red]"
        )


@auth_app.command("revoke")
def auth_revoke() -> None:
    """Delete the local copy of the OAuth credentials."""
    auth_mod.revoke_local()
    console.print(
        "Local credentials deleted. To revoke server-side: https://myaccount.google.com/permissions"
    )


@inbox_app.command("unread")
def inbox_unread(
    n: Annotated[int, typer.Option("-n", "--limit", help="How many messages to fetch.")] = 10,
) -> None:
    """Print N most recent unread messages."""
    settings = load_settings()
    creds = auth_mod.get_credentials(settings.google_client_secret_file, interactive=False)
    messages = GmailClient(creds).list_unread(max_results=n)
    if not messages:
        console.print("Inbox is clear.")
        return
    table = Table(title=f"Unread ({len(messages)})")
    table.add_column("From")
    table.add_column("Subject")
    table.add_column("Date")
    for m in messages:
        table.add_row(m.sender, m.subject, m.date)
    console.print(table)


@calendar_app.command("today")
def calendar_today() -> None:
    """Print today's calendar events."""
    settings = load_settings()
    creds = auth_mod.get_credentials(settings.google_client_secret_file, interactive=False)
    now = datetime.now().astimezone()
    start = datetime.combine(now.date(), time.min).astimezone()
    end = datetime.combine(now.date(), time.max).astimezone()
    events = CalendarClient(creds).list_events(start, end)
    if not events:
        console.print("No events today.")
        return
    table = Table(title=f"Today — {now.date().isoformat()}")
    table.add_column("Start")
    table.add_column("End")
    table.add_column("Title")
    table.add_column("Location")
    for e in events:
        table.add_row(e.start, e.end, e.summary, e.location)
    console.print(table)


@sync_app.command("init")
def sync_init(
    days: Annotated[
        int | None,
        typer.Option("-d", "--days", help="Lookback window in days. Overrides settings."),
    ] = None,
) -> None:
    """Full sync of the last N days into the local SQLite cache."""
    settings = load_settings()
    window = days if days is not None else settings.sync_window_days
    db = _open_db(settings)
    gmail = _gmail_from_settings(settings)
    console.print(f"Syncing the last [bold]{window}[/bold] days...")
    report = initial_sync(db, gmail, days=window)
    console.print(
        f"[green]Done.[/green] Upserted {report.upserted} messages, "
        f"history checkpoint {report.new_history_id}."
    )
    if report.errors:
        console.print(f"[yellow]{len(report.errors)} errors:[/yellow]")
        for err in report.errors[:5]:
            console.print(f"  {err}")


@sync_app.command("update")
def sync_update() -> None:
    """Incrementally apply changes since the last sync."""
    settings = load_settings()
    db = _open_db(settings)
    gmail = _gmail_from_settings(settings)
    try:
        report = incremental_sync(db, gmail)
    except SyncError as e:
        console.print(f"[red]Sync failed:[/red] {e}")
        raise typer.Exit(1) from e
    console.print(
        f"[green]Done.[/green] Upserted {report.upserted}, deleted {report.deleted}, "
        f"history checkpoint {report.new_history_id}."
    )
    if report.errors:
        console.print(f"[yellow]{len(report.errors)} errors:[/yellow]")
        for err in report.errors[:5]:
            console.print(f"  {err}")


@app.command("search")
def cli_search(
    query: Annotated[str, typer.Argument(help="FTS5 query, e.g. 'invoice OR receipt'.")],
    limit: Annotated[int, typer.Option("-n", "--limit")] = 20,
) -> None:
    """Full-text search across cached messages (subject, snippet, sender, body)."""
    settings = load_settings()
    db = _open_db(settings)
    hits = search_repo.search(db, query, limit=limit)
    if not hits:
        console.print("No matches.")
        return
    table = Table(title=f"Search: {query} ({len(hits)})")
    table.add_column("Date")
    table.add_column("From")
    table.add_column("Subject")
    for h in hits:
        table.add_row(h.date.strftime("%Y-%m-%d"), h.from_addr or h.from_name, h.subject)
    console.print(table)


def run() -> None:
    app()


if __name__ == "__main__":
    run()
