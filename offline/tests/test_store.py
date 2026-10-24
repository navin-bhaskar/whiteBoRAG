import pytest

import whiteborag_offline  # noqa: F401  (puts the shared packages on sys.path)
from ingest.store import CaptureRecord, Conflict, Link, Project
from ingest.todos import Sighting, TodoItem
from whiteborag_offline.store import SqliteStore


def _project(key="whiteborag", version=0) -> Project:
    return Project(key, "WhiteBoRAG", {"WhiteBoRAG": 2}, None, "2026-10-24T10:00:00Z", version)


def _link(captured_at: str, capture_id: str) -> Link:
    return Link("whiteborag", captured_at, capture_id, captured_at[:10], "Plan", "WhiteBoRAG")


def _capture(capture_id="01ABC") -> CaptureRecord:
    return CaptureRecord(
        capture_id=capture_id, s3_key=f"captures/cam-01/2026/10/24/20261024T100000Z_{capture_id}.jpg",
        device="cam-01", captured_at="2026-10-24T10:00:00Z", date="2026-10-24", project="whiteborag",
        project_name_as_seen="WhiteBoRAG", title_as_seen="Plan", descriptive_name=None,
        edges=[{"from": "A", "to": "B", "label": None}], todo_ids=["t1"], vector_keys=[f"{capture_id}#0"],
        transcript_key="transcripts/x.md", normalized_key="transcripts/x.normalized.md",
        normalization_rejected=False, truncated=False, ingested_at="2026-10-24T10:01:00Z",
        prompt_versions={"transcribe": "transcribe-v2"},
    )


def _todo(version=0) -> TodoItem:
    s = Sighting("01ABC", "2026-10-24", "2026-10-24T10:00:00Z", False, "write tests")
    return TodoItem("t1", {"01ABC": s}, version, "write tests", "2026-10-24", "open", None)


@pytest.fixture
def store():
    return SqliteStore(":memory:")


def test_create_project_twice_conflicts(store):
    store.create_project(_project())
    with pytest.raises(Conflict):
        store.create_project(_project())
    assert store.get_project("whiteborag") == _project()


def test_save_project_requires_matching_version_and_bumps_it(store):
    store.create_project(_project())
    store.save_project(_project(version=0))
    assert store.get_project("whiteborag").version == 1
    with pytest.raises(Conflict):
        store.save_project(_project(version=0))
    with pytest.raises(Conflict):
        store.save_project(_project(key="missing"))


def test_delete_project_stale_version_conflicts(store):
    store.create_project(_project())
    store.save_project(_project())
    with pytest.raises(Conflict):
        store.delete_project("whiteborag", 0)
    store.delete_project("whiteborag", 1)
    assert store.get_project("whiteborag") is None
    store.delete_project("whiteborag", 7)  # absent: nothing to protect


def test_list_projects(store):
    store.create_project(_project("a"))
    store.create_project(_project("b"))
    assert sorted(p.key for p in store.list_projects()) == ["a", "b"]


def test_links_ordered_by_captured_at(store):
    store.put_link(_link("2026-10-24T12:00:00Z", "02"))
    store.put_link(_link("2026-10-23T12:00:00Z", "01"))
    store.put_link(_link("2026-10-24T12:00:00Z", "02"))  # same key: replaced, not duplicated
    assert [l.capture_id for l in store.project_links("whiteborag")] == ["01", "02"]
    store.delete_link(_link("2026-10-23T12:00:00Z", "01"))
    assert [l.capture_id for l in store.project_links("whiteborag")] == ["02"]
    assert store.project_links("other") == []


def test_save_todo_version0_creates_then_conflicts_if_exists(store):
    store.save_todo("whiteborag", _todo(0))
    with pytest.raises(Conflict):
        store.save_todo("whiteborag", _todo(0))
    store.save_todo("whiteborag", _todo(1))
    assert store.list_todos("whiteborag")[0].version == 2
    with pytest.raises(Conflict):
        store.save_todo("whiteborag", _todo(1))
    with pytest.raises(Conflict):
        store.delete_todo("whiteborag", "t1", 1)
    store.delete_todo("whiteborag", "t1", 2)
    assert store.list_todos("whiteborag") == []


def test_save_todo_nonzero_version_on_missing_conflicts(store):
    with pytest.raises(Conflict):
        store.save_todo("whiteborag", _todo(3))


def test_todo_roundtrip_keeps_sightings(store):
    store.save_todo("whiteborag", _todo())
    (item,) = store.list_todos("whiteborag")
    assert item.sightings["01ABC"] == _todo().sightings["01ABC"]
    assert isinstance(item.sightings["01ABC"], Sighting)
    assert item.version == 1


def test_capture_roundtrip_and_delete(store):
    store.put_capture(_capture())
    assert store.get_capture("01ABC") == _capture()
    store.put_capture(_capture())  # overwrite allowed
    store.delete_capture("01ABC")
    assert store.get_capture("01ABC") is None
    store.delete_capture("01ABC")


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "wb.db"
    SqliteStore(path).put_capture(_capture())
    assert SqliteStore(path).get_capture("01ABC") == _capture()
