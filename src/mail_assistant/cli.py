from __future__ import annotations

from datetime import datetime, time
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mail_assistant.config.settings import load_settings
from mail_assistant.google_apis import auth as auth_mod
from mail_assistant.google_apis.calendar_client import CalendarClient
from mail_assistant.google_apis.gmail_client import GmailClient

app = typer.Typer(help="Local Gmail secretary — drafts, briefs, never sends.")
auth_app = typer.Typer(help="Manage Google OAuth credentials.")
inbox_app = typer.Typer(help="Inspect your Gmail inbox (read-only).")
calendar_app = typer.Typer(help="Inspect your Google Calendar (read-only).")
app.add_typer(auth_app, name="auth")
app.add_typer(inbox_app, name="inbox")
app.add_typer(calendar_app, name="calendar")

console = Console()


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


def run() -> None:
    app()


if __name__ == "__main__":
    run()
