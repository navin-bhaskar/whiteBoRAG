import csv
import json

from harness.report import SCORE_FIELDS, score_run, write_report


def test_score_and_report(tmp_path):
    ev = tmp_path / "eval"
    (ev / "ground_truth").mkdir(parents=True)
    (ev / "ground_truth/g.md").write_text(
        '# T\n\nEdges:\n- A box → B box, labelled "x"\n\n## L\n- [x] done item\n', encoding="utf-8")
    (ev / "manifest.csv").write_text(
        "image,ground_truth,environment,notes\na.jpg,g.md,daylight,\n", encoding="utf-8")
    rd = tmp_path / "run"
    (rd / "transcripts/bedrock_m/raw").mkdir(parents=True)
    (rd / "responses/bedrock_m/raw").mkdir(parents=True)
    (rd / "run.json").write_text(json.dumps({
        "engines": ["bedrock:m", "textract"], "variants": ["raw"], "images": ["a.jpg"],
        "prompt_hash": "abc", "region": "ap-south-1"}), encoding="utf-8")
    (rd / "transcripts/bedrock_m/raw/a.md").write_text(
        '# T\nEdges:\n- A box → B box, labelled "x"\n## L\n- [x] done item\n', encoding="utf-8")
    (rd / "responses/bedrock_m/raw/a.json").write_text(
        json.dumps({"ok": True, "latency_s": 1.5, "cost_usd": 0.002}), encoding="utf-8")

    rows = score_run(rd, ev)
    by = {r["engine"]: r for r in rows}
    assert by["bedrock:m"]["word_f1"] == 1.0 and by["bedrock:m"]["edge_recall"] == 1.0
    assert by["bedrock:m"]["checkbox_acc"] == 1.0 and by["bedrock:m"]["environment"] == "daylight"
    assert by["textract"]["ok"] is False

    write_report(rd, rows)
    summary = (rd / "summary.md").read_text(encoding="utf-8")
    assert "## By engine × variant" in summary and "## Recommendation" in summary
    assert "| bedrock:m | raw |" in summary
    with open(rd / "scores.csv", encoding="utf-8") as f:
        assert list(csv.DictReader(f))[0].keys() == set(SCORE_FIELDS)


def test_summary_columns_match_headers(tmp_path):
    rd = tmp_path / "run"
    rd.mkdir()
    (rd / "run.json").write_text(json.dumps({"engines": ["textract"]}), encoding="utf-8")
    row = {"engine": "textract", "variant": "raw", "image": "a.jpg", "environment": "env", "ok": True,
           "word_precision": 0.5, "word_recall": 0.25, "word_f1": 0.333, "cer": 0.1,
           "hallucination": 0.2, "edge_precision": None, "edge_recall": None, "checkbox_acc": None,
           "latency_s": 1.0, "cost_usd": 0.0018}
    write_report(rd, [row])
    table = [l for l in (rd / "summary.md").read_text(encoding="utf-8").splitlines() if l.startswith("|")]
    header = [c.strip() for c in table[0].strip("|").split("|")]
    values = [c.strip() for c in table[2].strip("|").split("|")]
    cell = dict(zip(header, values))
    assert (cell["word F1"], cell["precision"], cell["recall"]) == ("0.333", "0.500", "0.250")
    assert cell["$/capture"] == "0.00180"


def test_rescoring_keeps_written_recommendation(tmp_path):
    rd = tmp_path / "run"
    rd.mkdir()
    (rd / "run.json").write_text(json.dumps({"engines": ["textract"]}), encoding="utf-8")
    (rd / "recommendation.md").write_text("Pick nova-2-lite.", encoding="utf-8")
    row = {"engine": "textract", "variant": "raw", "image": "a.jpg", "environment": "env", "ok": False}
    write_report(rd, [row])
    write_report(rd, [row])
    summary = (rd / "summary.md").read_text(encoding="utf-8")
    assert summary.rstrip().endswith("Pick nova-2-lite.")
    assert "_To be written" not in summary
