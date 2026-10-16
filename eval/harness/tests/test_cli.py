from harness.cli import resume_conflicts

NEW = {"prompt_hash": "v2", "models": {"nova-lite": "p1"}, "max_tokens": 1500}


def test_fresh_run_has_no_conflicts():
    assert resume_conflicts({}, NEW) == []


def test_resume_with_changed_prompt_is_a_conflict():
    assert resume_conflicts({**NEW, "prompt_hash": "v1"}, NEW) == ["prompt_hash"]


def test_resume_with_changed_model_profile_is_a_conflict():
    assert resume_conflicts({**NEW, "models": {"nova-lite": "p0"}}, NEW) == ["models"]


def test_keys_missing_from_an_older_run_are_not_conflicts():
    assert resume_conflicts({"prompt_hash": "v2"}, NEW) == []
