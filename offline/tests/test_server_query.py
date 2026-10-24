import json

from fastapi.testclient import TestClient

import whiteborag_offline  # noqa: F401
from ingest.events import Job, parse_key
from ingest.pipeline import ingest_capture
from query.evidence import NOTHING

from fakes import FakeLlm
from helpers import JPEG, KEY, board_replies, runtime
from whiteborag_offline.deps import ingest_deps
from whiteborag_offline.server import create_app

INTENT = json.dumps({"intent": "todos", "project_name": "whiteBORAG", "section": None, "date_from": None,
                     "date_to": None, "before": None, "follow_up": False})


def _replies():
    board = board_replies()

    def reply(call):
        if call["prompt"].startswith("You read a question"):
            return INTENT
        if call["prompt"].startswith("You answer questions"):
            return "Three todos are open [1]."
        return board(call)
    return reply


def _app(tmp_path, ingested=True):
    rt = runtime(tmp_path, FakeLlm(_replies()))
    if ingested:
        rt.blobs.put_bytes(KEY, JPEG)
        ingest_capture(ingest_deps(rt), Job(parse_key(KEY), False), lambda: "2026-10-24T10:00:00Z")
    return create_app(rt.cfg, rt=rt, start_worker=False)


def _ask(client, question="what's left to do on WhiteBoRAG?"):
    return client.post("/query", content=json.dumps({"question": question, "history": []}),
                       headers={"Content-Type": "application/json"})


def test_query_roundtrip_returns_handler_body(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        resp = _ask(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Three todos are open [1]."
    assert body["project"]["key"] == "whiteborag"
    assert body["understood"]["intent"] == "todos"
    (source,) = body["sources"]
    assert source["image_url"] == f"http://testserver/photos/{KEY}"


def test_query_with_empty_store_is_not_500(tmp_path):
    with TestClient(_app(tmp_path, ingested=False)) as client:
        resp = _ask(client)
        search = _ask(client, "where did we write about the vector store?")
    assert resp.status_code == 200
    assert resp.json()["answer"] == NOTHING["empty"]
    assert search.status_code == 200


def test_query_bad_body_400(tmp_path):
    with TestClient(_app(tmp_path, ingested=False)) as client:
        resp = client.post("/query", content="not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_photos_serves_capture_and_404s_others(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        photo = client.get(f"/photos/{KEY}")
        assert photo.status_code == 200
        assert photo.headers["content-type"] == "image/jpeg"
        assert photo.content == JPEG
        assert client.get("/photos/transcripts/cam-01/2026/10/15/x.md").status_code == 404
        assert client.get("/photos/captures/cam-01/missing.jpg").status_code == 404
        assert client.get("/photos/captures/..%2F..%2Fwhiteborag.db").status_code == 404


def test_config_js_points_at_origin(tmp_path):
    with TestClient(_app(tmp_path, ingested=False)) as client:
        resp = client.get("/config.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert "apiUrl: location.origin" in resp.text
    assert 'apiKey: "offline"' in resp.text


def test_index_served(tmp_path):
    with TestClient(_app(tmp_path, ingested=False)) as client:
        resp = client.get("/")
        script = client.get("/app.js")
    assert resp.status_code == 200
    assert "config.js" in resp.text
    assert script.status_code == 200
