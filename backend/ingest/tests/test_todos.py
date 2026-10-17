from ingest.board import Todo
from ingest.todos import Sighting, TodoItem, derive, match_todos

S1 = Sighting("c1", "2026-10-15", "2026-10-15T07:00:00Z", False, "Test transform code")
S2 = Sighting("c2", "2026-10-16", "2026-10-16T08:00:00Z", True, "Test terraform code")
S3 = Sighting("c3", "2026-10-17", "2026-10-17T09:00:00Z", False, "Test terraform code")


def item(todo_id: str, text: str) -> TodoItem:
    return derive(TodoItem(todo_id, {"c0": Sighting("c0", "2026-10-14", "2026-10-14T07:00:00Z", False, text)}))


def test_derive_any_order():
    todo = derive(TodoItem("t1", {"c2": S2, "c1": S1}))
    assert todo.state == "done"
    assert todo.completed_on == "2026-10-16"
    assert todo.first_seen == "2026-10-15"
    assert todo.text == S2.text_as_seen


def test_reopen():
    todo = derive(TodoItem("t1", {"c2": S2, "c1": S1, "c3": S3}))
    assert todo.state == "open"
    assert todo.completed_on is None


def test_match_same():
    existing = item("t1", "Finilize IR sensor wave behaviour on ESP32 CAM")
    assert match_todos([Todo("Finalize IR sensor wave behaviour on ESP32 CAM", False)], [existing]) == ["t1"]


def test_spelling_drift_is_new():
    assert match_todos([Todo("Test durafirm code", False)], [item("t1", "Test transform code")]) == [None]


def test_one_to_one():
    existing = item("t1", "Deploy lambda")
    board = [Todo("Deploy lambdas", False), Todo("Deploy lambda", True)]
    assert match_todos(board, [existing]) == [None, "t1"]


def test_case_insensitive():
    assert match_todos([Todo("deploy LAMBDA", False)], [item("t1", "Deploy lambda")]) == ["t1"]
