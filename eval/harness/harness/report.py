"""Score a run directory offline and write scores.csv and summary.md."""

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from harness.dataset import load_manifest, parse_markdown
from harness.engines import engine_dir
from harness.scoring import (
    cer,
    checkbox_accuracy,
    edge_scores,
    hallucination_rate,
    normalize,
    word_scores,
)

SCORE_FIELDS = ["engine", "variant", "image", "environment", "ok", "word_precision", "word_recall",
                "word_f1", "cer", "hallucination", "edge_precision", "edge_recall", "checkbox_acc",
                "latency_s", "cost_usd"]
SUMMARY_COLUMNS = [("word F1", "word_f1"), ("precision", "word_precision"), ("recall", "word_recall"),
                   ("CER", "cer"), ("hallucination", "hallucination"), ("edge P", "edge_precision"),
                   ("edge R", "edge_recall"), ("checkbox", "checkbox_acc"), ("latency s", "latency_s"),
                   ("$/capture", "cost_usd")]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _score(gt_md: str, transcript: str, structured: bool) -> dict:
    ref, hyp = normalize(gt_md), normalize(transcript)
    precision, recall, f1 = word_scores(ref, hyp)
    row = {"word_precision": precision, "word_recall": recall, "word_f1": f1,
           "cer": cer(ref, hyp), "hallucination": hallucination_rate(ref, hyp),
           "edge_precision": None, "edge_recall": None, "checkbox_acc": None}
    if structured:
        gt, out = parse_markdown(gt_md), parse_markdown(transcript)
        row["edge_precision"], row["edge_recall"] = edge_scores(gt.edges, out.edges)
        row["checkbox_acc"] = checkbox_accuracy(gt.checkboxes, out.checkboxes)
    return row


def score_run(run_dir: Path, eval_dir: Path) -> list[dict]:
    meta = json.loads(_read(run_dir / "run.json"))
    samples = {s.image: s for s in load_manifest(eval_dir / "manifest.csv")}
    rows = []
    for engine in meta["engines"]:
        for variant in meta["variants"]:
            for image in meta["images"]:
                sample = samples[image]
                stem = Path(image).stem
                row = {"engine": engine, "variant": variant, "image": image,
                       "environment": sample.environment, "ok": False}
                response_path = run_dir / "responses" / engine_dir(engine) / variant / f"{stem}.json"
                response = json.loads(_read(response_path)) if response_path.exists() else {}
                if response.get("ok"):
                    transcript = _read(run_dir / "transcripts" / engine_dir(engine) / variant / f"{stem}.md")
                    gt_md = _read(eval_dir / "ground_truth" / sample.ground_truth)
                    row.update(_score(gt_md, transcript, ":" in engine))
                    row.update(ok=True, latency_s=response["latency_s"], cost_usd=response["cost_usd"])
                rows.append(row)
    return rows


def _mean(rows: list[dict], field: str) -> float | None:
    values = [r[field] for r in rows if r.get(field) is not None]
    return mean(values) if values else None


def _fmt(value: float | None) -> str:
    return "–" if value is None else f"{value:.3f}"


def write_report(run_dir: Path, rows: list[dict]) -> None:
    with open(run_dir / "scores.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SCORE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    meta = json.loads(_read(run_dir / "run.json"))
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["engine"], row["variant"])].append(row)
    environments = sorted({r["environment"] for r in rows})

    def ok_rows(key):
        return [r for r in groups[key] if r["ok"]]

    ranked = sorted(groups, key=lambda k: _mean(ok_rows(k), "word_f1") or -1, reverse=True)

    lines = [
        f"# OCR eval — {run_dir.name}",
        "",
        f"Prompt `{meta.get('prompt_hash', '?')}` · region `{meta.get('region', '?')}`",
        "",
        "## By engine × variant",
        "",
        "| engine | variant | n ok | failed | " + " | ".join(label for label, _ in SUMMARY_COLUMNS) + " |",
        "|---|---|---|---|" + "---|" * len(SUMMARY_COLUMNS),
    ]
    for key in ranked:
        ok = ok_rows(key)
        cells = [_fmt(_mean(ok, field)) for _, field in SUMMARY_COLUMNS]
        cells[-1] = "–" if _mean(ok, "cost_usd") is None else f"{_mean(ok, 'cost_usd'):.5f}"
        lines.append(f"| {key[0]} | {key[1]} | {len(ok)} | {len(groups[key]) - len(ok)} | "
                     + " | ".join(cells) + " |")

    lines += ["", "## Word F1 by environment", "",
              "| engine | variant | " + " | ".join(environments) + " |",
              "|---|---|" + "---|" * len(environments)]
    for key in ranked:
        ok = ok_rows(key)
        cells = [_fmt(_mean([r for r in ok if r["environment"] == env], "word_f1")) for env in environments]
        lines.append(f"| {key[0]} | {key[1]} | " + " | ".join(cells) + " |")

    total = sum(r["cost_usd"] for r in rows if r["ok"])
    lines += ["", "## Cost", "", f"Total for this run: ${total:.4f}", "",
              "## Recommendation", "", "_To be written after reviewing the results._", ""]
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
