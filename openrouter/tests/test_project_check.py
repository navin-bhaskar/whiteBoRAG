import pytest

from whiteborag_openrouter.eval import project_check
from whiteborag_offline.llm import Completion

ARCH = "# WhiteBoRAG architecture\n- ingest\n- query"
CRAWL = "# Crawlers\n- fetch pages"
GOALS = "# WhileBORAG local: goals\n- [ ] ship"


class FakeLlm:
    """Transcribes any image as the goals board; normalizes by echoing the transcript under a Project line."""

    def __init__(self, goals_title: str = "whiteBoRAG local: goals") -> None:
        self.goals_title = goals_title

    def chat(self, model, prompt, image=None, max_tokens=1500):
        if image is not None:
            reply = GOALS
        elif ARCH in prompt:
            reply = f"Project: WhiteBoRAG\n---\n{ARCH}"
        elif CRAWL in prompt:
            reply = f"Project: none\n---\n{CRAWL}"
        else:
            reply = f"Project: none\n---\n{GOALS.replace('WhileBORAG local: goals', self.goals_title)}"
        return Completion(reply, False, 0.1, 0.001)


@pytest.fixture
def setup(tmp_path):
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "manifest.csv").write_text(
        "image,ground_truth,environment,notes\na.jpg,architecture-v1.md,day,\nc.jpg,crawlers-v1.md,day,\n",
        encoding="utf-8")
    run_dir = tmp_path / "run"
    transcripts = run_dir / "transcripts" / "local_nova" / "raw"
    transcripts.mkdir(parents=True)
    (transcripts / "a.md").write_text(ARCH, encoding="utf-8")
    (transcripts / "c.md").write_text(CRAWL, encoding="utf-8")
    goals = tmp_path / "goals.jpg"
    goals.write_bytes(b"\xff\xd8goals")
    return run_dir, eval_dir, goals


def _check(setup, llm):
    run_dir, eval_dir, goals = setup
    return project_check.check("nova", "amazon/nova-2-lite-v1", llm, run_dir, eval_dir=eval_dir, goals_image=goals)


def test_scores_against_expected(setup):
    result = _check(setup, FakeLlm())
    assert (result.no_known, result.whiteborag_known, result.total) == (2, 2, 2)


def test_colon_title_uses_normalized_spelling(setup):
    result = _check(setup, FakeLlm())
    assert result.goals_ok
    assert result.goals_project == "whiteBoRAG local"


def test_uncorrected_title_fails_goals(setup):
    result = _check(setup, FakeLlm(goals_title="WhileBORAG local: goals"))
    assert not result.goals_ok
    assert result.goals_project == "WhileBORAG local"


def test_cost_summed(setup):
    # 2 transcripts x 2 conditions, plus transcribing and normalizing the goals board
    assert _check(setup, FakeLlm()).cost_usd == pytest.approx(0.006)


def test_expected_projects():
    assert project_check.EXPECTED["rag-revision-v1.md"] == {"ragrevision", None}
    assert project_check.GOALS_EXPECTED == "whiteboraglocal"
