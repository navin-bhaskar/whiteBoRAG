"""The ingest steps that write through a Store (spec §4.5–4.7)."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from ingest import check, normalize, vectors
from ingest.board import Todo, parse_board
from ingest.events import Capture, Job
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


TRANSCRIBE_VERSION = "transcribe-v2"


class Blobs(Protocol):
    def get_bytes(self, key: str) -> bytes | None: ...
    def get_text(self, key: str) -> str | None: ...
    def put_text(self, key: str, text: str) -> None: ...
    def delete(self, key: str) -> None: ...


@dataclass(frozen=True)
class Reply:
    text: str | None  # None: the model returned no text
    truncated: bool


class Reader(Protocol):
    def check(self, image: bytes) -> Reply: ...
    def transcribe(self, image: bytes) -> Reply: ...
    def normalize(self, prompt: str) -> Reply: ...


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class VectorIndex(Protocol):
    def put(self, records: list[dict]) -> None: ...
    def delete(self, keys: list[str]) -> None: ...
    def get(self, keys: list[str]) -> list[dict]: ...


@dataclass
class Deps:
    store: Store
    blobs: Blobs
    reader: Reader
    embedder: Embedder
    vectors: VectorIndex


@dataclass(frozen=True)
class Outcome:
    status: str  # "ingested", "skipped_missing_image" or "deleted_unusable"
    capture_id: str
    project: str | None = None
    todos: int = 0
    vectors: int = 0
    normalization_rejected: bool = False
    reused: bool = False
    reason: str | None = None  # why the model judged the photo unusable


def _normalize_prompt(store: Store, verbatim: str) -> str:
    projects = store.list_projects()
    todo_texts = [t.text for p in projects for t in store.list_todos(p.key)]
    return normalize.build_prompt(verbatim, [p.display_name for p in projects], todo_texts)


def undo_previous(store: Store, old: CaptureRecord) -> None:
    """Undo a capture's previous project link and todo sightings."""
    if old.project is not None:
        remove_sightings(store, old.project, old.capture_id, old.todo_ids)
    remove_from_project(store, old)


def delete_unusable(deps: Deps, capture: Capture, old: CaptureRecord | None) -> None:
    """Remove every trace of a capture. The image goes last, so a crash midway is finished by the SQS retry."""
    if old is not None:
        undo_previous(deps.store, old)
        if old.vector_keys:
            deps.vectors.delete(old.vector_keys)
        deps.store.delete_capture(capture.capture_id)
    for key in (capture.normalized_key, capture.transcript_key, capture.s3_key):
        deps.blobs.delete(key)


def ingest_capture(deps: Deps, job: Job, now: Callable[[], str]) -> Outcome:
    """Run one capture end to end (spec §4). Safe to repeat: it undoes the previous ingest before applying."""
    store, capture = deps.store, job.capture
    old = store.get_capture(capture.capture_id)

    # 1. Read the board: reuse the stored transcript unless asked to re-read.
    verbatim = None if job.reread else deps.blobs.get_text(capture.transcript_key)
    reused = verbatim is not None
    truncated = bool(old and old.truncated) if reused else False
    if verbatim is None:
        image = deps.blobs.get_bytes(capture.s3_key)
        if image is None:
            return Outcome("skipped_missing_image", capture.capture_id)
        if (reason := check.unusable_reason(deps.reader.check(image).text)) is not None:
            delete_unusable(deps, capture, old)
            return Outcome("deleted_unusable", capture.capture_id, reason=reason)
        reply = deps.reader.transcribe(image)
        if reply.text is None:
            raise RuntimeError(f"transcription returned no text for {capture.s3_key}")
        verbatim, truncated = normalize.strip_fence(reply.text), reply.truncated
        deps.blobs.put_text(capture.transcript_key, verbatim)

    # 2–3. Normalize spelling (reused likewise), then keep it only if the guard passes.
    normalized = None if job.reread else deps.blobs.get_text(capture.normalized_key)
    if normalized is None:
        reused = False
        reply = deps.reader.normalize(_normalize_prompt(store, verbatim))
        if reply.text is not None and not reply.truncated:
            normalized = reply.text.strip()
            deps.blobs.put_text(capture.normalized_key, normalized)
    decision = normalize.decide(verbatim, normalized)

    # 4. Parse the chosen text; the title as seen always comes from the verbatim text.
    board = parse_board(decision.chosen)
    title_as_seen = parse_board(verbatim).title

    # 5. Undo the previous ingest of this capture, if any.
    if old is not None:
        undo_previous(store, old)

    # 6–7. Apply the project, then (only for a project) the todos.
    name = decision.project_name
    project = apply_project(
        store,
        name,
        lambda key: Link(key, capture.captured_at, capture.capture_id, capture.date, title_as_seen, name or ""),
    )
    todo_ids = apply_todos(store, project, capture, board.todos) if project else []

    # 8. One vector per section; upsert, then delete the keys this ingest no longer writes.
    display = store.get_project(project).display_name if project else None
    label = vectors.label(display, board.title, board.descriptive_name)
    embeddings = [deps.embedder.embed(vectors.embed_text(label, s)) for s in board.sections]
    records = vectors.build_records(capture, project, board.sections, embeddings)
    if records:
        deps.vectors.put(records)
    vector_keys = [r["key"] for r in records]
    if stale := vectors.stale_keys(old.vector_keys if old else [], vector_keys):
        deps.vectors.delete(stale)

    # 9. The capture record goes last: it is what the next re-ingest undoes.
    store.put_capture(
        CaptureRecord(
            capture_id=capture.capture_id,
            s3_key=capture.s3_key,
            device=capture.device,
            captured_at=capture.captured_at,
            date=capture.date,
            project=project,
            project_name_as_seen=name if project else None,
            title_as_seen=title_as_seen,
            descriptive_name=board.descriptive_name,
            edges=[{"src": e.src, "dst": e.dst, "label": e.label} for e in board.edges],
            todo_ids=todo_ids,
            vector_keys=vector_keys,
            transcript_key=capture.transcript_key,
            normalized_key=capture.normalized_key,
            normalization_rejected=decision.rejected,
            truncated=truncated,
            ingested_at=now(),
            prompt_versions={
                "check": check.PROMPT_VERSION,
                "transcribe": TRANSCRIBE_VERSION,
                "normalize": normalize.PROMPT_VERSION,
            },
        )
    )
    return Outcome(
        "ingested",
        capture.capture_id,
        project=project,
        todos=len(todo_ids),
        vectors=len(records),
        normalization_rejected=decision.rejected,
        reused=reused,
    )
