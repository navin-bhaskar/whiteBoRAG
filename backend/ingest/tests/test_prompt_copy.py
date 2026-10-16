from pathlib import Path

from ingest import PROMPTS_DIR

EVAL_PROMPT = Path(__file__).parents[3] / "eval/harness/harness/prompts/transcribe-v2.md"


def test_prompt_copy_identical():
    assert (PROMPTS_DIR / "transcribe-v2.md").read_bytes() == EVAL_PROMPT.read_bytes()
