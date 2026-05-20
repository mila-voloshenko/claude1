from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    summary: str
    start: str
    end: str
    attendees: list[str]
    location: str
    description: str


class CalendarClient:
    def __init__(self, credentials: Credentials) -> None:
        self._service: Any = build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def list_events(
        self,
        time_min: datetime,
        time_max: datetime,
        calendar_id: str = "primary",
    ) -> list[CalendarEvent]:
        resp = (
            self._service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events: list[CalendarEvent] = []
        for e in resp.get("items", []):
            start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date") or ""
            end = e.get("end", {}).get("dateTime") or e.get("end", {}).get("date") or ""
            events.append(
                CalendarEvent(
                    id=e["id"],
                    summary=e.get("summary", "(no title)"),
                    start=start,
                    end=end,
                    attendees=[a.get("email", "") for a in e.get("attendees", [])],
                    location=e.get("location", ""),
                    description=e.get("description", ""),
                )
            )
        return events
