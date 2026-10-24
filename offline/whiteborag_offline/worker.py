"""The background ingest loop: one job at a time, so only one model is busy at once."""

import json
import threading
from dataclasses import asdict
from datetime import UTC, datetime

from ingest.events import Job, parse_key
from ingest.pipeline import ingest_capture

from whiteborag_offline.deps import Runtime, ingest_deps
from whiteborag_offline.jobs import JobQueue


def _log(**fields) -> None:
    print(json.dumps(fields), flush=True)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Worker:
    def __init__(self, rt: Runtime, queue: JobQueue, poll_s: float = 1.0) -> None:
        self.queue, self.poll_s = queue, poll_s
        self.deps = ingest_deps(rt)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """Process the oldest queued job; False if there was none."""
        claimed = self.queue.claim()
        if claimed is None:
            return False
        job_id, key = claimed
        try:
            capture = parse_key(key)
            if capture is None:
                raise ValueError(f"not a capture key: {key}")
            outcome = asdict(ingest_capture(self.deps, Job(capture, reread=False), _now))
        except Exception as exc:  # the model server down, a bad reply: record it and move on
            self.queue.fail(job_id, repr(exc))
            _log(job=job_id, key=key, status="failed", error=repr(exc))
            return True
        self.queue.finish(job_id, outcome)
        _log(job=job_id, key=key, **outcome)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self.run_once():
                self._stop.wait(self.poll_s)

    def start(self) -> None:
        if (n := self.queue.requeue_running()):
            _log(requeued=n)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ingest-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Waits for the current job to finish."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
