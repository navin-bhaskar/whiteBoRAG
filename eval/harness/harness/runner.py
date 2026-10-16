"""Run engines × variants over samples into a resumable run directory, within the budget."""

import json
from dataclasses import dataclass
from pathlib import Path

from harness.dataset import Sample
from harness.engines import Engine, engine_dir
from harness.ledger import BudgetExceeded, Ledger
from harness.preprocess import prepare


@dataclass
class RunStats:
    done: int = 0
    skipped: int = 0
    failed: int = 0
    spent_usd: float = 0.0


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=str, ensure_ascii=False, indent=2), encoding="utf-8")


def _prepare_inputs(run_dir: Path, images_dir: Path, samples: list[Sample], variants: list[str]) -> None:
    for variant in variants:
        out_dir = run_dir / "inputs" / variant
        notes_path = out_dir / "notes.json"
        notes = json.loads(notes_path.read_text(encoding="utf-8")) if notes_path.exists() else {}
        for sample in samples:
            target = out_dir / sample.image
            if target.exists():
                continue
            data, note = prepare((images_dir / sample.image).read_bytes(), variant)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            notes[sample.image] = note
        _write_json(notes_path, notes)


def _is_done(path: Path) -> bool:
    return path.exists() and json.loads(path.read_text(encoding="utf-8")).get("ok", False)


def run(run_dir: Path, images_dir: Path, samples: list[Sample], engines: list[Engine],
        variants: list[str], ledger: Ledger) -> RunStats:
    _prepare_inputs(run_dir, images_dir, samples, variants)
    stats = RunStats()
    pending = []
    for engine in engines:
        for variant in variants:
            for sample in samples:
                stem = Path(sample.image).stem
                response = run_dir / "responses" / engine_dir(engine.id) / variant / f"{stem}.json"
                if _is_done(response):
                    stats.skipped += 1
                else:
                    pending.append((engine, variant, sample, stem, response))

    estimate = sum(engine.worst_case_cost() for engine, *_ in pending)
    total = ledger.total()
    if total + estimate > ledger.budget_usd:
        raise BudgetExceeded(
            f"run refused: ledger total ${total:.4f} + worst-case estimate ${estimate:.4f} "
            f"for {len(pending)} calls > cap ${ledger.budget_usd:.2f}"
        )

    for n, (engine, variant, sample, stem, response) in enumerate(pending, 1):
        ledger.ensure_room(engine.worst_case_cost())
        image = (run_dir / "inputs" / variant / sample.image).read_bytes()
        try:
            result = engine.run(image)
        except Exception as exc:
            _write_json(response, {"ok": False, "error": repr(exc)})
            stats.failed += 1
            print(f"[{n}/{len(pending)}] {engine.id} {variant} {sample.image} FAILED {exc!r}")
            continue
        _write_json(response, {"ok": True, "raw": result.raw, "usage": result.usage,
                               "cost_usd": result.cost_usd, "latency_s": result.latency_s})
        transcript = run_dir / "transcripts" / engine_dir(engine.id) / variant / f"{stem}.md"
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_text(result.text, encoding="utf-8")
        ledger.record({"run": run_dir.name, "engine": engine.id, "variant": variant,
                       "image": sample.image, "usage": result.usage, "cost_usd": result.cost_usd})
        stats.done += 1
        stats.spent_usd += result.cost_usd
        print(f"[{n}/{len(pending)}] {engine.id} {variant} {sample.image} ok ${result.cost_usd:.5f}")
    return stats
