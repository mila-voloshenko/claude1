from mail_assistant.google_apis.scopes import READ_SCOPES

FORBIDDEN_SUBSTRINGS = (
    "gmail.send",
    "gmail.compose",
    "gmail.modify",
    "auth/calendar.events",
    "auth/calendar ",
)


def test_no_write_scopes() -> None:
    for scope in READ_SCOPES:
        for fs in FORBIDDEN_SUBSTRINGS:
            assert fs not in scope, f"Forbidden substring {fs!r} found in scope {scope!r}"


def test_only_readonly_scopes() -> None:
    for scope in READ_SCOPES:
        assert scope.endswith(".readonly"), f"Non-readonly scope: {scope!r}"
