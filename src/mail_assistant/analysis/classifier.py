from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources

from mail_assistant.analysis.categories import Classification
from mail_assistant.analysis.llm import LLMClient
from mail_assistant.store.db import Database
from mail_assistant.store.models import StoredMessage


def _load_system_prompt() -> str:
    return (
        resources.files("mail_assistant.analysis.prompts")
        .joinpath("classifier_system.md")
        .read_text(encoding="utf-8")
    )


CLASSIFIER_SYSTEM_PROMPT = _load_system_prompt()


@dataclass(frozen=True)
class ClassifyReport:
    classified: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def build_user_message(message: StoredMessage) -> str:
    body = message.body_text if message.body_text else "<body not yet fetched>"
    return (
        f"From: {message.from_name} <{message.from_addr}>\n"
        f"To: {', '.join(message.to_addrs) if message.to_addrs else '(unknown)'}\n"
        f"Subject: {message.subject}\n"
        f"Date: {message.date.isoformat()}\n"
        f"Labels: {', '.join(message.labels)}\n"
        f"Snippet: {message.snippet}\n"
        f"\n"
        f"Body:\n{body}"
    )


class ClassifierError(Exception):
    pass


def classify_message(llm: LLMClient, message: StoredMessage) -> Classification:
    """Single LLM call returning a structured Classification.

    Disabled thinking + low effort: classification is a per-message task, high
    volume, low per-call stakes; thinking adds latency and tokens for no real
    accuracy gain. If the user later wants higher accuracy on edge cases, flip
    to adaptive thinking in settings.
    """
    response = llm.client.messages.parse(
        model=llm.model,
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": CLASSIFIER_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": build_user_message(message)}],
        output_format=Classification,
        thinking={"type": "disabled"},
        output_config={"effort": "low"},
    )
    parsed = response.parsed_output
    if parsed is None:
        raise ClassifierError(
            f"Claude returned no parsed output for message {message.id}. "
            f"stop_reason={response.stop_reason!r}."
        )
    return parsed


# Type alias for dependency injection in tests
ClassifyFn = Callable[[LLMClient, StoredMessage], Classification]


def classify_pending(
    db: Database,
    llm: LLMClient,
    limit: int = 50,
    classify_fn: ClassifyFn = classify_message,
) -> ClassifyReport:
    """Classify up to `limit` messages that have no classification yet."""
    from mail_assistant.store import classifications as classifications_repo

    pending = classifications_repo.list_unclassified(db, limit=limit)
    classified = 0
    errors: list[str] = []
    for msg in pending:
        try:
            classification = classify_fn(llm, msg)
        except Exception as e:
            errors.append(f"{msg.id}: {e}")
            continue
        classifications_repo.upsert(db, msg.id, classification, model=llm.model)
        classified += 1
    return ClassifyReport(classified=classified, skipped=0, errors=errors)
