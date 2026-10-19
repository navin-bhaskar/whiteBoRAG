from pathlib import Path

from fakes import FakeBlobs, FakeEmbedder, FakeReader, FakeVectors, InMemoryStore
from ingest.events import Job, parse_key
from ingest.pipeline import Deps, Reply, ingest_capture

FIXTURES = Path(__file__).parent / "fixtures"
KEY = "captures/wb-cam-01/2026/10/15/20261015T084632Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg"
CAPTURE = parse_key(KEY)
CID = CAPTURE.capture_id
ARCH = (FIXTURES / "architecture.md").read_text(encoding="utf-8")
ARCH_FIXED = ARCH.replace("White BORAH", "whiteBORAG").replace("transform", "terraform")
CRAWLERS = (FIXTURES / "crawlers.md").read_text(encoding="utf-8")


def now() -> str:
    return "2026-10-17T10:00:00Z"


def deps(transcript: str = ARCH, normalized: str = "Project: whiteBORAG\n---\n" + ARCH_FIXED, truncated=False) -> Deps:
    return Deps(
        store=InMemoryStore(),
        blobs=FakeBlobs({KEY: b"jpeg"}),
        reader=FakeReader(Reply(transcript, truncated), Reply(normalized, False)),
        embedder=FakeEmbedder(),
        vectors=FakeVectors(),
    )


def run(d: Deps, reread: bool = False):
    return ingest_capture(d, Job(CAPTURE, reread), now)


def test_fresh_ingest():
    d = deps()
    out = run(d)
    assert (out.status, out.project, out.todos, out.vectors) == ("ingested", "whiteborag", 3, 2)
    assert out.reused is False
    assert d.blobs.get_text(CAPTURE.transcript_key) == ARCH
    assert d.blobs.get_text(CAPTURE.normalized_key).startswith("Project: whiteBORAG\n---\n")
    rec = d.store.get_capture(CID)
    assert len(rec.edges) == 3
    assert rec.edges[0] == {"src": "Dp32", "dst": "API gateway", "label": "AWS key"}
    assert rec.normalization_rejected is False
    assert rec.title_as_seen == "White BORAH architecture"
    assert rec.prompt_versions == {"transcribe": "transcribe-v3", "normalize": "normalize-v1"}
    assert rec.vector_keys == [f"{CID}#0", f"{CID}#1"]
    assert {t.text for t in d.store.list_todos("whiteborag")} >= {"Test terraform code"}


def test_reuse_skips_reader():
    d = deps()
    run(d)
    calls = d.reader.calls
    out = run(d)
    assert d.reader.calls == calls
    assert out.reused is True


def test_reread_calls_reader():
    d = deps()
    run(d)
    calls = d.reader.calls
    run(d, reread=True)
    assert d.reader.calls == calls + 2


def test_switch_project_leaves_no_stray():
    d = deps()
    run(d)
    d.blobs.put_text(CAPTURE.normalized_key, "Project: tender crawler\n---\n" + ARCH_FIXED)
    out = run(d)
    assert out.project == "tendercrawler"
    assert d.store.get_project("whiteborag") is None
    assert d.store.project_links("whiteborag") == []
    assert d.store.list_todos("whiteborag") == []
    assert [p.key for p in d.store.list_projects()] == ["tendercrawler"]
    assert len(d.store.project_links("tendercrawler")) == 1
    assert len(d.store.list_todos("tendercrawler")) == 3
    records = d.vectors.get([f"{CID}#0", f"{CID}#1"])
    assert [r["metadata"]["project"] for r in records] == ["tendercrawler", "tendercrawler"]


def test_fewer_sections_deletes_stale_vectors():
    d = deps()
    run(d)
    diagram_only = ARCH.split("## TODO")[0].strip()
    d.blobs.put_text(CAPTURE.transcript_key, diagram_only)
    d.blobs.put_text(CAPTURE.normalized_key, "Project: whiteBORAG\n---\n" + diagram_only)
    out = run(d)
    assert out.vectors == 1
    assert d.vectors.get([f"{CID}#1"]) == []
    assert d.store.get_capture(CID).vector_keys == [f"{CID}#0"]
    assert d.store.list_todos("whiteborag") == []


def test_untitled_no_todos_tracked():
    d = deps(CRAWLERS, "Project: none\n---\n" + CRAWLERS)
    out = run(d)
    assert out.project is None
    assert out.todos == 0
    assert d.store.list_projects() == []
    assert d.embedder.texts[0].startswith("no project: Lightsail Box — diagram")
    assert d.store.get_capture(CID).descriptive_name == "Lightsail Box"


def test_guard_rejection_recorded():
    flipped = ARCH_FIXED.replace("- [x] Test terraform code", "- [ ] Test terraform code")
    d = deps(normalized="Project: whiteBORAG\n---\n" + flipped)
    out = run(d)
    assert out.normalization_rejected is True
    assert d.store.get_capture(CID).normalization_rejected is True
    todo = next(t for t in d.store.list_todos("whiteborag") if "Test" in t.text)
    assert todo.state == "done"
    assert todo.text == "Test transform code"


def test_truncated_flag():
    d = deps(truncated=True)
    run(d)
    assert d.store.get_capture(CID).truncated is True


def test_missing_image_is_skipped_here():
    d = deps()
    d.blobs.files.clear()
    out = run(d)
    assert out.status == "skipped_missing_image"
    assert d.reader.calls == 0
    assert d.blobs.files == {}
    assert d.store.captures == {} and d.store.projects == {} and d.store.links == {}
    assert d.vectors.records == {}


def test_reapply_after_partial_apply_is_idempotent():
    d = deps()
    put_capture = d.store.put_capture

    def fail_once(rec):
        d.store.put_capture = put_capture
        raise RuntimeError("crash before the capture record")

    d.store.put_capture = fail_once
    try:
        run(d)
    except RuntimeError:
        pass
    run(d)
    assert len(d.store.project_links("whiteborag")) == 1
    todos = d.store.list_todos("whiteborag")
    assert len(todos) == 3
    assert all(list(t.sightings) == [CID] for t in todos)


UNUSABLE = "# (unusable)\nToo blurry to read."


def test_unusable_deletes_image_and_writes_nothing():
    d = deps(UNUSABLE)
    out = run(d)
    assert (out.status, out.reason) == ("deleted_unusable", "Too blurry to read.")
    assert d.reader.calls == 1
    assert d.blobs.files == {}
    assert d.store.captures == {} and d.store.projects == {} and d.store.links == {} and d.store.todos == {}
    assert d.vectors.records == {}


def test_unusable_reread_undoes_previous_ingest():
    d = deps()
    run(d)
    d.reader.transcript = Reply(UNUSABLE, False)
    out = run(d, reread=True)
    assert out.status == "deleted_unusable"
    assert d.blobs.files == {}
    assert d.store.captures == {} and d.store.projects == {} and d.store.links == {} and d.store.todos == {}
    assert d.vectors.records == {}
