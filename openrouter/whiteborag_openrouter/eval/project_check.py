"""Project-pick check: does each bake-off candidate put boards in the right project?

For each eval photo, the candidate's own bake-off transcript goes through the normalize prompt twice, with no
known projects and with WhiteBoRAG known, and the project decide() settles on (colon rule included) is checked
against EXPECTED. The real goals board is then transcribed and normalized as the first board of its project.

Run from openrouter/ after a bake-off run:
    uv run python -m whiteborag_openrouter.eval.project_check --run eval/runs/<stamp> [--candidates nova-2-lite,...]
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

from whiteborag_openrouter import REPO_DIR
from whiteborag_offline.eval.bakeoff import load_candidates
from whiteborag_offline.keys import api_key
from whiteborag_offline.llm import LlmClient, LlmError

from harness.config import EVAL_DIR
from harness.dataset import load_manifest
from harness.engines import engine_dir
from ingest import PROMPTS_DIR as INGEST_PROMPTS
from ingest.normalize import build_prompt, decide, strip_fence
from ingest.pipeline import TRANSCRIBE_VERSION
from ingest.projects import canonical_key

CANDIDATES = Path(__file__).resolve().parents[2] / "eval" / "candidates.toml"
KNOWN = {"no_known": [], "whiteborag_known": ["WhiteBoRAG"]}

# Canonical project keys each ground-truth board may land in (None: no project).
EXPECTED: dict[str, set[str | None]] = {
    "architecture-v1.md": {"whiteborag"},
    "questions-v1.md": {"whiteborag"},
    "crawlers-v1.md": {None},
    "video-pipeline-v1.md": {None},
    "rag-revision-v1.md": {"ragrevision", None},
}
# The real board "whiteBoRAG local: goals", which Qwen3-VL misread as "WhileBORAG local: goals".
GOALS_IMAGE = REPO_DIR / "offline/data/uploads/cam-01/2026/10/27/20261027T071827Z_01M5Y3K1G1TVGKA642HJT0TY97.jpg"
GOALS_EXPECTED = "whiteboraglocal"


@dataclass
class CheckResult:
    cand_id: str
    no_known: int = 0
    whiteborag_known: int = 0
    total: int = 0
    goals_ok: bool = False
    goals_project: str | None = None
    cost_usd: float = 0.0


def check(cand_id: str, model: str, client: LlmClient, run_dir: Path, eval_dir: Path = EVAL_DIR,
          goals_image: Path = GOALS_IMAGE) -> CheckResult:
    result = CheckResult(cand_id)

    def project(verbatim: str, known: list[str]) -> str | None:
        reply = client.chat(model, build_prompt(verbatim, known, []))
        result.cost_usd += reply.cost_usd
        return decide(verbatim, strip_fence(reply.text) if reply.text else None).project_name

    transcripts = run_dir / "transcripts" / engine_dir(f"local:{cand_id}") / "raw"
    for sample in load_manifest(eval_dir / "manifest.csv"):
        result.total += 1
        path = transcripts / f"{Path(sample.image).stem}.md"
        if not path.exists():  # a failed bake-off call: scored as wrong in both conditions
            continue
        verbatim = path.read_text(encoding="utf-8")
        for field, known in KNOWN.items():
            name = project(verbatim, known)
            if (canonical_key(name) if name else None) in EXPECTED[sample.ground_truth]:
                setattr(result, field, getattr(result, field) + 1)

    prompt = (INGEST_PROMPTS / f"{TRANSCRIBE_VERSION}.md").read_text(encoding="utf-8")
    reply = client.chat(model, prompt, image=goals_image.read_bytes())
    result.cost_usd += reply.cost_usd
    if reply.text:
        result.goals_project = project(strip_fence(reply.text), [])
        result.goals_ok = result.goals_project is not None and canonical_key(result.goals_project) == GOALS_EXPECTED
    return result


def table(results: list[CheckResult]) -> str:
    lines = ["| candidate | no projects known | WhiteBoRAG known | goals board | project read | cost $ |",
             "|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.cand_id} | {r.no_known}/{r.total} | {r.whiteborag_known}/{r.total} | "
                     f"{'pass' if r.goals_ok else 'FAIL'} | {r.goals_project or 'none'} | {r.cost_usd:.4f} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project_check")
    parser.add_argument("--run", type=Path, required=True, help="a bake-off run directory")
    parser.add_argument("--candidates", help="comma-separated candidate ids (default: all)")
    parser.add_argument("--candidates-file", type=Path, default=CANDIDATES)
    args = parser.parse_args(argv)

    cands = load_candidates(args.candidates_file)
    ids = args.candidates.split(",") if args.candidates else list(cands.by_id)
    client = LlmClient(cands.base_url, api_key=api_key(cands.api_key_env) if cands.api_key_env else None)
    results = []
    for cid in ids:
        try:
            results.append(check(cid, cands.by_id[cid].model, client, args.run))
        except LlmError as exc:
            print(f"{cid}: check failed: {exc}")
            return 1
        print(table(results[-1:]).splitlines()[-1], flush=True)
    report = table(results)
    (args.run / "project_check.md").write_text("# Project-pick check\n\n" + report, encoding="utf-8")
    print("\n" + report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
