"""What a question asks for (spec §5.1): the prompt and the reply parser. A reply we can't read becomes a plain search."""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from ingest.normalize import strip_fence
from query.request import Turn

log = logging.getLogger(__name__)

PROMPT_VERSION = "understand-v2"
PROMPT = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
INTENTS = ("todos", "board_latest", "diagram_latest", "diagram_history", "search")
SECTIONS = ("todos", "diagram", "notes")


@dataclass(frozen=True)
class Intent:
    intent: str
    project_name: str | None
    section: str | None
    date_from: str | None
    date_to: str | None
    before: str | None
    follow_up: bool

    def as_dict(self) -> dict:
        return asdict(self)


SEARCH = Intent("search", None, None, None, None, None, False)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "(none yet)"


def _history(history: list[Turn]) -> str:
    """Questions, what we understood and when the sources were captured. Never the answers."""
    lines = []
    for turn in history:
        dates = ", ".join(s["captured_at"] for s in turn.sources if isinstance(s.get("captured_at"), str))
        lines.append(
            f'Question "{turn.question}", understood {json.dumps(turn.understood, ensure_ascii=False)}, '
            f"sources captured at {dates or '(none)'}"
        )
    return "\n".join(lines) or "(none)"


def build_prompt(question: str, history: list[Turn], project_names: list[str], today: str) -> str:
    return (
        PROMPT.replace("{{TODAY}}", today)
        .replace("{{PROJECTS}}", _bullets(project_names))
        .replace("{{HISTORY}}", _history(history))
        .replace("{{QUESTION}}", question.strip())
    )


def _date(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat() if len(value) == 10 else None
    except ValueError:
        return None


def _timestamp(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return value


def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def parse_intent(reply: str | None, history: list[Turn]) -> Intent:
    try:
        data = json.loads(strip_fence(reply or ""))
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or data.get("intent") not in INTENTS:
        log.warning("understand reply unusable, falling back to search (reply length %d)", len(reply or ""))
        return SEARCH

    intent = data["intent"]
    project_name = _text(data.get("project_name"))
    follow_up = data.get("follow_up") is True
    # A follow-up that names nothing and came back as a plain search keeps the previous turn's intent;
    # an explicit todos/diagram intent means the question changed what it asks for.
    if follow_up and intent == "search" and project_name is None and history:
        previous = history[-1].understood.get("intent")
        if previous in INTENTS:
            intent = previous

    section = data.get("section")
    return Intent(
        intent=intent,
        project_name=project_name,
        section=section if section in SECTIONS else None,
        date_from=_date(data.get("date_from")),
        date_to=_date(data.get("date_to")),
        before=_timestamp(data.get("before")),
        follow_up=follow_up,
    )
