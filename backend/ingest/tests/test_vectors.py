from ingest.board import Section
from ingest.events import parse_key
from ingest.vectors import build_records, embed_text, label, stale_keys

KEY = "captures/wb-cam-01/2026/10/15/20261015T084632Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg"
CAPTURE = parse_key(KEY)
SECTIONS = [Section("diagram", "## Diagram\n- Dp32"), Section("todos", "## TODO\n- [x] a")]


def test_label_untitled():
    assert label(None, "Lightsail Box (untitled)", "Lightsail Box") == "no project: Lightsail Box"
    assert label("whiteBORAG", "x", None) == "whiteBORAG"


def test_embed_text():
    assert embed_text("whiteBORAG", Section("todos", "## TODO\n- [x] a")) == "whiteBORAG — todos — ## TODO\n- [x] a"


def test_build_records():
    vecs = [[0.1, 0.2], [0.3, 0.4]]
    records = build_records(CAPTURE, "whiteborag", SECTIONS, vecs)
    cid = CAPTURE.capture_id
    assert [r["key"] for r in records] == [f"{cid}#0", f"{cid}#1"]
    assert records[0]["data"] == {"float32": vecs[0]}
    assert records[0]["metadata"] == {
        "project": "whiteborag",
        "date": "2026-10-15",
        "section": "diagram",
        "device": "wb-cam-01",
        "capture_id": cid,
        "s3_key": KEY,
        "text": SECTIONS[0].text,
    }
    assert records[1]["metadata"]["section"] == "todos"
    assert build_records(CAPTURE, None, SECTIONS, vecs)[0]["metadata"]["project"] == "none"


def test_stale_keys():
    assert stale_keys(["a#0", "a#1", "a#2"], ["a#0"]) == ["a#1", "a#2"]
