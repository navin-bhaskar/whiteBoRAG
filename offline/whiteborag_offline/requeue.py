"""Queue captures for ingest again: failed jobs, or captures by key. A running server picks them up.

Run from offline/:
    uv run python -m whiteborag_offline.requeue --failed
    uv run python -m whiteborag_offline.requeue captures/cam-01/2026/10/27/<stamp>_<id>.jpg

Ingesting a capture again reuses its stored transcripts, so a hand-corrected title takes effect.
"""

import argparse
import sys
from pathlib import Path

from ingest.events import parse_key

from whiteborag_offline.config import load_config
from whiteborag_offline.deps import DB_NAME
from whiteborag_offline.jobs import JobQueue


def main(argv: list[str] | None = None, db_path: Path | None = None) -> int:
    parser = argparse.ArgumentParser(prog="requeue")
    parser.add_argument("--failed", action="store_true", help="put every failed job back in the queue")
    parser.add_argument("--config", type=Path, help="the config whose data_dir holds the queue (default: offline)")
    parser.add_argument("keys", nargs="*", help="capture keys (captures/<device>/...) to ingest again")
    args = parser.parse_args(argv)
    if not args.failed and not args.keys:
        parser.error("give --failed or at least one capture key")
    if bad := [k for k in args.keys if parse_key(k) is None]:
        print(f"not capture keys: {', '.join(bad)}", file=sys.stderr)
        return 2

    if args.config and not args.config.exists():
        print(f"no config at {args.config}", file=sys.stderr)  # don't fall back to offline's queue
        return 2

    cfg = load_config(args.config) if args.config else load_config()
    if db_path is None:
        cfg.data_dir.mkdir(parents=True, exist_ok=True)  # as the server does on start
    queue = JobQueue(db_path or cfg.data_dir / DB_NAME)
    if args.failed:
        print(f"requeued {queue.requeue_failed()} failed job(s)")
    for key in args.keys:
        print(f"queued job {queue.enqueue(key)} for {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
