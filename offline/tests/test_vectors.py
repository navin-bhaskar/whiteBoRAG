import pytest

import whiteborag_offline  # noqa: F401
from ingest.board import Section
from ingest.events import parse_key
from ingest.vectors import build_records
from whiteborag_offline.vectors import QdrantVectors, to_qdrant_filter

KEY = "captures/cam-01/2026/10/24/20261024T100000Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg"


def _records(project="whiteborag"):
    capture = parse_key(KEY)
    sections = [Section("todos", "- [ ] write tests"), Section("diagram", "- A\n- B")]
    return build_records(capture, project, sections, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


@pytest.fixture
def vectors():
    return QdrantVectors(":memory:")


def test_put_get_roundtrip_shape(vectors):
    records = _records()
    vectors.put(records)
    got = sorted(vectors.get([r["key"] for r in records]), key=lambda r: r["key"])
    assert got == sorted(records, key=lambda r: r["key"])


def test_query_returns_nearest_with_metadata(vectors):
    vectors.put(_records())
    (hit, *_) = vectors.query([0.0, 1.0, 0.0], 2, None)
    assert hit["metadata"]["section"] == "diagram"
    assert hit["key"].endswith("#1") or hit["metadata"]["text"] == "- A\n- B"
    assert hit["distance"] == pytest.approx(0.0, abs=1e-6)


def test_query_filters_by_project_and_section(vectors):
    vectors.put(_records("whiteborag"))
    other = _records("other")
    for r in other:
        r["key"] = "other-" + r["key"]
    vectors.put(other)
    hits = vectors.query([1.0, 0.0, 0.0], 10, {"$and": [{"project": {"$eq": "other"}}, {"section": {"$eq": "todos"}}]})
    assert [h["metadata"]["project"] for h in hits] == ["other"]
    assert [h["metadata"]["section"] for h in hits] == ["todos"]
    hits = vectors.query([1.0, 0.0, 0.0], 10, {"project": {"$eq": "whiteborag"}})
    assert {h["metadata"]["project"] for h in hits} == {"whiteborag"}
    assert len(hits) == 2


def test_query_empty_collection_returns_empty(vectors):
    assert vectors.query([1.0, 0.0, 0.0], 5, None) == []
    assert vectors.get(["nope"]) == []
    vectors.delete(["nope"])


def test_delete_keys(vectors):
    records = _records()
    vectors.put(records)
    vectors.delete([records[0]["key"]])
    assert [r["key"] for r in vectors.get([r["key"] for r in records])] == [records[1]["key"]]


def test_persists_on_disk(tmp_path):
    first = QdrantVectors(tmp_path / "vectors")
    first.put(_records())
    first.close()
    assert len(QdrantVectors(tmp_path / "vectors").query([1.0, 0.0, 0.0], 5, None)) == 2


def test_filter_translation_rejects_unknown_operator():
    assert to_qdrant_filter(None) is None
    with pytest.raises(ValueError):
        to_qdrant_filter({"project": {"$in": ["a"]}})
    with pytest.raises(ValueError):
        to_qdrant_filter({"$or": [{"project": {"$eq": "a"}}]})
