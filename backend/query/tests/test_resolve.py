import pytest

from ingest.store import Project
from query.request import BadRequest, Turn
from query.resolve import Resolution, rank_projects, resolve


def project(key: str, display: str) -> Project:
    return Project(key=key, display_name=display, aliases={display: 1})


P = [project("whiteborag", "whiteBORAG"), project("tendercrawler", "Tender crawler")]
P3 = P + [project("tendercrawlers", "Tender crawlers")]


def none():
    return None


def latest():
    return "whiteborag"


def asked(project_key: str) -> Turn:
    return Turn("earlier question", {"intent": "todos", "project": project_key}, "an answer", [])


def test_confident_name():
    assert resolve("white borag", "todos", None, [], P, none) == Resolution("whiteborag", "named", None)


def test_short_name_partial():
    assert rank_projects("the crawler", {"tendercrawler": [], "whiteborag": []})[0][0] == "tendercrawler"


def test_short_name_resolves():
    assert resolve("the crawler", "diagram_latest", None, [], P, none).project == "tendercrawler"


def test_weak_partial_does_not_count():
    # "zebra" partially matches "whiteborag" at 80; only near-exact substrings use partial scoring.
    assert dict(rank_projects("zebra", {"whiteborag": []}))["whiteborag"] < 70


def test_aliases_are_matched():
    p = Project(key="whiteborag", display_name="whiteBORAG", aliases={"wb rag board": 2})
    assert resolve("wb rag board", "todos", None, [], [p], none).project == "whiteborag"


def test_two_close_candidates_clarify():
    r = resolve("tender crawler", "diagram_latest", None, [], P3, none)
    assert r.project is None
    assert {o["key"] for o in r.clarify["options"]} == {"tendercrawler", "tendercrawlers"}
    assert r.clarify["message"] == "Which project did you mean?"


def test_did_you_mean_band():
    r = resolve("wightborag", "todos", None, [], P3, none)
    assert r.project is None
    assert r.clarify["options"] == [{"key": "whiteborag", "display_name": "whiteBORAG"}]
    assert r.clarify["message"].startswith("Did you mean")


def test_did_you_mean_at_most_3():
    many = [project(f"whiteborag{i}", f"whiteBORAG {i}") for i in range(5)]
    r = resolve("wightborag", "todos", None, [], many, none)
    assert len(r.clarify["options"]) <= 3


def test_unknown_lists_all_projects():
    r = resolve("zebra", "todos", None, [], P3, none)
    assert r.project is None
    assert {o["key"] for o in r.clarify["options"]} == {"whiteborag", "tendercrawler", "tendercrawlers"}
    assert "zebra" in r.clarify["message"]


def test_requested_key_skips_matching():
    assert resolve("zebra", "todos", "tendercrawler", [], P3, none) == Resolution("tendercrawler", "named", None)


def test_unknown_requested_key_is_bad_request():
    with pytest.raises(BadRequest):
        resolve(None, "todos", "nosuchproject", [], P3, none)


def test_follow_up_inherits_previous():
    r = resolve(None, "diagram_latest", None, [asked("tendercrawler")], P, latest, follow_up=True)
    assert r == Resolution("tendercrawler", "previous", None)


def test_no_name_todos_in_a_conversation_inherits_previous():
    assert resolve(None, "todos", None, [asked("tendercrawler")], P, latest).how == "previous"


def test_previous_project_gone_falls_through():
    r = resolve(None, "todos", None, [asked("deletedproject")], P, latest, follow_up=True)
    assert r == Resolution("whiteborag", "latest", None)


def test_latest_when_no_name_no_history():
    assert resolve(None, "todos", None, [], P, latest) == Resolution("whiteborag", "latest", None)


def test_latest_project_gone_is_none():
    assert resolve(None, "todos", None, [], P, lambda: "deletedproject") == Resolution(None, None, None)


def test_search_never_clarifies():
    assert resolve("zebra", "search", None, [], P, none) == Resolution(None, None, None)
    assert resolve("tender crawler", "search", None, [], P3, none) == Resolution(None, None, None)


def test_search_confident_name_filters():
    assert resolve("whiteborag", "search", None, [], P, none) == Resolution("whiteborag", "named", None)


def test_search_without_name_has_no_filter():
    assert resolve(None, "search", None, [asked("tendercrawler")], P, latest) == Resolution(None, None, None)


def test_search_follow_up_inherits_previous():
    r = resolve(None, "search", None, [asked("tendercrawler")], P, latest, follow_up=True)
    assert r == Resolution("tendercrawler", "previous", None)


def test_empty_store():
    assert resolve(None, "todos", None, [], [], lambda: None) == Resolution(None, None, None)
    assert resolve("x", "todos", None, [], [], lambda: None).clarify is None


def test_junk_previous_project_is_ignored():
    junk = Turn("q", {"project": ["not", "a", "key"]}, None, [])
    assert resolve(None, "todos", None, [junk], P, latest) == Resolution("whiteborag", "latest", None)
