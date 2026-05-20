"""Read-only OAuth scopes for the Google APIs we use.

Adding a write scope (gmail.send, gmail.compose, gmail.modify, calendar write)
requires a serious review. tests/test_scopes.py and tests/test_no_send.py both
guard this file.
"""

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_READONLY = "https://www.googleapis.com/auth/calendar.readonly"

READ_SCOPES: tuple[str, ...] = (GMAIL_READONLY, CALENDAR_READONLY)
