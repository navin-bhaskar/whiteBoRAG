from fakes import FakeEmbedder, InMemoryStore
from query.evidence import (
    NOTHING,
    board_text,
    diagram_history,
    edge_diff,
    latest_board,
    latest_diagram,
    latest_project,
    search_boards,
    todo_boards,
)
from query.understand import Intent
from query_fakes import ARCH, FakeSearch, Seeded, board, hit

P = "whiteborag"
PLAIN = Intent("todos", None, None, None, None, None, False)


def intent(kind: str = "todos", date_from=None, date_to=None, before=None) -> Intent:
    return Intent(kind, None, None, date_from, date_to, before, False)


def three_arch_boards() -> Seeded:
    s = Seeded()
    for day in ("15", "17", "19"):
        s.add(f"202610{day}T084632Z")
    return s


def test_latest_todo_board_is_newest_with_todos():
    s = Seeded()
    s.add("20261015T084632Z")
    middle = s.add("20261017T084632Z")
    s.add("20261019T084632Z", board(edges=["Dp32 → API gateway"]))
    [b] = todo_boards(s.store, s.blobs, P, PLAIN)
    assert (b.capture_id, b.date, b.section) == (middle, "2026-10-17", "todos")
    assert [t["text"] for t in b.todos] == [
        "Test transform code",
        "Deploy lambda du and check for pre-signed URL",
        "Finilize IR sensor wave behaviour on ESP32 CAM",
    ]
    assert b.s3_key.endswith(f"_{middle}.jpg") and b.project == P
    assert "## TODO" in b.text and not b.text.startswith("Project:")


def test_todo_state_as_on_that_board():
    s = Seeded()
    s.add("20261015T084632Z", board(todos=["[ ] Test terraform code", "[ ] Deploy lambda"]))
    s.add("20261019T084632Z", board(todos=["[x] Test terraform code", "[ ] Deploy lambda"]))
    [b] = todo_boards(s.store, s.blobs, P, intent(before="2026-10-19T00:00:00Z"))
    t = next(t for t in b.todos if "Test" in t["text"])
    assert (t["checked"], t["done_since"]) == (False, "2026-10-19")
    still_open = next(t for t in b.todos if "Deploy" in t["text"])
    assert still_open["done_since"] is None


def test_todo_ticked_on_the_board_itself_has_no_done_since():
    s = Seeded()
    s.add("20261015T084632Z", board(todos=["[ ] Test terraform code"]))
    s.add("20261019T084632Z", board(todos=["[x] Test terraform code"]))
    [b] = todo_boards(s.store, s.blobs, P, PLAIN)
    assert b.todos == [{"text": "Test terraform code", "checked": True, "done_since": None}]


def test_date_range_returns_up_to_5_boards_newest_first():
    s = Seeded()
    for day in range(9, 17):
        s.add(f"202610{day:02d}T084632Z")
    boards = todo_boards(s.store, s.blobs, P, intent(date_from="2026-10-10", date_to="2026-10-15"))
    assert [b.date for b in boards] == ["2026-10-15", "2026-10-14", "2026-10-13", "2026-10-12", "2026-10-11"]


def test_single_day_date_range():
    s = three_arch_boards()
    [b] = todo_boards(s.store, s.blobs, P, intent(date_from="2026-10-17", date_to="2026-10-17"))
    assert b.date == "2026-10-17"


def test_latest_diagram_honours_before():
    s = three_arch_boards()
    [newest] = latest_diagram(s.store, s.blobs, P, intent("diagram_latest"))
    assert (newest.date, newest.section, newest.todos) == ("2026-10-19", "diagram", None)
    [b] = latest_diagram(s.store, s.blobs, P, intent("diagram_latest", before=newest.captured_at))
    assert b.date == "2026-10-17"


def test_latest_diagram_skips_boards_without_edges():
    s = Seeded()
    s.add("20261015T084632Z")
    s.add("20261019T084632Z", board(todos=["[ ] Deploy lambda"]))
    [b] = latest_diagram(s.store, s.blobs, P, intent("diagram_latest"))
    assert b.date == "2026-10-15"


def test_latest_board_is_newest_board_of_any_kind():
    s = Seeded()
    s.add("20261015T084632Z")
    newest = s.add("20261019T084632Z", board("whiteBORAG goals"))
    [b] = latest_board(s.store, s.blobs, P, intent("board_latest"))
    assert (b.capture_id, b.section, b.todos) == (newest, "board", None)
    assert "whiteBORAG goals" in b.text


def test_latest_board_carries_its_todos_and_honours_before():
    s = Seeded()
    s.add("20261015T084632Z", board(todos=["[ ] Deploy lambda"]))
    newest = s.add("20261019T084632Z", board("whiteBORAG goals"))
    before = s.store.get_capture(newest).captured_at
    [b] = latest_board(s.store, s.blobs, P, intent("board_latest", before=before))
    assert b.date == "2026-10-15" and [t["text"] for t in b.todos] == ["Deploy lambda"]


def test_history_oldest_first_capped_at_10():
    s = Seeded()
    for day in range(1, 13):
        s.add(f"202610{day:02d}T084632Z", board(edges=["Cam → Bucket", f"Bucket → Step{day}"]))
    boards = diagram_history(s.store, s.blobs, P, intent("diagram_history"))
    assert [b.date for b in boards] == [f"2026-10-{day:02d}" for day in range(3, 13)]
    # The first board shown is still compared with the board before it.
    assert boards[0].diff == {
        "added": [{"src": "Bucket", "dst": "Step3", "label": None}],
        "removed": [{"src": "Bucket", "dst": "Step2", "label": None}],
    }
    assert boards[-1].diff["added"] == [{"src": "Bucket", "dst": "Step12", "label": None}]


def test_history_first_board_has_no_diff():
    s = three_arch_boards()
    boards = diagram_history(s.store, s.blobs, P, intent("diagram_history"))
    assert [b.diff for b in boards] == [None, {"added": [], "removed": []}, {"added": [], "removed": []}]


def test_edge_diff_case_spacing_and_labels():
    d = edge_diff(
        [{"src": "S3", "dst": "SQS", "label": None}],
        [{"src": " s3", "dst": "sqs ", "label": None}, {"src": "SQS", "dst": "Lambda", "label": "batch"}],
    )
    assert d == {"added": [{"src": "SQS", "dst": "Lambda", "label": "batch"}], "removed": []}


def test_edge_diff_label_change_is_remove_and_add():
    d = edge_diff([{"src": "A", "dst": "B", "label": "x"}], [{"src": "A", "dst": "B", "label": "y"}])
    assert d == {"added": [{"src": "A", "dst": "B", "label": "y"}], "removed": [{"src": "A", "dst": "B", "label": "x"}]}


def test_missing_capture_or_transcript_skipped():
    s = three_arch_boards()
    oldest, middle, newest = s.ids
    s.store.delete_capture(newest)
    rec = s.store.get_capture(middle)
    s.blobs.delete(rec.normalized_key)
    for find in (todo_boards, latest_diagram):
        [b] = find(s.store, s.blobs, P, PLAIN)
        assert b.capture_id == oldest
    assert [b.capture_id for b in diagram_history(s.store, s.blobs, P, PLAIN)] == [oldest]


def test_board_text_uses_verbatim_when_normalization_rejected():
    s = three_arch_boards()
    rec = s.store.get_capture(s.ids[0])
    assert board_text(s.blobs, rec) == ARCH.strip()
    rec.normalization_rejected = True
    s.blobs.put_text(rec.transcript_key, "VERBATIM")
    assert board_text(s.blobs, rec) == "VERBATIM"
    s.blobs.delete(rec.transcript_key)
    assert board_text(s.blobs, rec) is None


def test_unknown_project_or_no_boards_finds_nothing():
    s = three_arch_boards()
    for find in (todo_boards, latest_diagram, diagram_history):
        assert find(s.store, s.blobs, "zebra", PLAIN) == []
        assert find(InMemoryStore(), s.blobs, P, PLAIN) == []


def test_latest_project_empty_store():
    assert latest_project(InMemoryStore()) is None


def test_latest_project_is_newest_link():
    s = Seeded()
    s.add("20261015T084632Z", project="Tender crawler")
    s.add("20261017T084632Z")
    s.add("20261016T084632Z", project="Tender crawler")
    assert latest_project(s.store) == "whiteborag"


def test_nothing_messages_take_the_project_name():
    assert NOTHING["diagram_latest"].format(name="whiteBORAG") == "whiteBORAG has no boards with a diagram yet."
    assert set(NOTHING) == {"todos", "board_latest", "diagram_latest", "diagram_history", "search", "empty"}


def search(hits, project=None, section=None, date_from=None, date_to=None, before=None):
    index = FakeSearch(hits)
    boards = search_boards(
        FakeEmbedder(), index, "where are the sensors?", project,
        Intent("search", None, section, date_from, date_to, before, False),
    )
    return boards, index


def test_filter_for_project_and_section():
    _, index = search([], project=P, section="diagram")
    assert index.last_filter == {"$and": [{"project": {"$eq": P}}, {"section": {"$eq": "diagram"}}]}
    assert index.last_top_k == 8


def test_single_condition_has_no_and():
    _, index = search([], project=P)
    assert index.last_filter == {"project": {"$eq": P}}
    _, index = search([], section="todos")
    assert index.last_filter == {"section": {"$eq": "todos"}}


def test_no_filter_when_unknown():
    _, index = search([])
    assert (index.last_filter, index.last_top_k) == (None, 8)


def test_date_filter_post_query():
    hits = [hit(1, "a", date="2026-10-09"), hit(2, "b", date="2026-10-12"), hit(3, "c", date="2026-10-20")]
    boards, index = search(hits, date_from="2026-10-10", date_to="2026-10-15")
    assert index.last_top_k == 30 and index.last_filter is None
    assert [b.date for b in boards] == ["2026-10-12"]


def test_before_filter_post_query():
    hits = [hit(1, "a", date="2026-10-19"), hit(2, "b", date="2026-10-12")]
    boards, index = search(hits, before="2026-10-19T08:46:32Z")
    assert index.last_top_k == 30 and [b.date for b in boards] == ["2026-10-12"]


def test_grouped_and_capped():
    order = [1, 2, 1, 3, 4, 5, 6, 2]
    hits = [hit(n, f"text {i}", section="todos" if i == 0 else "notes") for i, n in enumerate(order)]
    boards, _ = search(hits)
    assert [b.capture_id[-4:] for b in boards] == ["0001", "0002", "0003", "0004", "0005"]
    first = boards[0]
    assert (first.text, first.section, first.project) == ("text 0\n\ntext 2", "todos", P)
    assert (first.captured_at, first.date) == ("2026-10-15T08:46:32Z", "2026-10-15")
    assert first.s3_key.endswith("_01M4Z7KFZ5KHCYV4BWHM8R0001.jpg")


def test_untitled_board_has_no_project():
    [b], _ = search([hit(1, "x", project="none")])
    assert b.project is None


def test_embeds_the_question():
    embedder, index = FakeEmbedder(), FakeSearch([])
    search_boards(embedder, index, "where are the sensors?", None, PLAIN)
    assert embedder.texts == ["where are the sensors?"]
