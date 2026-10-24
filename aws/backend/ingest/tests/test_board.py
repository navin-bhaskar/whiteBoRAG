from pathlib import Path

from ingest.board import Edge, Todo, parse_board

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_architecture():
    board = parse_board(fixture("architecture.md"))
    assert board.title == "White BORAH architecture"
    assert board.untitled is False
    assert board.descriptive_name is None
    assert [s.kind for s in board.sections] == ["diagram", "todos"]
    assert board.todos[0] == Todo("Test transform code", True)
    assert [t.checked for t in board.todos] == [True, True, False]
    assert board.edges[0] == Edge("Dp32", "API gateway", "AWS key")
    assert len(board.edges) == 3


def test_questions():
    board = parse_board(fixture("questions.md"))
    assert [s.kind for s in board.sections] == ["notes"]
    assert "Vector Stone → S3 as vector store" in board.sections[0].text
    assert board.edges == []  # an arrow in a plain list is not a diagram edge


def test_crawlers_untitled():
    board = parse_board(fixture("crawlers.md"))
    assert board.untitled is True
    assert board.descriptive_name == "Lightsail Box"
    assert [s.kind for s in board.sections] == ["diagram"]
    assert board.edges[2] == Edge("Lightsail Box", "Neon db", "update db")


def test_ascii_arrows_and_annotation():
    board = parse_board("# T\n## Diagram\n- A (boundary box)\nEdges:\n- A (boundary box) -> B => x\n")
    assert board.edges == [Edge("A", "B => x", None)]  # the first arrow splits, as in the harness
    board = parse_board("# T\n## Diagram\nEdges:\n- A => B\n")
    assert board.edges == [Edge("A", "B", None)]


def test_section_text_keeps_heading():
    board = parse_board(fixture("architecture.md"))
    assert board.sections[1].text.startswith("## TODO")
