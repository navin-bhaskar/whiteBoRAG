"""An in-memory Store with the same conditional-write semantics as the DynamoDB one."""

from copy import deepcopy

from ingest.pipeline import Reply
from ingest.store import CaptureRecord, Conflict, Link, Project
from ingest.todos import TodoItem


class InMemoryStore:
    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}
        self.links: dict[tuple[str, str, str], Link] = {}
        self.todos: dict[tuple[str, str], TodoItem] = {}
        self.captures: dict[str, CaptureRecord] = {}
        # Set to a Project to simulate another Lambda creating it just before our create_project.
        self.fail_next_create: Project | None = None
        # Set to True to make the next save_todo lose, as if another Lambda wrote the todo first.
        self.fail_next_save_todo = False

    def list_projects(self) -> list[Project]:
        return [deepcopy(p) for p in self.projects.values()]

    def get_project(self, key: str) -> Project | None:
        return deepcopy(self.projects.get(key))

    def create_project(self, p: Project) -> None:
        if self.fail_next_create is not None:
            winner, self.fail_next_create = self.fail_next_create, None
            self.projects[winner.key] = deepcopy(winner)
        if p.key in self.projects:
            raise Conflict(f"project {p.key} exists")
        self.projects[p.key] = deepcopy(p)

    def save_project(self, p: Project) -> None:
        stored = self.projects.get(p.key)
        if stored is None or stored.version != p.version:
            raise Conflict(f"project {p.key} changed")
        self.projects[p.key] = deepcopy(p)
        self.projects[p.key].version += 1

    def delete_project(self, key: str, version: int) -> None:
        stored = self.projects.get(key)
        if stored is not None and stored.version != version:
            raise Conflict(f"project {key} changed")
        self.projects.pop(key, None)

    def project_links(self, key: str) -> list[Link]:
        return sorted((l for l in self.links.values() if l.project_key == key), key=lambda l: l.captured_at)

    def put_link(self, link: Link) -> None:
        self.links[(link.project_key, link.captured_at, link.capture_id)] = link

    def delete_link(self, link: Link) -> None:
        self.links.pop((link.project_key, link.captured_at, link.capture_id), None)

    def list_todos(self, project_key: str) -> list[TodoItem]:
        return [deepcopy(t) for (pk, _), t in self.todos.items() if pk == project_key]

    def save_todo(self, project_key: str, item: TodoItem) -> None:
        if self.fail_next_save_todo:
            self.fail_next_save_todo = False
            raise Conflict(f"todo {item.todo_id} changed")
        stored = self.todos.get((project_key, item.todo_id))
        if (stored is None) != (item.version == 0) or (stored is not None and stored.version != item.version):
            raise Conflict(f"todo {item.todo_id} changed")
        self.todos[(project_key, item.todo_id)] = deepcopy(item)
        self.todos[(project_key, item.todo_id)].version += 1

    def delete_todo(self, project_key: str, todo_id: str, version: int) -> None:
        stored = self.todos.get((project_key, todo_id))
        if stored is not None and stored.version != version:
            raise Conflict(f"todo {todo_id} changed")
        self.todos.pop((project_key, todo_id), None)

    def get_capture(self, capture_id: str) -> CaptureRecord | None:
        return deepcopy(self.captures.get(capture_id))

    def put_capture(self, rec: CaptureRecord) -> None:
        self.captures[rec.capture_id] = deepcopy(rec)


class FakeBlobs:
    def __init__(self, files: dict[str, bytes | str] | None = None) -> None:
        self.files: dict[str, bytes | str] = dict(files or {})

    def get_bytes(self, key: str) -> bytes | None:
        value = self.files.get(key)
        return value if isinstance(value, bytes) else None

    def get_text(self, key: str) -> str | None:
        value = self.files.get(key)
        return value if isinstance(value, str) else None

    def put_text(self, key: str, text: str) -> None:
        self.files[key] = text


class FakeReader:
    """Returns canned replies and counts its calls."""

    def __init__(self, transcript: Reply, normalized: Reply) -> None:
        self.transcript = transcript
        self.normalized = normalized
        self.calls = 0
        self.prompts: list[str] = []

    def transcribe(self, image: bytes) -> Reply:
        self.calls += 1
        return self.transcript

    def normalize(self, prompt: str) -> Reply:
        self.calls += 1
        self.prompts.append(prompt)
        return self.normalized


class FakeEmbedder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.texts.append(text)
        return [float(len(text)), 1.0]


class FakeVectors:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}

    def put(self, records: list[dict]) -> None:
        self.records.update({r["key"]: deepcopy(r) for r in records})

    def delete(self, keys: list[str]) -> None:
        for key in keys:
            self.records.pop(key, None)

    def get(self, keys: list[str]) -> list[dict]:
        return [deepcopy(self.records[k]) for k in keys if k in self.records]
