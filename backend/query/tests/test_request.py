import base64
import json

import pytest

from query.request import BadRequest, parse_request


def event(d) -> dict:
    return {"body": json.dumps(d)}


def test_valid_request():
    r = parse_request(event({"question": "latest todos?", "history": [], "project": None}))
    assert (r.question, r.history, r.project) == ("latest todos?", [], None)


def test_base64_body():
    body = base64.b64encode(json.dumps({"question": "q", "project": "whiteborag"}).encode()).decode()
    r = parse_request({"body": body, "isBase64Encoded": True})
    assert (r.question, r.project) == ("q", "whiteborag")


def test_question_bounds():
    for q in ["", "   ", "x" * 501, None, 5]:
        with pytest.raises(BadRequest):
            parse_request(event({"question": q}))


def test_bad_body():
    for body in [None, "not json", "[1,2]"]:
        with pytest.raises(BadRequest):
            parse_request({"body": body})


def test_project_must_be_a_string():
    with pytest.raises(BadRequest):
        parse_request(event({"question": "q", "project": 5}))


def test_history_trimmed_to_last_6_and_junk_dropped():
    turns = [{"question": f"q{i}", "understood": {}, "answer": "a", "sources": []} for i in range(50)]
    r = parse_request(event({"question": "q", "history": turns + ["junk", {"answer": "no question"}]}))
    assert [t.question for t in r.history] == ["q44", "q45", "q46", "q47", "q48", "q49"]


def test_history_missing_fields_default():
    r = parse_request(event({"question": "q", "history": [{"question": "q0", "understood": "x", "sources": 3}]}))
    [t] = r.history
    assert (t.understood, t.answer, t.sources) == ({}, None, [])


def test_history_not_a_list():
    with pytest.raises(BadRequest):
        parse_request(event({"question": "q", "history": "oops"}))
