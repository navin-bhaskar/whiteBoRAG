"""The ingest steps that write through a Store (spec §4.5–4.7)."""

from datetime import datetime, timezone
from typing import Callable

from ingest.board import Todo
from ingest.events import Capture
from ingest.projects import canonical_key, match_project, summarize
from ingest.store import CaptureRecord, Conflict, Link, Project, Store, with_retries
from ingest.todos import Sighting, TodoItem, derive, match_todos
from ingest.ulid import new_ulid


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _match(store: Store, name: str) -> str | None:
    return match_project(name, {p.key: list(p.aliases) for p in store.list_projects()})


def refresh_project(store: Store, key: str) -> None:
    """Recompute aliases and the display name from the project's links; delete the project if none are left."""
    project = store.get_project(key)
    links = store.project_links(key)
    if project is None:
        if links:
            # A concurrent undo deleted it after our link went in; restore it (Conflict → with_retries re-runs).
            store.create_project(Project(key, links[0].project_name_as_seen, {}, created_at=_now()))
            project = store.get_project(key)
        else:
            return
    elif not links:
        store.delete_project(key, project.version)
        return
    project.aliases, project.display_name = summarize(
        [(link.captured_at, link.project_name_as_seen) for link in links], project.pinned_name
    )
    store.save_project(project)


def apply_project(store: Store, name: str | None, link_for: Callable[[str], Link]) -> str | None:
    """Join the best-matching project, or create one, and link this capture to it. Returns the project key."""
    if name is None or not (key := canonical_key(name)):
        return None
    project = _match(store, name)
    if project is None:
        try:
            store.create_project(Project(key, name, {}, created_at=_now()))
            project = key
        except Conflict:
            # Another capture created it first: join whatever now matches, which includes that key.
            project = _match(store, name) or key
    store.put_link(link_for(project))
    with_retries(lambda: refresh_project(store, project))
    return project


def remove_from_project(store: Store, rec: CaptureRecord) -> None:
    """Undo apply_project for a capture's previous ingest."""
    if rec.project is None:
        return
    store.delete_link(
        Link(rec.project, rec.captured_at, rec.capture_id, rec.date, rec.title_as_seen, rec.project_name_as_seen or "")
    )
    with_retries(lambda: refresh_project(store, rec.project))


def apply_todos(store: Store, project_key: str, capture: Capture, board_todos: list[Todo]) -> list[str]:
    """Record this capture's sighting on each board todo, matching known todos. Returns the todo_ids in board order."""

    def attempt() -> list[str]:
        # Re-read and re-match on every attempt, so a retry never applies a decision made on stale state.
        existing = store.list_todos(project_key)
        by_id = {item.todo_id: item for item in existing}
        ids = []
        for todo, todo_id in zip(board_todos, match_todos(board_todos, existing)):
            item = by_id[todo_id] if todo_id else TodoItem(new_ulid(), {})
            item.sightings[capture.capture_id] = Sighting(
                capture.capture_id, capture.date, capture.captured_at, todo.checked, todo.text
            )
            store.save_todo(project_key, derive(item))
            ids.append(item.todo_id)
        return ids

    return with_retries(attempt)


def remove_sightings(store: Store, project_key: str, capture_id: str, todo_ids: list[str]) -> None:
    """Undo apply_todos: drop this capture's sighting, deleting todos left with none."""

    def remove(todo_id: str) -> None:
        item = next((t for t in store.list_todos(project_key) if t.todo_id == todo_id), None)
        if item is None or item.sightings.pop(capture_id, None) is None:
            return
        if item.sightings:
            store.save_todo(project_key, derive(item))
        else:
            store.delete_todo(project_key, todo_id, item.version)

    for todo_id in todo_ids:
        with_retries(lambda: remove(todo_id))
