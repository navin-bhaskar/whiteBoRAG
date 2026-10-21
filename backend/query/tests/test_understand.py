from query.request import Turn
from query.understand import INTENTS, Intent, build_prompt, parse_intent

PREV = Turn(
    "arch of crawler?",
    {"intent": "diagram_latest", "project": "tendercrawler"},
    "…",
    [{"capture_id": "01M", "captured_at": "2026-10-15T08:11:04Z"}],
)
FALLBACK = Intent("search", None, None, None, None, None, False)


def test_parses_json_in_fence():
    reply = '```json\n{"intent":"todos","project_name":"tender crawler","follow_up":false}\n```'
    i = parse_intent(reply, [])
    assert (i.intent, i.project_name) == ("todos", "tender crawler")


def test_parses_every_field():
    reply = (
        '{"intent":"diagram_history","project_name":"whiteborag","section":"diagram",'
        '"date_from":"2026-10-01","date_to":"2026-10-15","before":null,"follow_up":false}'
    )
    assert parse_intent(reply, []) == Intent(
        "diagram_history", "whiteborag", "diagram", "2026-10-01", "2026-10-15", None, False
    )


def test_invalid_json_falls_back_to_search():
    assert parse_intent("sorry", []) == FALLBACK


def test_no_reply_falls_back_to_search():
    assert parse_intent(None, []) == FALLBACK


def test_non_object_json_falls_back_to_search():
    assert parse_intent('["todos"]', []) == FALLBACK


def test_unknown_intent_falls_back():
    assert parse_intent('{"intent":"weather","project_name":"whiteborag"}', []) == FALLBACK


def test_bad_date_dropped():
    i = parse_intent('{"intent":"todos","date_from":"15 Oct","date_to":"2026-02-30"}', [])
    assert (i.intent, i.date_from, i.date_to) == ("todos", None, None)


def test_bad_before_and_section_dropped():
    i = parse_intent('{"intent":"search","section":"kitchen","before":"yesterday"}', [])
    assert (i.section, i.before) == (None, None)


def test_blank_project_name_is_none():
    assert parse_intent('{"intent":"todos","project_name":"  "}', []).project_name is None


def test_follow_up_inherits_intent():
    i = parse_intent(
        '{"intent":"search","project_name":null,"before":"2026-10-15T08:11:04Z","follow_up":true}', [PREV]
    )
    assert (i.intent, i.before, i.follow_up) == ("diagram_latest", "2026-10-15T08:11:04Z", True)


def test_follow_up_with_new_explicit_intent_keeps_it():
    i = parse_intent('{"intent":"todos","project_name":null,"follow_up":true}', [PREV])
    assert i.intent == "todos"


def test_follow_up_with_a_name_keeps_search():
    i = parse_intent('{"intent":"search","project_name":"whiteborag","follow_up":true}', [PREV])
    assert i.intent == "search"


def test_follow_up_without_history_stays_search():
    assert parse_intent('{"intent":"search","follow_up":true}', []).intent == "search"


def test_follow_up_ignores_junk_previous_intent():
    junk = Turn("q", {"intent": "weather"}, None, [])
    assert parse_intent('{"intent":"search","follow_up":true}', [junk]).intent == "search"


def test_as_dict_has_every_field():
    assert set(FALLBACK.as_dict()) == {
        "intent", "project_name", "section", "date_from", "date_to", "before", "follow_up"
    }


def test_prompt_has_no_previous_answers():
    p = build_prompt("q", [Turn("q0", {"intent": "todos"}, "SECRET ANSWER", [])], ["whiteBORAG"], "2026-10-19")
    assert "SECRET ANSWER" not in p and "whiteBORAG" in p and "2026-10-19" in p


def test_prompt_shows_history_and_source_dates():
    p = build_prompt("and the one before that?", [PREV], [], "2026-10-19")
    assert "arch of crawler?" in p and "2026-10-15T08:11:04Z" in p and "tendercrawler" in p
    assert "and the one before that?" in p


def test_prompt_mentions_every_intent():
    p = build_prompt("q", [], [], "2026-10-19")
    assert all(intent in p for intent in INTENTS)
