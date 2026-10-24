"""The local OCR bake-off: run local candidates through the AWS eval harness and compare with Nova 2 Lite.

Run from offline/:
    uv run python -m whiteborag_offline.eval.bakeoff ocr --candidate glm-ocr
    uv run python -m whiteborag_offline.eval.bakeoff run --run eval/runs/bakeoff --engines local:glm-ocr,local-hv:glm-ocr
    uv run python -m whiteborag_offline.eval.bakeoff score --run eval/runs/bakeoff
"""

import argparse
import csv
import fnmatch
import json
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from harness.config import EVAL_DIR, load_config
from harness.dataset import load_manifest
from harness.engines import prompt_hash, prompt_text
from harness.ledger import Ledger
from harness.report import score_run, write_report
from harness.runner import RunStats, run

from whiteborag_offline import OFFLINE_DIR, PROMPTS_DIR
from whiteborag_offline.eval.engines import LocalHybridText, LocalHybridVision, LocalRaw, OcrCache
from whiteborag_offline.llm import LlmClient, LlmError

CANDIDATES = OFFLINE_DIR / "eval" / "candidates.toml"
RUNS_DIR = OFFLINE_DIR / "eval" / "runs"
CACHE_DIR = OFFLINE_DIR / "eval" / "ocr-cache"
BASELINE_CSV = EVAL_DIR / "runs" / "20261016T122626Z" / "scores.csv"
BASELINE_HEADING = "## Baseline (AWS, Nova 2 Lite raw)"
RESTRUCTURE_PROMPT = PROMPTS_DIR / "restructure-v1.md"
VARIANTS = ["raw"]  # production ingest doesn't enhance photos, so neither does the bake-off


@dataclass(frozen=True)
class Candidate:
    id: str
    model: str
    kind: str              # "ocr" (dedicated OCR model) or "vlm" (general vision model)
    base_url: str | None   # a server other than the default one
    ocr_prompt: str | None  # the model's own plain-OCR prompt


@dataclass(frozen=True)
class Candidates:
    base_url: str
    restructure_text_model: str
    restructure_vision_model: str
    by_id: dict[str, Candidate]


def load_candidates(path: Path = CANDIDATES) -> Candidates:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    by_id = {
        cid: Candidate(cid, c["model"], c["kind"], c.get("base_url") or None, c.get("ocr_prompt") or None)
        for cid, c in raw.get("candidates", {}).items()
    }
    return Candidates(raw["base_url"], raw["restructure_text_model"], raw["restructure_vision_model"], by_id)


def build_engines(ids: list[str], cands: Candidates, cache: OcrCache,
                  client_for: Callable[[str], LlmClient] = LlmClient) -> list:
    clients: dict[str, LlmClient] = {}

    def client(url: str | None) -> LlmClient:
        url = url or cands.base_url
        if url not in clients:
            clients[url] = client_for(url)
        return clients[url]

    transcribe = prompt_text(load_config())
    engines = []
    for engine_id in ids:
        kind, _, cid = engine_id.partition(":")
        cand = cands.by_id.get(cid)
        if cand is None:
            raise ValueError(f"unknown candidate in {engine_id!r}; add it to {CANDIDATES.name}")
        if kind == "local":
            engines.append(LocalRaw(client(cand.base_url), cid, cand.model, transcribe))
        elif kind == "local-hv":
            engines.append(LocalHybridVision(client(None), cid, cands.restructure_vision_model, transcribe, cache))
        elif kind == "local-ht":
            restructure = RESTRUCTURE_PROMPT.read_text(encoding="utf-8")
            engines.append(LocalHybridText(client(None), cid, cands.restructure_text_model, restructure, cache))
        else:
            raise ValueError(f"unknown engine kind in {engine_id!r}: use local, local-hv or local-ht")
    return engines


def _samples(eval_dir: Path, images: str):
    return [s for s in load_manifest(eval_dir / "manifest.csv") if fnmatch.fnmatch(s.image, images)]


def fill_ocr_cache(cand: Candidate, client: LlmClient, cache: OcrCache, eval_dir: Path, images: str) -> int:
    """Plain-OCR each raw photo with the candidate; returns how many were new."""
    done = 0
    samples = _samples(eval_dir, images)
    for n, sample in enumerate(samples, 1):
        image = (eval_dir / "images" / sample.image).read_bytes()
        if cache.get(cand.id, image) is not None:
            continue
        reply = client.chat(cand.model, cand.ocr_prompt or "Transcribe all text in this image.", image=image)
        cache.put(cand.id, image, reply.text or "")
        done += 1
        print(f"[{n}/{len(samples)}] {cand.id} {sample.image} ocr {reply.latency_s:.1f}s")
    return done


def _baseline_rows(baseline_csv: Path) -> list[dict]:
    with open(baseline_csv, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f)
                if r["engine"] == "bedrock:nova-2-lite" and r["variant"] == "raw" and r["ok"] == "True"]


def append_baseline(run_dir: Path, baseline_csv: Path) -> None:
    rows = _baseline_rows(baseline_csv)
    fields = [("word F1", "word_f1"), ("CER", "cer"), ("hallucination", "hallucination"),
              ("edge P", "edge_precision"), ("edge R", "edge_recall"), ("checkbox", "checkbox_acc"),
              ("latency s", "latency_s")]

    def avg(field: str) -> str:
        values = [float(r[field]) for r in rows if r.get(field)]
        return f"{mean(values):.3f}" if values else "–"

    lines = ["", BASELINE_HEADING, "",
             f"From `{baseline_csv.parent.name}`, the run that picked Nova 2 Lite. Same images and scoring.", "",
             "| engine | variant | n ok | " + " | ".join(label for label, _ in fields) + " |",
             "|---|---|---|" + "---|" * len(fields),
             f"| bedrock:nova-2-lite | raw | {len(rows)} | " + " | ".join(avg(f) for _, f in fields) + " |", ""]
    with open(run_dir / "summary.md", "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def score(run_dir: Path, eval_dir: Path = EVAL_DIR, baseline_csv: Path = BASELINE_CSV) -> None:
    write_report(run_dir, score_run(run_dir, eval_dir))  # rewrites summary.md, so the baseline goes on once
    append_baseline(run_dir, baseline_csv)


def run_bakeoff(run_dir: Path, eval_dir: Path, images: str, engines: list,
                baseline_csv: Path = BASELINE_CSV) -> RunStats:
    samples = _samples(eval_dir, images)
    if not samples:
        raise ValueError(f"no images match {images!r}")
    meta_path = run_dir / "run.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    merged = lambda key, new: list(dict.fromkeys(meta.get(key, []) + new))  # noqa: E731
    meta.update(
        engines=merged("engines", [e.id for e in engines]),
        variants=merged("variants", VARIANTS),
        images=merged("images", [s.image for s in samples]),
        models={e.id: e.model for e in engines if hasattr(e, "model")} | meta.get("models", {}),
        prompt_hash=prompt_hash(load_config()),
        region="local",
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    stats = run(run_dir, eval_dir / "images", samples, engines, VARIANTS, Ledger(run_dir / "ledger.jsonl", 0.0))
    score(run_dir, eval_dir, baseline_csv)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bakeoff")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ocr = sub.add_parser("ocr", help="fill the plain-OCR cache for a candidate")
    p_ocr.add_argument("--candidate", required=True)
    p_ocr.add_argument("--images", default="*")
    p_run = sub.add_parser("run", help="run engines over the eval images and score them")
    p_run.add_argument("--engines", required=True)
    p_run.add_argument("--run")
    p_run.add_argument("--images", default="*")
    p_score = sub.add_parser("score", help="re-score a run")
    p_score.add_argument("--run", required=True)
    args = parser.parse_args(argv)

    cands = load_candidates()
    if args.cmd == "score":
        score(Path(args.run))
        return 0
    if args.cmd == "ocr":
        cand = cands.by_id[args.candidate]
        try:
            n = fill_ocr_cache(cand, LlmClient(cand.base_url or cands.base_url), OcrCache(CACHE_DIR), EVAL_DIR,
                               args.images)
        except LlmError as exc:
            print(f"OCR failed: {exc}")
            return 1
        print(f"cached {n} new OCR results for {cand.id}")
        return 0
    run_dir = Path(args.run) if args.run else RUNS_DIR / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    engines = build_engines(args.engines.split(","), cands, OcrCache(CACHE_DIR))
    stats = run_bakeoff(run_dir, EVAL_DIR, args.images, engines)
    print(f"done {stats.done}, skipped {stats.skipped}, failed {stats.failed}; summary in {run_dir / 'summary.md'}")
    return 1 if stats.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
