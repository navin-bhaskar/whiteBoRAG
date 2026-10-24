"""SQLite implementation of ingest's Store protocol, with the same conditional writes on `version`."""

import json
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import asdict
from functools import wraps
from pathlib import Path

from ingest.store import CaptureRecord, Conflict, Link, Project
from ingest.todos import Sighting, TodoItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (key TEXT PRIMARY KEY, json TEXT NOT NULL, version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS links (
    project_key TEXT NOT NULL, captured_at TEXT NOT NULL, capture_id TEXT NOT NULL, json TEXT NOT NULL,
    PRIMARY KEY (project_key, captured_at, capture_id));
CREATE TABLE IF NOT EXISTS todos (
    project_key TEXT NOT NULL, todo_id TEXT NOT NULL, json TEXT NOT NULL, version INTEGER NOT NULL,
    PRIMARY KEY (project_key, todo_id));
CREATE TABLE IF NOT EXISTS captures (capture_id TEXT PRIMARY KEY, json TEXT NOT NULL);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    """One connection shared by the worker thread and request threads; callers hold a lock around each use."""
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=30)
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _locked(method: Callable) -> Callable:
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapper


def _todo(raw: str, version: int) -> TodoItem:
    data = json.loads(raw)
    data["sightings"] = {k: Sighting(**s) for k, s in data["sightings"].items()}
    return TodoItem(**{**data, "version": version})


class SqliteStore:
    def __init__(self, path: Path | str) -> None:
        self.conn = connect(path)
        self.lock = threading.Lock()
        self.conn.executescript(SCHEMA)

    def _one(self, sql: str, *params) -> tuple | None:
        return self.conn.execute(sql, params).fetchone()

    # Projects

    @_locked
    def list_projects(self) -> list[Project]:
        return [Project(**{**json.loads(j), "version": v})
                for j, v in self.conn.execute("SELECT json, version FROM projects ORDER BY key")]

    @_locked
    def get_project(self, key: str) -> Project | None:
        row = self._one("SELECT json, version FROM projects WHERE key = ?", key)
        return Project(**{**json.loads(row[0]), "version": row[1]}) if row else None

    @_locked
    def create_project(self, p: Project) -> None:
        try:
            self.conn.execute("INSERT INTO projects VALUES (?, ?, ?)", (p.key, json.dumps(asdict(p)), p.version))
        except sqlite3.IntegrityError as exc:
            raise Conflict(f"project {p.key} exists") from exc

    @_locked
    def save_project(self, p: Project) -> None:
        cur = self.conn.execute("UPDATE projects SET json = ?, version = ? WHERE key = ? AND version = ?",
                                (json.dumps(asdict(p)), p.version + 1, p.key, p.version))
        if cur.rowcount != 1:
            raise Conflict(f"project {p.key} changed")

    @_locked
    def delete_project(self, key: str, version: int) -> None:
        row = self._one("SELECT version FROM projects WHERE key = ?", key)
        if row is not None and row[0] != version:
            raise Conflict(f"project {key} changed")
        self.conn.execute("DELETE FROM projects WHERE key = ? AND version = ?", (key, version))

    # Links

    @_locked
    def project_links(self, key: str) -> list[Link]:
        rows = self.conn.execute("SELECT json FROM links WHERE project_key = ? ORDER BY captured_at, capture_id",
                                 (key,))
        return [Link(**json.loads(j)) for (j,) in rows]

    @_locked
    def put_link(self, link: Link) -> None:
        self.conn.execute("INSERT OR REPLACE INTO links VALUES (?, ?, ?, ?)",
                          (link.project_key, link.captured_at, link.capture_id, json.dumps(asdict(link))))

    @_locked
    def delete_link(self, link: Link) -> None:
        self.conn.execute("DELETE FROM links WHERE project_key = ? AND captured_at = ? AND capture_id = ?",
                          (link.project_key, link.captured_at, link.capture_id))

    # Todos

    @_locked
    def list_todos(self, project_key: str) -> list[TodoItem]:
        rows = self.conn.execute("SELECT json, version FROM todos WHERE project_key = ? ORDER BY todo_id",
                                 (project_key,))
        return [_todo(j, v) for j, v in rows]

    @_locked
    def save_todo(self, project_key: str, item: TodoItem) -> None:
        raw = json.dumps(asdict(item))
        if item.version == 0:
            try:
                self.conn.execute("INSERT INTO todos VALUES (?, ?, ?, 1)", (project_key, item.todo_id, raw))
            except sqlite3.IntegrityError as exc:
                raise Conflict(f"todo {item.todo_id} changed") from exc
            return
        cur = self.conn.execute(
            "UPDATE todos SET json = ?, version = ? WHERE project_key = ? AND todo_id = ? AND version = ?",
            (raw, item.version + 1, project_key, item.todo_id, item.version))
        if cur.rowcount != 1:
            raise Conflict(f"todo {item.todo_id} changed")

    @_locked
    def delete_todo(self, project_key: str, todo_id: str, version: int) -> None:
        row = self._one("SELECT version FROM todos WHERE project_key = ? AND todo_id = ?", project_key, todo_id)
        if row is not None and row[0] != version:
            raise Conflict(f"todo {todo_id} changed")
        self.conn.execute("DELETE FROM todos WHERE project_key = ? AND todo_id = ?", (project_key, todo_id))

    # Captures

    @_locked
    def get_capture(self, capture_id: str) -> CaptureRecord | None:
        row = self._one("SELECT json FROM captures WHERE capture_id = ?", capture_id)
        return CaptureRecord(**json.loads(row[0])) if row else None

    @_locked
    def put_capture(self, rec: CaptureRecord) -> None:
        self.conn.execute("INSERT OR REPLACE INTO captures VALUES (?, ?)", (rec.capture_id, json.dumps(asdict(rec))))

    @_locked
    def delete_capture(self, capture_id: str) -> None:
        self.conn.execute("DELETE FROM captures WHERE capture_id = ?", (capture_id,))
