from query.answer import FALLBACK, PROMPT_VERSION, build_prompt
from query.evidence import Board
from query.request import Turn
from query.understand import Intent

TODOS = Intent("todos", None, None, None, None, None, False)
WB = {"key": "whiteborag", "display_name": "whiteBORAG"}


def todo_board(date: str = "2026-10-15") -> Board:
    return Board(
        "01M", f"{date}T08:46:32Z", date, "captures/x.jpg", "whiteborag", "todos", "# whiteBORAG\n## TODO",
        todos=[
            {"text": "Test terraform code", "checked": False, "done_since": "2026-10-19"},
            {"text": "Deploy lambda", "checked": True, "done_since": None},
        ],
    )


def test_version_and_fallback():
    assert PROMPT_VERSION == "answer-v1" and FALLBACK == "Here are the boards I found."


def test_boards_numbered_with_dates():
    later = Board("01N", "2026-10-19T08:46:32Z", "2026-10-19", "k", "whiteborag", "diagram", "LATER TEXT")
    p = build_prompt("what's left?", TODOS, WB, "named", [], [todo_board(), later])
    assert p.index("[1] The 15 Oct 2026 board") < p.index("[2] The 19 Oct 2026 board") < p.index("LATER TEXT")
    assert "what's left?" in p


def test_todos_rendered_with_boxes_and_done_since():
    p = build_prompt("q", TODOS, WB, "named", [], [todo_board()])
    assert "☐ Test terraform code (done since, on 19 Oct 2026)" in p
    assert "☑ Deploy lambda" in p and "☑ Deploy lambda (done" not in p


def test_diff_rendered():
    diff = {"added": [{"src": "SQS", "dst": "Lambda", "label": "batch"}], "removed": [{"src": "S3", "dst": "SQS", "label": None}]}
    b = Board("01M", "2026-10-15T08:46:32Z", "2026-10-15", "k", "whiteborag", "diagram", "t", diff=diff)
    p = build_prompt("q", Intent("diagram_history", None, None, None, None, None, False), WB, "named", [], [b])
    assert 'SQS → Lambda, labelled "batch"' in p and "S3 → SQS" in p


def test_only_last_3_turns():
    history = [Turn(f"question {i}", {}, f"answer {i}", []) for i in range(5)]
    p = build_prompt("q", TODOS, WB, "named", history, [todo_board()])
    assert "question 1" not in p and "answer 1" not in p
    assert all(f"question {i}" in p and f"answer {i}" in p for i in (2, 3, 4))


def test_project_named_when_previous_or_latest():
    latest = build_prompt("q", TODOS, WB, "latest", [], [todo_board()])
    assert "most recent board" in latest and "whiteBORAG" in latest
    previous = build_prompt("q", TODOS, WB, "previous", [], [todo_board()])
    assert "previous question" in previous
    named = build_prompt("q", TODOS, WB, "named", [], [todo_board()])
    assert "first sentence" not in named


def test_search_with_unknown_name_says_so():
    intent = Intent("search", "zebra", None, None, None, None, False)
    b = Board("01M", "2026-10-15T08:46:32Z", "2026-10-15", "k", None, "notes", "t")
    p = build_prompt("q", intent, None, None, [], [b])
    assert '"zebra"' in p and "all boards" in p
