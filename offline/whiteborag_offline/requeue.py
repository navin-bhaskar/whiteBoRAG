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
    parser.add_argument("keys", nargs="*", help="capture keys (captures/<device>/...) to ingest again")
    args = parser.parse_args(argv)
    if not args.failed and not args.keys:
        parser.error("give --failed or at least one capture key")
    if bad := [k for k in args.keys if parse_key(k) is None]:
        print(f"not capture keys: {', '.join(bad)}", file=sys.stderr)
        return 2

    queue = JobQueue(db_path or load_config().data_dir / DB_NAME)
    if args.failed:
        print(f"requeued {queue.requeue_failed()} failed job(s)")
    for key in args.keys:
        print(f"queued job {queue.enqueue(key)} for {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
