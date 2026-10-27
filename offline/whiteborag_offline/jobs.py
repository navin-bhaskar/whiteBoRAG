"""The ingest queue: a table in the same SQLite file, standing in for SQS."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from whiteborag_offline.store import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, s3_key TEXT NOT NULL, status TEXT NOT NULL,
    error TEXT, outcome_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
"""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class JobQueue:
    def __init__(self, path: Path | str) -> None:
        self.conn = connect(path)
        self.lock = threading.Lock()
        self.conn.executescript(SCHEMA)

    def _set(self, job_id: int, **fields) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.lock:
            self.conn.execute(f"UPDATE jobs SET {cols}, updated_at = ? WHERE id = ?", (*fields.values(), _now(), job_id))

    def enqueue(self, s3_key: str) -> int:
        with self.lock:
            now = _now()
            cur = self.conn.execute("INSERT INTO jobs (s3_key, status, created_at, updated_at) VALUES (?, 'queued', ?, ?)",
                                    (s3_key, now, now))
            return cur.lastrowid

    def claim(self) -> tuple[int, str] | None:
        """The oldest queued job, now marked running."""
        with self.lock:
            row = self.conn.execute("SELECT id, s3_key FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
            if row is None:
                return None
            self.conn.execute("UPDATE jobs SET status = 'running', updated_at = ? WHERE id = ?", (_now(), row[0]))
            return row[0], row[1]

    def finish(self, job_id: int, outcome: dict) -> None:
        self._set(job_id, status="done", outcome_json=json.dumps(outcome))

    def fail(self, job_id: int, error: str) -> None:
        self._set(job_id, status="failed", error=error)

    def requeue_running(self) -> int:
        """Jobs a crashed or stopped server left running go back in the queue."""
        with self.lock:
            return self.conn.execute("UPDATE jobs SET status = 'queued', updated_at = ? WHERE status = 'running'",
                                     (_now(),)).rowcount

    def requeue_failed(self) -> int:
        """Failed jobs (the model server was down, say) go back in the queue."""
        with self.lock:
            return self.conn.execute("UPDATE jobs SET status = 'queued', error = NULL, updated_at = ? "
                                     "WHERE status = 'failed'", (_now(),)).rowcount

    def recent(self, limit: int = 50) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, s3_key, status, error, outcome_json, created_at, updated_at FROM jobs ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        return [{"id": i, "s3_key": k, "status": s, "error": e, "outcome": json.loads(o) if o else None,
                 "created_at": c, "updated_at": u} for i, k, s, e, o, c, u in rows]
