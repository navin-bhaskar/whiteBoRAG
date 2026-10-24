"""The SQS-triggered Lambda entry point: one JSON log line per capture, failures reported per message."""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable

from ingest.events import parse_message
from ingest.pipeline import Deps, ingest_capture

_deps: Deps | None = None  # Built on the first invocation, reused while the Lambda stays warm.


def _log(**fields) -> None:
    print(json.dumps(fields), flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _handle_record(record: dict, deps: Deps, now: Callable[[], str]) -> bool:
    """Process one SQS message. Returns False if it should be retried."""
    try:
        jobs, skipped = parse_message(record["body"])
    except (ValueError, KeyError, TypeError) as exc:
        _log(message_id=record.get("messageId"), outcome="failed", error=f"bad message: {exc!r}")
        return False
    for key in skipped:
        _log(key=key, outcome="skipped_bad_key")
    ok = True
    for job in jobs:
        try:
            outcome = asdict(ingest_capture(deps, job, now))
        except Exception as exc:  # Any failure: log it and let SQS retry this message, then the DLQ.
            _log(capture_id=job.capture.capture_id, key=job.capture.s3_key, outcome="failed", error=repr(exc))
            ok = False
        else:
            _log(outcome=outcome.pop("status"), date=job.capture.date, key=job.capture.s3_key, **outcome)
    return ok


def handle(event: dict, deps: Deps, now: Callable[[], str]) -> dict:
    failures = [
        {"itemIdentifier": record["messageId"]}
        for record in event.get("Records", [])
        if not _handle_record(record, deps, now)
    ]
    return {"batchItemFailures": failures}


def lambda_handler(event, context) -> dict:
    global _deps
    if _deps is None:
        from ingest.aws import build_deps

        _deps = build_deps()
    return handle(event, _deps, _now)
