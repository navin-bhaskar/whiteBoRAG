"""Todo tracking (spec §4.6): sightings per capture, derived state, and one-to-one fuzzy matching."""

from dataclasses import dataclass

from rapidfuzz import fuzz

from ingest.board import Todo

THRESHOLD = 85


@dataclass(frozen=True)
class Sighting:
    capture_id: str
    date: str
    captured_at: str
    checked: bool
    text_as_seen: str


@dataclass
class TodoItem:
    todo_id: str
    sightings: dict[str, Sighting]
    version: int = 0
    # Derived from the sightings by derive().
    text: str = ""
    first_seen: str = ""
    state: str = "open"
    completed_on: str | None = None


def derive(item: TodoItem) -> TodoItem:
    """Recompute the derived fields from the sightings, by captured_at rather than processing order."""
    ordered = sorted(item.sightings.values(), key=lambda s: (s.captured_at, s.capture_id))
    latest = ordered[-1]
    item.text = latest.text_as_seen
    item.first_seen = min(s.date for s in ordered)
    item.state = "done" if latest.checked else "open"
    item.completed_on = min(s.date for s in ordered if s.checked) if latest.checked else None
    return item


def match_todos(board: list[Todo], existing: list[TodoItem]) -> list[str | None]:
    """Per board todo, the matched existing todo_id or None; pairs are taken greedily by score, one-to-one."""
    pairs = sorted(
        (
            (score, i, item.todo_id)
            for i, todo in enumerate(board)
            for item in existing
            if (score := fuzz.ratio(todo.text.lower(), item.text.lower())) >= THRESHOLD
        ),
        key=lambda p: -p[0],
    )
    matched: list[str | None] = [None] * len(board)
    taken: set[str] = set()
    for _, i, todo_id in pairs:
        if matched[i] is None and todo_id not in taken:
            matched[i] = todo_id
            taken.add(todo_id)
    return matched
