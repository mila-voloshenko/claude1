from __future__ import annotations

import base64
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


@dataclass(frozen=True)
class MessageSummary:
    id: str
    thread_id: str
    subject: str
    sender: str
    date: str
    snippet: str


def _extract_body_text(payload: dict[str, Any]) -> str:
    """Walk a Gmail message payload and return the first text/plain body, or strip HTML."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return _b64url_decode(data)
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")
            if data:
                return _b64url_decode(data)
        nested = _extract_body_text(part)
        if nested:
            return nested
    if mime == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            return _strip_html(_b64url_decode(data))
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data")
            if data:
                return _strip_html(_b64url_decode(data))
    return ""


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class GmailClient:
    def __init__(self, credentials: Credentials) -> None:
        self._service: Any = build("gmail", "v1", credentials=credentials, cache_discovery=False)

    # ---------- Phase 1 surface (read-only metadata) ----------

    def list_unread(self, max_results: int = 25) -> list[MessageSummary]:
        return self._list("is:unread in:inbox", max_results)

    def list_recent(self, query: str, max_results: int = 50) -> list[MessageSummary]:
        return self._list(query, max_results)

    def _list(self, query: str, max_results: int) -> list[MessageSummary]:
        resp = (
            self._service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        summaries: list[MessageSummary] = []
        for m in resp.get("messages", []):
            detail = (
                self._service.users()
                .messages()
                .get(
                    userId="me",
                    id=m["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                )
                .execute()
            )
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            summaries.append(
                MessageSummary(
                    id=detail["id"],
                    thread_id=detail["threadId"],
                    subject=headers.get("Subject", "(no subject)"),
                    sender=headers.get("From", "(unknown)"),
                    date=headers.get("Date", ""),
                    snippet=detail.get("snippet", ""),
                )
            )
        return summaries

    def get_profile(self) -> dict[str, Any]:
        return dict(self._service.users().getProfile(userId="me").execute())

    # ---------- Phase 2 surface (sync) ----------

    def iter_message_ids(self, query: str) -> Iterator[str]:
        """Yield message IDs matching `query`, paging through all results."""
        page_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"userId": "me", "q": query, "maxResults": 500}
            if page_token:
                kwargs["pageToken"] = page_token
            resp = self._service.users().messages().list(**kwargs).execute()
            for m in resp.get("messages", []):
                yield m["id"]
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def get_message_metadata(self, message_id: str) -> dict[str, Any]:
        """Headers + labels + snippet — no body. ~1 KiB per message."""
        return dict(
            self._service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["Subject", "From", "To", "Cc", "Date"],
            )
            .execute()
        )

    def get_message_full(self, message_id: str) -> dict[str, Any]:
        """Full message including the MIME payload tree."""
        return dict(
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

    def get_body(self, message_id: str) -> str:
        """Fetch and parse the message body, preferring text/plain."""
        full = self.get_message_full(message_id)
        return _extract_body_text(full.get("payload", {}))

    def iter_history(self, start_history_id: str) -> Iterator[dict[str, Any]]:
        """Yield raw history records since `start_history_id`."""
        page_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "userId": "me",
                "startHistoryId": start_history_id,
                "maxResults": 500,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            resp = self._service.users().history().list(**kwargs).execute()
            yield from resp.get("history", [])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
