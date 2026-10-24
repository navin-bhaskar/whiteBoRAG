from harness.config import EVAL_DIR, load_config


def test_load_default_config():
    cfg = load_config()
    assert cfg.region == "ap-south-1"
    assert cfg.budget_usd == 5.00
    assert cfg.price_margin == 1.20
    assert cfg.max_tokens == 1500
    assert set(cfg.models) == {"nova-lite", "nova-pro", "nova-2-lite"}
    assert cfg.models["nova-2-lite"].profile == "global.amazon.nova-2-lite-v1:0"
    assert cfg.prompt_path.name == "transcribe-v2.md"


def test_eval_dir_points_at_dataset():
    assert (EVAL_DIR / "manifest.csv").exists()


def test_worst_case_input_covers_observed_calls():
    # The full run saw up to 2,658 input tokens (hybrid: image + prompt + Textract hints).
    assert load_config().worst_case_input_tokens >= 4000
