"""The ingest steps that write through a Store (spec §4.5–4.7)."""

from datetime import datetime, timezone
from typing import Callable

from ingest.projects import canonical_key, match_project, summarize
from ingest.store import CaptureRecord, Conflict, Link, Project, Store, with_retries


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
