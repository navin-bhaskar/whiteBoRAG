import whiteborag_offline  # noqa: F401
from ingest.events import Job, parse_key
from ingest.pipeline import ingest_capture

from fakes import FakeLlm
from helpers import JPEG, KEY, board_replies, runtime
from whiteborag_offline.deps import ingest_deps

CAPTURE = parse_key(KEY)


def now() -> str:
    return "2026-10-24T10:00:00Z"


def _point_count(rt) -> int:
    return rt.vectors.client.count(rt.vectors.collection).count


def test_ingest_capture_end_to_end_local(tmp_path):
    rt = runtime(tmp_path)
    rt.blobs.put_bytes(KEY, JPEG)
    out = ingest_capture(ingest_deps(rt), Job(CAPTURE, reread=False), now)
    assert (out.status, out.project) == ("ingested", "whiteborag")
    assert rt.store.get_capture(CAPTURE.capture_id) is not None
    assert _point_count(rt) == out.vectors > 0
    assert (tmp_path / "derived" / CAPTURE.transcript_key).exists()
    assert (tmp_path / "uploads" / KEY.removeprefix("captures/")).exists()


def test_reingest_replaces_not_duplicates(tmp_path):
    rt = runtime(tmp_path)
    rt.blobs.put_bytes(KEY, JPEG)
    deps = ingest_deps(rt)
    ingest_capture(deps, Job(CAPTURE, reread=False), now)
    points, links = _point_count(rt), len(rt.store.project_links("whiteborag"))
    out = ingest_capture(deps, Job(CAPTURE, reread=True), now)
    assert out.status == "ingested"
    assert _point_count(rt) == points
    assert len(rt.store.project_links("whiteborag")) == links == 1


def test_unusable_photo_moved_to_rejected(tmp_path):
    rt = runtime(tmp_path, FakeLlm(board_replies(check="UNUSABLE: a hand covers the board")))
    rt.blobs.put_bytes(KEY, JPEG)
    out = ingest_capture(ingest_deps(rt), Job(CAPTURE, reread=False), now)
    assert out.status == "deleted_unusable"
    assert out.reason
    rest = KEY.removeprefix("captures/")
    assert not (tmp_path / "uploads" / rest).exists()
    assert (tmp_path / "rejected" / rest).read_bytes() == JPEG
