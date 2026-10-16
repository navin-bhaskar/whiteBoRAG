from harness.config import EVAL_DIR
from harness.dataset import Checkbox, Edge, load_manifest, parse_markdown

ARCH = (EVAL_DIR / "ground_truth/architecture-v1.md").read_text(encoding="utf-8")


def test_load_manifest():
    s = load_manifest(EVAL_DIR / "manifest.csv")
    assert len(s) == 13
    assert s[0].ground_truth == "architecture-v1.md"
    assert s[0].environment == "evening-backlit-window"


def test_parse_edges_with_labels():
    p = parse_markdown(ARCH)
    assert Edge("ESP32 CAM", "API Gateway", "API key") in p.edges
    assert Edge("API Gateway", "Pre-Sign URL λ", None) in p.edges
    assert len(p.edges) == 4


def test_parse_checkboxes():
    p = parse_markdown(ARCH)
    assert Checkbox("Test terraform code", True) in p.checkboxes
    assert Checkbox("Finalize IR sensor wave behaviour on ESP32 cam", False) in p.checkboxes


def test_parse_edges_ascii_arrows():
    p = parse_markdown('Edges:\n- A -> B\n- C => D, labelled "x"\n')
    assert p.edges == [Edge("A", "B", None), Edge("C", "D", "x")]


def test_arrows_outside_edges_section_are_not_edges():
    q = (EVAL_DIR / "ground_truth/questions-v1.md").read_text(encoding="utf-8")
    assert parse_markdown(q).edges == []


def test_annotations_stripped_from_nodes():
    p = parse_markdown("Edges:\n- Lightsail Box (boundary box) → Neon db\n")
    assert p.edges == [Edge("Lightsail Box", "Neon db", None)]
