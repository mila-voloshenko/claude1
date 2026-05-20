from __future__ import annotations

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


class GmailClient:
    def __init__(self, credentials: Credentials) -> None:
        self._service: Any = build("gmail", "v1", credentials=credentials, cache_discovery=False)

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
