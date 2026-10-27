import csv
import json

import pytest
from harness.engines import EngineResult
from harness.ledger import BudgetExceeded

from fakes import FakeLlm
from whiteborag_offline.eval import bakeoff
from whiteborag_offline.eval.engines import OcrCache

IMAGE = "20261015T073208Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg"
GT = "# Plan\n- [ ] write tests\n- ship it\n"


def _eval_dir(tmp_path):
    eval_dir = tmp_path / "eval"
    (eval_dir / "images").mkdir(parents=True)
    (eval_dir / "ground_truth").mkdir()
    (eval_dir / "images" / IMAGE).write_bytes(b"\xff\xd8fake")
    (eval_dir / "ground_truth" / "plan.md").write_text(GT, encoding="utf-8")
    (eval_dir / "manifest.csv").write_text(
        f"image,ground_truth,environment,notes\n{IMAGE},plan.md,night-dim,\n", encoding="utf-8")
    return eval_dir


def _baseline(tmp_path):
    path = tmp_path / "scores.csv"
    fields = ["engine", "variant", "image", "ok", "word_f1", "cer", "hallucination",
              "edge_precision", "edge_recall", "checkbox_acc", "latency_s"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerow({"engine": "bedrock:nova-2-lite", "variant": "raw", "image": IMAGE, "ok": "True",
                    "word_f1": "0.847", "cer": "0.084", "hallucination": "0.1", "edge_precision": "",
                    "edge_recall": "", "checkbox_acc": "1.0", "latency_s": "2.0"})
        w.writerow({"engine": "bedrock:nova-2-lite", "variant": "enhanced", "image": IMAGE, "ok": "True",
                    "word_f1": "0.5", "cer": "0.3", "hallucination": "0.1", "edge_precision": "",
                    "edge_recall": "", "checkbox_acc": "", "latency_s": "2.0"})
    return path


class EchoEngine:
    id = "local:echo"
    structured = True

    def worst_case_cost(self) -> float:
        return 0.0

    def run(self, image: bytes) -> EngineResult:
        return EngineResult(GT, {}, {}, 0.0, 1.5)


def test_bakeoff_run_scores_with_harness(tmp_path):
    eval_dir = _eval_dir(tmp_path)
    run_dir = tmp_path / "run"
    stats = bakeoff.run_bakeoff(run_dir, eval_dir, "*", [EchoEngine()], _baseline(tmp_path))
    assert stats.done == 1
    response = json.loads((run_dir / "responses" / "local_echo" / "raw" / f"{IMAGE[:-4]}.json").read_text())
    assert response["ok"] is True
    assert (run_dir / "scores.csv").exists()
    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "| local:echo | raw | 1 | 0 | 1.000" in summary
    assert "## Baseline (AWS, Nova 2 Lite raw)" in summary
    assert "| bedrock:nova-2-lite | raw | 1 | 0.847 |" in summary


def test_bakeoff_rescore_keeps_one_baseline(tmp_path):
    eval_dir = _eval_dir(tmp_path)
    run_dir = tmp_path / "run"
    bakeoff.run_bakeoff(run_dir, eval_dir, "*", [EchoEngine()], _baseline(tmp_path))
    bakeoff.score(run_dir, eval_dir, _baseline(tmp_path))
    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert summary.count("## Baseline (AWS, Nova 2 Lite raw)") == 1


def test_bakeoff_resume_merges_engines(tmp_path):
    eval_dir = _eval_dir(tmp_path)
    run_dir = tmp_path / "run"

    class Other(EchoEngine):
        id = "local:other"

    bakeoff.run_bakeoff(run_dir, eval_dir, "*", [EchoEngine()], _baseline(tmp_path))
    stats = bakeoff.run_bakeoff(run_dir, eval_dir, "*", [Other(), EchoEngine()], _baseline(tmp_path))
    assert (stats.done, stats.skipped) == (1, 1)
    meta = json.loads((run_dir / "run.json").read_text())
    assert meta["engines"] == ["local:echo", "local:other"]
    assert meta["variants"] == ["raw"]


def test_fill_ocr_cache_skips_cached(tmp_path):
    eval_dir = _eval_dir(tmp_path)
    cache = OcrCache(tmp_path / "cache")
    llm = FakeLlm("plain text")
    cand = bakeoff.Candidate("glm", "glm-ocr", "ocr", None, "Text Recognition:")
    assert bakeoff.fill_ocr_cache(cand, llm, cache, eval_dir, "*") == 1
    assert bakeoff.fill_ocr_cache(cand, llm, cache, eval_dir, "*") == 0
    assert llm.calls[0]["prompt"] == "Text Recognition:"
    assert cache.get("glm", b"\xff\xd8fake") == "plain text"


def test_build_engines_by_id(tmp_path):
    path = tmp_path / "candidates.toml"
    path.write_text(
        'base_url = "http://localhost:1234/v1"\n'
        'restructure_text_model = "llama"\n'
        'restructure_vision_model = "qwen3-vl"\n\n'
        '[candidates.glm]\nmodel = "glm-ocr"\nkind = "ocr"\nocr_prompt = "Text Recognition:"\n',
        encoding="utf-8")
    cands = bakeoff.load_candidates(path)
    urls = []
    engines = bakeoff.build_engines(["local:glm", "local-hv:glm", "local-ht:glm"], cands,
                                    OcrCache(tmp_path), client_for=lambda url, key: urls.append(url) or FakeLlm())
    assert [e.id for e in engines] == ["local:glm", "local-hv:glm", "local-ht:glm"]
    assert set(urls) == {"http://localhost:1234/v1"}


def _candidates_file(tmp_path, extra=""):
    path = tmp_path / "cands" / "candidates.toml"
    path.parent.mkdir()
    path.write_text(
        'base_url = "https://router.test/v1"\n' + extra +
        'restructure_text_model = "t"\nrestructure_vision_model = "v"\n\n'
        '[candidates.nova]\nmodel = "amazon/nova-2-lite-v1"\nkind = "vlm"\n', encoding="utf-8")
    return path


def test_candidates_path_option(tmp_path, monkeypatch):
    path = _candidates_file(tmp_path)
    seen = {}

    def fake_run(run_dir, eval_dir, images, engines, budget_usd=0.0):
        seen.update(run_dir=run_dir, engines=[e.id for e in engines])
        return bakeoff.RunStats()

    monkeypatch.setattr(bakeoff, "run_bakeoff", fake_run)
    assert bakeoff.main(["--candidates", str(path), "run", "--engines", "local:nova"]) == 0
    assert seen["engines"] == ["local:nova"]
    assert seen["run_dir"].parent == path.parent / "runs"


def test_api_key_env_builds_keyed_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTER_KEY", "sk-test")
    cands = bakeoff.load_candidates(_candidates_file(tmp_path, 'api_key_env = "ROUTER_KEY"\n'))
    assert cands.api_key_env == "ROUTER_KEY"
    seen = []
    bakeoff.build_engines(["local:nova"], cands, OcrCache(tmp_path),
                          client_for=lambda url, key: seen.append((url, key)) or FakeLlm())
    assert seen == [("https://router.test/v1", "sk-test")]


def test_budget_stops_a_paid_run(tmp_path):
    class Paid(EchoEngine):
        def run(self, image):
            return EngineResult(GT, {}, {}, 0.01, 1.0)

    class Second(Paid):
        id = "local:second"

    eval_dir = _eval_dir(tmp_path)
    run_dir = tmp_path / "run"
    with pytest.raises(BudgetExceeded):
        bakeoff.run_bakeoff(run_dir, eval_dir, "*", [Paid(), Second()], _baseline(tmp_path), budget_usd=0.005)
    assert bakeoff.load_candidates(_candidates_file(tmp_path, "budget_usd = 2.5\n")).budget_usd == 2.5
