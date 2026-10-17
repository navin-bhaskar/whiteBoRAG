"""The storage interface (spec §5) the pipeline writes through; DynamoDB implements it, tests use a fake."""

from dataclasses import dataclass
from typing import Callable, Protocol, TypeVar

from ingest.todos import TodoItem

T = TypeVar("T")


class Conflict(Exception):
    """A conditional write lost: the item exists already, or changed since it was read."""


@dataclass
class Project:
    key: str
    display_name: str
    aliases: dict[str, int]  # A cache of summarize() over the project's links.
    pinned_name: str | None = None
    created_at: str = ""
    version: int = 0


@dataclass(frozen=True)
class Link:
    """A capture in a project: `PROJECT#<key>` / `CAPTURE#<captured_at>#<capture_id>`."""

    project_key: str
    captured_at: str
    capture_id: str
    date: str
    title_as_seen: str
    project_name_as_seen: str


@dataclass
class CaptureRecord:
    capture_id: str
    s3_key: str
    device: str
    captured_at: str
    date: str
    project: str | None
    project_name_as_seen: str | None
    title_as_seen: str
    descriptive_name: str | None
    edges: list[dict]
    todo_ids: list[str]
    vector_keys: list[str]
    transcript_key: str
    normalized_key: str
    normalization_rejected: bool
    truncated: bool
    ingested_at: str
    prompt_versions: dict[str, str]


class Store(Protocol):
    def list_projects(self) -> list[Project]: ...
    def get_project(self, key: str) -> Project | None: ...
    def create_project(self, p: Project) -> None:
        """Raises Conflict if the project exists."""
    def save_project(self, p: Project) -> None:
        """Raises Conflict unless the stored version == p.version; stores version + 1."""
    def delete_project(self, key: str, version: int) -> None:
        """Raises Conflict unless the stored version == version, so a project another capture just joined survives."""
    def project_links(self, key: str) -> list[Link]: ...
    def put_link(self, link: Link) -> None: ...
    def delete_link(self, link: Link) -> None: ...
    def list_todos(self, project_key: str) -> list[TodoItem]: ...
    def save_todo(self, project_key: str, item: TodoItem) -> None:
        """Version 0 creates the todo if absent; otherwise a conditional write as in save_project."""
    def delete_todo(self, project_key: str, todo_id: str) -> None: ...
    def get_capture(self, capture_id: str) -> CaptureRecord | None: ...
    def put_capture(self, rec: CaptureRecord) -> None: ...


def with_retries(fn: Callable[[], T], attempts: int = 5) -> T:
    """Re-run fn, which must re-read what it changes, while it loses conditional writes."""
    for attempt in range(attempts):
        try:
            return fn()
        except Conflict:
            if attempt == attempts - 1:
                raise
    raise AssertionError("unreachable")
