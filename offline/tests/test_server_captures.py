import pytest
from fastapi.testclient import TestClient

import whiteborag_offline  # noqa: F401
from ingest.events import parse_key

from fakes import FakeLlm
from helpers import JPEG, board_replies, runtime
from whiteborag_offline.llm import LlmError
from whiteborag_offline.server import create_app

DEVICE_KEY = "change-me-device-key"


def _app(tmp_path, llm=None):
    rt = runtime(tmp_path, llm)
    return create_app(rt.cfg, rt=rt, start_worker=False), rt


def _post(client, body=JPEG, key=DEVICE_KEY):
    headers = {"Content-Type": "image/jpeg", "X-Trigger": "ir"}
    if key is not None:
        headers["X-Device-Key"] = key
    return client.post("/captures", content=body, headers=headers)


def test_capture_saved_and_enqueued(tmp_path):
    app, rt = _app(tmp_path)
    with TestClient(app) as client:
        resp = _post(client)
        assert resp.status_code == 201
        body = resp.json()
        assert rt.blobs.get_bytes(body["key"]) == JPEG
        assert body["key"].startswith("captures/cam-01/")
        assert (tmp_path / "uploads" / body["key"].removeprefix("captures/")).exists()
        (job,) = client.get("/jobs").json()
        assert (job["id"], job["status"], job["s3_key"]) == (body["job_id"], "queued", body["key"])


def test_generated_key_matches_ingest_regex(tmp_path):
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        body = _post(client).json()
    capture = parse_key(body["key"])
    assert capture is not None
    assert capture.capture_id == body["capture_id"]
    assert capture.device == "cam-01"


@pytest.mark.parametrize("key", [None, "wrong-key"])
def test_unknown_device_key_403(tmp_path, key):
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        assert _post(client, key=key).status_code == 403
        assert client.get("/jobs").json() == []


@pytest.mark.parametrize("body", [b"", b"GIF89a not a jpeg", b"\xff\xd8" + b"0" * (5 * 1024 * 1024)],
                         ids=["empty", "not-jpeg", "too-large"])
def test_bad_body_400_and_nothing_written(tmp_path, body):
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        assert _post(client, body=body).status_code == 400
        assert client.get("/jobs").json() == []
    assert list((tmp_path / "uploads").rglob("*.jpg")) == []


def test_worker_ingests_queued_capture(tmp_path):
    app, rt = _app(tmp_path)
    with TestClient(app) as client:
        body = _post(client).json()
        assert app.state.worker.run_once() is True
        (job,) = client.get("/jobs").json()
    assert job["status"] == "done"
    assert job["outcome"]["status"] == "ingested"
    assert rt.store.get_capture(body["capture_id"]) is not None


def test_worker_marks_failed_on_llm_error_and_continues(tmp_path):
    replies = board_replies()
    state = {"fail": True}

    def flaky(call):
        if state["fail"]:
            return LlmError("model server unreachable")
        return replies(call)

    app, rt = _app(tmp_path, FakeLlm(flaky))
    with TestClient(app) as client:
        first = _post(client).json()
        assert app.state.worker.run_once() is True
        state["fail"] = False
        second = _post(client).json()
        assert app.state.worker.run_once() is True
        jobs = {j["id"]: j for j in client.get("/jobs").json()}
    assert jobs[first["job_id"]]["status"] == "failed"
    assert "model server unreachable" in jobs[first["job_id"]]["error"]
    assert jobs[second["job_id"]]["status"] == "done"
    assert rt.blobs.get_bytes(first["key"]) == JPEG  # nothing half-deleted
    assert app.state.worker.run_once() is False


def test_requeue_running_on_start(tmp_path):
    app, _ = _app(tmp_path)
    queue = app.state.queue
    job_id = queue.enqueue("captures/cam-01/2026/10/24/20261024T100000Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg")
    queue.claim()  # the server died mid-job
    app.state.worker.start()
    app.state.worker.stop()
    assert {j["id"]: j["status"] for j in queue.recent()}[job_id] != "running"


def test_health(tmp_path):
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"ok": True}
