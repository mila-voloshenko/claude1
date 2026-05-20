from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import keyring
import keyring.errors
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from mail_assistant.google_apis.scopes import READ_SCOPES

KEYRING_SERVICE = "mail_assistant"
KEYRING_USERNAME = "google-primary"

# Refresh tokens issued to test users of an unverified app expire after 7 days.
# We surface this to the user via `auth status` and warn when within ~2 days.
REFRESH_TOKEN_LIFETIME_DAYS = 7


class AuthError(Exception):
    pass


def _read_stored() -> dict[str, Any] | None:
    raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    return json.loads(raw) if raw else None


def _write_stored(payload: dict[str, Any]) -> None:
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, json.dumps(payload))


def _delete_stored() -> None:
    with contextlib.suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)


def _credentials_from_json(creds_json: str) -> Credentials:
    return Credentials.from_authorized_user_info(json.loads(creds_json), list(READ_SCOPES))


def _fetch_account_email(creds: Credentials) -> str:
    from googleapiclient.discovery import build

    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = gmail.users().getProfile(userId="me").execute()
    return str(profile["emailAddress"])


def get_credentials(client_secret_file: Path, *, interactive: bool = True) -> Credentials:
    """Return valid Google credentials, running the OAuth flow if needed.

    interactive=False is used by background commands (inbox/calendar fetches)
    that should never block on a browser pop-up.
    """
    stored = _read_stored()
    if stored:
        creds = _credentials_from_json(stored["credentials"])
        if not creds.expired:
            return creds
        if creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                if not interactive:
                    raise AuthError(
                        "Refresh token rejected (likely expired or revoked). "
                        "Run `mail-assistant auth` to sign in again."
                    ) from e
            else:
                stored["credentials"] = creds.to_json()
                _write_stored(stored)
                return creds

    if not interactive:
        raise AuthError("No valid credentials available. Run `mail-assistant auth` first.")

    if not client_secret_file.exists():
        raise AuthError(
            f"OAuth client secret JSON not found at {client_secret_file}. "
            "Download a Desktop OAuth client from Google Cloud Console and save it there."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), list(READ_SCOPES))
    creds = flow.run_local_server(port=0)
    email = _fetch_account_email(creds)
    _write_stored(
        {
            "credentials": creds.to_json(),
            "issued_at": datetime.now(UTC).isoformat(),
            "account_email": email,
        }
    )
    return creds


def auth_status() -> dict[str, Any] | None:
    stored = _read_stored()
    if not stored:
        return None
    issued_at = datetime.fromisoformat(stored["issued_at"])
    age_days = (datetime.now(UTC) - issued_at).total_seconds() / 86400
    return {
        "account_email": stored["account_email"],
        "issued_at": stored["issued_at"],
        "age_days": round(age_days, 1),
        "refresh_expires_in_days": round(REFRESH_TOKEN_LIFETIME_DAYS - age_days, 1),
    }


def revoke_local() -> None:
    _delete_stored()
