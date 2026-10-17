import pytest

from ingest.normalize import (
    NormalizationError,
    build_prompt,
    decide,
    guard_ok,
    parse_response,
    project_name,
)

V = "# whiteBORAG architecture\n- [x] Test terraform code\n- [ ] Add alarms"


def test_build_prompt_fills_lists():
    prompt = build_prompt(V, ["whiteBORAG"], ["Test terraform code"])
    assert "- whiteBORAG" in prompt
    assert "- Test terraform code" in prompt
    assert V in prompt
    assert "{{" not in prompt


def test_parse_response():
    assert parse_response("Project: whiteBORAG\n---\n# whiteBORAG architecture\n- a") == (
        "whiteBORAG",
        "# whiteBORAG architecture\n- a",
    )
    assert parse_response("Project: none\n---\n# x") == (None, "# x")
    assert parse_response("Project: none\n---\n```markdown\n# x\n- a\n```") == (None, "# x\n- a")


def test_parse_response_malformed_raises():
    with pytest.raises(NormalizationError):
        parse_response("# just markdown")


def test_malformed_response_rejected():
    result = decide(V, "# just markdown")
    assert result.rejected is True
    assert result.chosen == V


def test_guard_flipped_checkbox():
    assert guard_ok("# T\n- [x] a", "# T\n- [ ] a") is False


def test_guard_dropped_checkbox():
    assert guard_ok("# T\n- [x] a\n- [ ] b", "# T\n- [x] a\n- b") is False


def test_guard_line_count():
    assert guard_ok("# T\n- a", "# T\n- a\n- b") is False


def test_guard_allows_title_fix():
    assert guard_ok(
        "# White BORAH architecture\n- [x] Test transform code",
        "# whiteBORAG architecture\n- [x] Test terraform code",
    ) is True


def test_untitled_never_has_project():
    md = "# Lightsail Box (untitled)\n"
    assert project_name(md, md, "Lightsail") is None


def test_colon_overrides_nova():
    md = "# whiteBORAG: Questions"
    assert project_name(md, md, "Questions") == "whiteBORAG"


def test_nova_pick_used():
    md = "# white borAG Questions"
    assert project_name(md, md, "whiteBORAG") == "whiteBORAG"


def test_decide_rejected_uses_verbatim_rules():
    colon = "# tender crawler: plan\n- a"
    result = decide(colon, "Project: tender crawler\n---\n# tender crawler: plan\n- a\n- b")
    assert result.rejected is True
    assert result.chosen == colon
    assert result.project_name == "tender crawler"

    plain = "# tender crawler plan\n- a"
    result = decide(plain, "Project: tender crawler\n---\n# tender crawler plan\n- a\n- b")
    assert result.rejected is True
    assert result.project_name is None


def test_decide_none_reply():
    result = decide(V, None)
    assert result.rejected is True
    assert result.chosen == V


def test_decide_accepts_good_reply():
    reply = "Project: whiteBORAG\n---\n# whiteBORAG architecture\n- [x] Test terraform code\n- [ ] Add alarms"
    result = decide("# White BORAH architecture\n- [x] Test transform code\n- [ ] Add alarms", reply)
    assert result.rejected is False
    assert result.chosen.startswith("# whiteBORAG architecture")
    assert result.project_name == "whiteBORAG"
