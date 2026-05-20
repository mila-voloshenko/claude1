from __future__ import annotations

from mail_assistant.sync.syncer import _gmail_payload_to_stored, _parse_addresses


def test_parse_addresses_handles_simple() -> None:
    out = _parse_addresses("alice@example.com, bob@example.com")
    assert out == ["alice@example.com", "bob@example.com"]


def test_parse_addresses_handles_commas_in_display_names() -> None:
    out = _parse_addresses('"Smith, John" <john@example.com>, jane@example.com')
    assert out == ['"Smith, John" <john@example.com>', "jane@example.com"]


def test_parse_addresses_empty() -> None:
    assert _parse_addresses("") == []
    assert _parse_addresses("   ") == []


def test_gmail_payload_to_stored_minimal() -> None:
    payload = {
        "id": "m1",
        "threadId": "t1",
        "historyId": "100",
        "snippet": "short preview",
        "labelIds": ["INBOX", "UNREAD"],
        "internalDate": "1747731600000",  # arbitrary ms epoch
        "payload": {
            "headers": [
                {"name": "From", "value": "Alice <alice@example.com>"},
                {"name": "Subject", "value": "Hello"},
                {"name": "To", "value": "bob@example.com"},
                {"name": "Date", "value": "Tue, 20 May 2025 12:00:00 +0000"},
            ]
        },
    }
    stored = _gmail_payload_to_stored(payload)
    assert stored.id == "m1"
    assert stored.thread_id == "t1"
    assert stored.from_addr == "alice@example.com"
    assert stored.from_name == "Alice"
    assert stored.subject == "Hello"
    assert stored.to_addrs == ["bob@example.com"]
    assert stored.is_unread is True
    assert stored.is_sent is False
    assert stored.snippet == "short preview"


def test_gmail_payload_to_stored_sent_flag() -> None:
    payload = {
        "id": "m2",
        "threadId": "t2",
        "historyId": "101",
        "snippet": "",
        "labelIds": ["SENT"],
        "internalDate": "1747731600000",
        "payload": {"headers": []},
    }
    stored = _gmail_payload_to_stored(payload)
    assert stored.is_sent is True
    assert stored.is_unread is False


def test_gmail_payload_to_stored_missing_headers() -> None:
    payload = {
        "id": "m3",
        "threadId": "t3",
        "historyId": "0",
        "snippet": "",
        "labelIds": [],
        "internalDate": "0",
        "payload": {"headers": []},
    }
    stored = _gmail_payload_to_stored(payload)
    assert stored.from_addr == ""
    assert stored.subject == ""
    assert stored.to_addrs == []
