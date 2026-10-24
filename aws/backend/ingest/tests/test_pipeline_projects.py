import pytest

from fakes import InMemoryStore
from ingest.pipeline import apply_project, refresh_project, remove_from_project
from ingest.store import CaptureRecord, Conflict, Link, Project, with_retries


def link_for(capture_id: str, captured_at: str, name: str):
    return lambda key: Link(key, captured_at, capture_id, captured_at[:10], f"{name} architecture", name)


def record(capture_id: str, captured_at: str, project: str, name: str) -> CaptureRecord:
    return CaptureRecord(
        capture_id=capture_id, s3_key=f"captures/{capture_id}.jpg", device="wb-cam-01",
        captured_at=captured_at, date=captured_at[:10], project=project,
        project_name_as_seen=name, title_as_seen=f"{name} architecture", descriptive_name=None,
        edges=[], todo_ids=[], vector_keys=[], transcript_key="", normalized_key="",
        normalization_rejected=False, truncated=False, ingested_at="", prompt_versions={},
    )


def test_new_project_created():
    store = InMemoryStore()
    assert apply_project(store, "whiteBORAG", link_for("c1", "2026-10-15T07:00:00Z", "whiteBORAG")) == "whiteborag"
    assert store.get_project("whiteborag").display_name == "whiteBORAG"
    assert len(store.project_links("whiteborag")) == 1


def test_misread_joins_existing():
    store = InMemoryStore()
    apply_project(store, "whiteBORAG", link_for("c1", "2026-10-15T07:00:00Z", "whiteBORAG"))
    assert apply_project(store, "White BORAH", link_for("c2", "2026-10-15T08:00:00Z", "White BORAH")) == "whiteborag"
    assert store.get_project("whiteborag").aliases == {"whiteBORAG": 1, "White BORAH": 1}


def test_none_name_no_project():
    store = InMemoryStore()
    assert apply_project(store, None, link_for("c1", "2026-10-15T07:00:00Z", "x")) is None
    assert apply_project(store, "!!", link_for("c1", "2026-10-15T07:00:00Z", "!!")) is None
    assert store.list_projects() == []


def test_create_race_joins_existing():
    store = InMemoryStore()
    store.fail_next_create = Project("whiteborag", "whiteBORAG", {})
    assert apply_project(store, "whiteBORAG", link_for("c1", "2026-10-15T07:00:00Z", "whiteBORAG")) == "whiteborag"
    assert len(store.list_projects()) == 1


def test_remove_last_capture_deletes_project():
    store = InMemoryStore()
    apply_project(store, "whiteBORAG", link_for("c1", "2026-10-15T07:00:00Z", "whiteBORAG"))
    remove_from_project(store, record("c1", "2026-10-15T07:00:00Z", "whiteborag", "whiteBORAG"))
    assert store.get_project("whiteborag") is None
    assert store.project_links("whiteborag") == []


def test_remove_keeps_other_captures():
    store = InMemoryStore()
    apply_project(store, "whiteBORAG", link_for("c1", "2026-10-15T07:00:00Z", "whiteBORAG"))
    apply_project(store, "White BORAH", link_for("c2", "2026-10-15T08:00:00Z", "White BORAH"))
    remove_from_project(store, record("c2", "2026-10-15T08:00:00Z", "whiteborag", "White BORAH"))
    assert [link.capture_id for link in store.project_links("whiteborag")] == ["c1"]
    assert store.get_project("whiteborag").aliases == {"whiteBORAG": 1}


def test_with_retries_gives_up():
    calls = []

    def always_conflicts():
        calls.append(1)
        raise Conflict("stale")

    with pytest.raises(Conflict):
        with_retries(always_conflicts)
    assert len(calls) == 5


def test_delete_loses_to_concurrent_link():
    """Undo saw no links, but another capture joined before the delete: the project must survive."""
    store = InMemoryStore()
    apply_project(store, "whiteBORAG", link_for("c1", "2026-10-15T07:00:00Z", "whiteBORAG"))
    stale = store.get_project("whiteborag")
    apply_project(store, "whiteBORAG", link_for("c2", "2026-10-15T08:00:00Z", "whiteBORAG"))
    with pytest.raises(Conflict):
        store.delete_project("whiteborag", stale.version)
    assert store.get_project("whiteborag") is not None


def test_refresh_recreates_project_deleted_under_a_link():
    """Undo deleted the project between another capture's put_link and its refresh: the refresh restores it."""
    store = InMemoryStore()
    store.put_link(link_for("c2", "2026-10-15T08:00:00Z", "whiteBORAG")("whiteborag"))
    refresh_project(store, "whiteborag")
    assert store.get_project("whiteborag").display_name == "whiteBORAG"
