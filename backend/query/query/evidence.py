"""Evidence boards for todos and diagram questions (spec §5.3), read straight from the store and S3."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice

from ingest.normalize import NormalizationError, parse_response
from ingest.pipeline import Blobs
from ingest.store import CaptureRecord, Link, Store
from query.understand import Intent

MAX_TODO_BOARDS = 5
MAX_HISTORY_BOARDS = 10

NOTHING = {
    "todos": "{name} has no boards with todos yet.",
    "diagram_latest": "{name} has no boards with a diagram yet.",
    "diagram_history": "{name} has no boards with a diagram yet.",
    "search": "I couldn't find anything about that on your boards.",
    "empty": "There are no boards yet. Take a snap and ask again.",
}


@dataclass(frozen=True)
class Board:
    capture_id: str
    captured_at: str
    date: str
    s3_key: str
    project: str | None
    section: str
    text: str
    todos: list[dict] | None = None
    diff: dict | None = None


def board_text(blobs: Blobs, rec: CaptureRecord) -> str | None:
    """The board's normalized transcript without its `Project:` header, or the verbatim one if that was rejected."""
    if rec.normalization_rejected:
        return blobs.get_text(rec.transcript_key)
    reply = blobs.get_text(rec.normalized_key)
    if reply is None:
        return None
    try:
        return parse_response(reply)[1]
    except NormalizationError:
        return blobs.get_text(rec.transcript_key)


def _edge_key(edge: dict) -> tuple[str, str, str]:
    return tuple((edge.get(part) or "").strip().lower() for part in ("src", "dst", "label"))


def edge_diff(prev: list[dict], cur: list[dict]) -> dict:
    before, after = {_edge_key(e) for e in prev}, {_edge_key(e) for e in cur}
    return {
        "added": [e for e in cur if _edge_key(e) not in before],
        "removed": [e for e in prev if _edge_key(e) not in after],
    }


def _instant(timestamp: str) -> datetime:
    at = datetime.fromisoformat(timestamp)
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _links(store: Store, project: str, intent: Intent) -> list[Link]:
    """The project's capture links within the question's date filters, newest first."""
    before = _instant(intent.before) if intent.before else None
    return [
        link
        for link in reversed(store.project_links(project))
        if (intent.date_from is None or link.date >= intent.date_from)
        and (intent.date_to is None or link.date <= intent.date_to)
        and (before is None or _instant(link.captured_at) < before)
    ]


def _records(store: Store, blobs: Blobs, project: str, intent: Intent, wanted: Callable[[CaptureRecord], bool]):
    """(record, text) per wanted record newest first, skipping links whose record or transcript is gone.

    The transcript is read only for wanted records, so walking past boards without todos costs no S3 read.
    """
    for link in _links(store, project, intent):
        rec = store.get_capture(link.capture_id)
        if rec is None or not wanted(rec):
            continue
        text = board_text(blobs, rec)
        if text is not None:
            yield rec, text


def _board(rec: CaptureRecord, section: str, text: str, **parts) -> Board:
    return Board(rec.capture_id, rec.captured_at, rec.date, rec.s3_key, rec.project, section, text, **parts)


def _todos_as_on(store: Store, project: str, rec: CaptureRecord) -> list[dict]:
    """Each of the board's todos as written and ticked on that board, plus when it was done since."""
    items = {item.todo_id: item for item in store.list_todos(project)}
    todos = []
    for todo_id in rec.todo_ids:
        item = items.get(todo_id)
        sighting = item.sightings.get(rec.capture_id) if item else None
        if sighting is None:
            continue
        done_later = item.state == "done" and item.completed_on is not None and item.completed_on > rec.date
        todos.append(
            {"text": sighting.text_as_seen, "checked": sighting.checked, "done_since": item.completed_on if done_later else None}
        )
    return todos


def todo_boards(store: Store, blobs: Blobs, project: str, intent: Intent) -> list[Board]:
    """The newest board with todos, or with a date range every such board in it (newest first, up to 5)."""
    limit = MAX_TODO_BOARDS if intent.date_from or intent.date_to else 1
    boards = []
    for rec, text in _records(store, blobs, project, intent, lambda rec: bool(rec.todo_ids)):
        boards.append(_board(rec, "todos", text, todos=_todos_as_on(store, project, rec)))
        if len(boards) == limit:
            break
    return boards


def latest_diagram(store: Store, blobs: Blobs, project: str, intent: Intent) -> list[Board]:
    for rec, text in _records(store, blobs, project, intent, lambda rec: bool(rec.edges)):
        return [_board(rec, "diagram", text)]
    return []


def diagram_history(store: Store, blobs: Blobs, project: str, intent: Intent) -> list[Board]:
    """The most recent 10 boards with a diagram, oldest first, each with its edge diff from the board before."""
    # One extra board, so the oldest board shown still gets its diff.
    newest_first = _records(store, blobs, project, intent, lambda rec: bool(rec.edges))
    found = list(islice(newest_first, MAX_HISTORY_BOARDS + 1))[::-1]
    boards = [
        _board(rec, "diagram", text, diff=edge_diff(found[i - 1][0].edges, rec.edges) if i else None)
        for i, (rec, text) in enumerate(found)
    ]
    return boards[-MAX_HISTORY_BOARDS:]


def latest_project(store: Store) -> str | None:
    """The project of the most recent capture that has one."""
    newest = [links[-1] for p in store.list_projects() if (links := store.project_links(p.key))]
    return max(newest, key=lambda link: link.captured_at).project_key if newest else None
