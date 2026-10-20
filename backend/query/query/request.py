"""POST /query request body: the question, the page's recent turns and an optional project key."""

import base64
import binascii
import json
from dataclasses import dataclass

MAX_QUESTION = 500
MAX_HISTORY = 6


class BadRequest(ValueError):
    pass


@dataclass(frozen=True)
class Turn:
    question: str
    understood: dict
    answer: str | None
    sources: list[dict]


@dataclass(frozen=True)
class Request:
    question: str
    history: list[Turn]
    project: str | None


def _body(event: dict) -> dict:
    body = event.get("body")
    if not body:
        raise BadRequest("request body is required")
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body, validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            raise BadRequest("body is not valid base64")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise BadRequest("body is not valid JSON")
    if not isinstance(data, dict):
        raise BadRequest("body must be a JSON object")
    return data


def _turn(raw) -> Turn | None:
    """One history turn as the page sent it, or None if it is junk."""
    if not isinstance(raw, dict) or not isinstance(raw.get("question"), str):
        return None
    understood = raw.get("understood")
    answer = raw.get("answer")
    sources = raw.get("sources")
    return Turn(
        question=raw["question"],
        understood=understood if isinstance(understood, dict) else {},
        answer=answer if isinstance(answer, str) else None,
        sources=[s for s in sources if isinstance(s, dict)] if isinstance(sources, list) else [],
    )


def parse_request(event: dict) -> Request:
    data = _body(event)

    question = data.get("question")
    if not isinstance(question, str) or not question.strip():
        raise BadRequest("question is required")
    question = question.strip()
    if len(question) > MAX_QUESTION:
        raise BadRequest(f"question must be at most {MAX_QUESTION} characters")

    history = data.get("history", [])
    if history is None:
        history = []
    if not isinstance(history, list):
        raise BadRequest("history must be a list")
    turns = [t for t in map(_turn, history) if t is not None][-MAX_HISTORY:]

    project = data.get("project")
    if project is not None and not isinstance(project, str):
        raise BadRequest("project must be a project key")

    return Request(question=question, history=turns, project=project or None)
