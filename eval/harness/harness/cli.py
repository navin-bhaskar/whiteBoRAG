"""harness check | run | score"""

import argparse
import dataclasses
import fnmatch
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import boto3

from harness.config import EVAL_DIR, load_config
from harness.dataset import load_manifest
from harness.engines import EngineError, build_engines, prompt_hash
from harness.ledger import BudgetExceeded, Ledger
from harness.report import score_run, write_report
from harness.runner import run

LEDGER_PATH = EVAL_DIR / "runs" / "ledger.jsonl"
IMAGES_DIR = EVAL_DIR / "images"


RESUME_KEYS = ("prompt_hash", "models", "max_tokens")


def resume_conflicts(old: dict, new: dict) -> list[str]:
    """Settings that differ from the run being resumed; mixing them would make results incomparable."""
    return [key for key in RESUME_KEYS if key in old and old[key] != new[key]]


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True, cwd=EVAL_DIR).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def cmd_check(args) -> int:
    cfg = load_config()
    session = boto3.Session(region_name=cfg.region)
    print("caller:", session.client("sts").get_caller_identity()["Arn"])
    ledger = Ledger(LEDGER_PATH, cfg.budget_usd)
    image_path = min(IMAGES_DIR.glob("*.jpg"), key=lambda p: p.stat().st_size)
    image = image_path.read_bytes()
    print("image:", image_path.name)
    failures = 0
    for engine in build_engines(["all"], dataclasses.replace(cfg, max_tokens=16), session):
        ledger.ensure_room(engine.worst_case_cost())
        try:
            result = engine.run(image)
        except Exception as exc:
            failures += 1
            if isinstance(exc, EngineError) and exc.cost_usd:
                ledger.record({"run": "check", "engine": engine.id, "ok": False, "cost_usd": exc.cost_usd})
            print(f"  {engine.id:22} FAILED {exc!r}")
            continue
        ledger.record({"run": "check", "engine": engine.id, "usage": result.usage,
                       "cost_usd": result.cost_usd})
        print(f"  {engine.id:22} ok  {result.latency_s:.1f}s  ${result.cost_usd:.5f}")
    total = ledger.total()
    print(f"ledger total ${total:.4f}, remaining ${cfg.budget_usd - total:.4f} of ${cfg.budget_usd:.2f}")
    return 1 if failures else 0


def cmd_run(args) -> int:
    cfg = load_config()
    session = boto3.Session(region_name=cfg.region)
    engines = build_engines(args.engines.split(","), cfg, session)
    variants = args.variants.split(",")
    samples = [s for s in load_manifest(EVAL_DIR / "manifest.csv")
               if fnmatch.fnmatch(s.image, args.images)]
    if not samples:
        print(f"no images match {args.images!r}")
        return 1
    run_dir = Path(args.run) if args.run else EVAL_DIR / "runs" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    meta_path = run_dir / "run.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    settings = {"prompt_hash": prompt_hash(cfg), "models": {m.id: m.profile for m in cfg.models.values()},
                "max_tokens": cfg.max_tokens}
    if conflicts := resume_conflicts(meta, settings):
        print(f"refusing to resume {run_dir}: {', '.join(conflicts)} changed since it started; "
              "start a new run instead")
        return 2
    # Resuming with a wider selection grows the run; scoring covers the union.
    merged = lambda key, new: list(dict.fromkeys(meta.get(key, []) + new))
    meta.update(
        engines=merged("engines", [e.id for e in engines]),
        variants=merged("variants", variants),
        images=merged("images", [s.image for s in samples]),
        **settings,
        region=cfg.region,
        git_sha=_git_sha(),
        prices_verified_on=cfg.prices_verified_on,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    ledger = Ledger(LEDGER_PATH, cfg.budget_usd)
    print(f"run {run_dir}: {len(engines)} engines × {len(variants)} variants × {len(samples)} images")
    try:
        stats = run(run_dir, IMAGES_DIR, samples, engines, variants, ledger)
    except BudgetExceeded as exc:
        print(exc)
        return 2
    print(f"done {stats.done}, skipped {stats.skipped}, failed {stats.failed}, spent ${stats.spent_usd:.4f}")
    cmd_score(argparse.Namespace(run_dir=str(run_dir)))
    print(f"ledger total ${ledger.total():.4f} of ${cfg.budget_usd:.2f}")
    return 1 if stats.failed else 0


def cmd_score(args) -> int:
    run_dir = Path(args.run_dir)
    write_report(run_dir, score_run(run_dir, EVAL_DIR))
    print("summary:", run_dir / "summary.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="harness")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="verify credentials and one real call per engine").set_defaults(func=cmd_check)
    p_run = sub.add_parser("run", help="run engines over the eval images")
    p_run.add_argument("--engines", default="all")
    p_run.add_argument("--variants", default="raw,enhanced")
    p_run.add_argument("--images", default="*", help="fnmatch glob on the image file name")
    p_run.add_argument("--run", help="existing run directory to resume")
    p_run.set_defaults(func=cmd_run)
    p_score = sub.add_parser("score", help="score a run directory without calling AWS")
    p_score.add_argument("run_dir")
    p_score.set_defaults(func=cmd_score)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
