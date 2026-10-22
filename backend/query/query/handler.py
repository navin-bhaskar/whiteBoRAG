"""The POST /query Lambda entry point (spec §3): understand, resolve, gather, answer, sign. One JSON log line per request."""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ingest.events import LOCAL_TZ
from ingest.pipeline import Blobs, Embedder, Reply
from ingest.store import Store
from query import answer, evidence, understand
from query.evidence import NOTHING, Board, VectorSearch
from query.request import BadRequest, parse_request
from query.resolve import resolve
from query.response import respond

UNDERSTAND_MAX_TOKENS = 300


class Llm(Protocol):
    def ask(self, prompt: str, max_tokens: int) -> Reply: ...


@dataclass
class Deps:
    store: Store
    blobs: Blobs
    llm: Llm
    embedder: Embedder
    search: VectorSearch
    sign: Callable[[str], str]
    query_key_id: str
    origin: str


_deps: Deps | None = None  # Built on the first invocation, reused while the Lambda stays warm.


def _log(**fields) -> None:
    print(json.dumps(fields), flush=True)


def _today() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


def _gather(deps: Deps, question: str, intent: understand.Intent, project: str | None) -> list[Board]:
    if intent.intent == "search":
        return evidence.search_boards(deps.embedder, deps.search, question, project, intent)
    if project is None:
        return []
    find = {
        "todos": evidence.todo_boards,
        "board_latest": evidence.latest_board,
        "diagram_latest": evidence.latest_diagram,
        "diagram_history": evidence.diagram_history,
    }[intent.intent]
    return find(deps.store, deps.blobs, project, intent)


def _answer(deps: Deps, today: Callable[[], str], event: dict, log: dict) -> dict:
    req = parse_request(event)
    log["question_length"] = len(req.question)
    projects = deps.store.list_projects()
    by_key = {p.key: p for p in projects}

    reply = deps.llm.ask(
        understand.build_prompt(req.question, req.history, [p.display_name for p in projects], today()),
        UNDERSTAND_MAX_TOKENS,
    )
    intent = understand.parse_intent(reply.text, req.history)
    resolution = resolve(
        intent.project_name, intent.intent, req.project, req.history, projects,
        lambda: evidence.latest_project(deps.store), follow_up=intent.follow_up,
    )
    key = resolution.project
    log.update(intent=intent.intent, project=key, how=resolution.how)
    project = {"key": key, "display_name": by_key[key].display_name, "how": resolution.how} if key else None
    result = {
        "answer": None,
        "project": project,
        "understood": {**intent.as_dict(), "project": key},
        "sources": [],
        "clarify": resolution.clarify,
    }
    if resolution.clarify:
        return result

    boards = _gather(deps, req.question, intent, key)
    log["sources"] = len(boards)
    if not boards:
        if not projects:
            result["answer"] = NOTHING["empty"]
        elif intent.intent == "search" or project is None:
            result["answer"] = NOTHING["search"]
        else:
            result["answer"] = NOTHING[intent.intent].format(name=project["display_name"])
        return result

    reply = deps.llm.ask(
        answer.build_prompt(req.question, intent, project, resolution.how, req.history, boards), answer.MAX_TOKENS
    )
    result["answer"] = reply.text.strip() if reply.text and reply.text.strip() and not reply.truncated else answer.FALLBACK
    result["sources"] = [
        {
            "capture_id": b.capture_id,
            "captured_at": b.captured_at,
            "date": b.date,
            "project": by_key[b.project].display_name if b.project in by_key else None,
            "section": b.section,
            "image_url": deps.sign(b.s3_key),
        }
        for b in sorted(boards, key=lambda b: b.captured_at, reverse=True)
    ]
    return result


def handle(event: dict, deps: Deps, today: Callable[[], str]) -> dict:
    started = time.monotonic()
    log: dict = {"status": 200}
    try:
        key_id = ((event.get("requestContext") or {}).get("identity") or {}).get("apiKeyId")
        if key_id != deps.query_key_id:
            log["status"] = 403
            return respond(403, {"error": "forbidden"}, deps.origin)
        try:
            return respond(200, _answer(deps, today, event, log), deps.origin)
        except BadRequest as exc:
            log.update(status=400, error=str(exc))
            return respond(400, {"error": str(exc)}, deps.origin)
        except Exception as exc:  # Bedrock, DynamoDB or S3 failing: the page still gets a readable error.
            log.update(status=500, error=repr(exc))
            return respond(500, {"error": "something went wrong"}, deps.origin)
    finally:
        log["latency_ms"] = round((time.monotonic() - started) * 1000)
        if (tokens := getattr(deps.llm, "tokens", None)) is not None:
            log["tokens"] = tokens()
        _log(**log)


def lambda_handler(event, context) -> dict:
    global _deps
    if _deps is None:
        from query.aws import build_deps

        _deps = build_deps()
    return handle(event, _deps, _today)
