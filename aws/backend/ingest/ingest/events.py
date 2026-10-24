"""SQS messages carrying S3 event notifications → ingest jobs, one per capture."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import unquote_plus
from zoneinfo import ZoneInfo

CAPTURE_PREFIX = "captures/"
TRANSCRIPT_PREFIX = "transcripts/"
LOCAL_TZ = ZoneInfo("Asia/Kolkata")
KEY_RE = re.compile(
    r"^captures/([a-z0-9-]{1,32})/\d{4}/\d{2}/\d{2}/(\d{8}T\d{6}Z)_([0-9A-HJKMNP-TV-Z]{26})\.jpg$"
)


@dataclass(frozen=True)
class Capture:
    s3_key: str
    device: str
    capture_id: str
    captured_at: str  # ISO UTC, "YYYY-MM-DDTHH:MM:SSZ"
    date: str         # the user's calendar day (Asia/Kolkata), "YYYY-MM-DD"

    @property
    def _transcript_stem(self) -> str:
        return TRANSCRIPT_PREFIX + self.s3_key.removeprefix(CAPTURE_PREFIX).removesuffix(".jpg")

    @property
    def transcript_key(self) -> str:
        return self._transcript_stem + ".md"

    @property
    def normalized_key(self) -> str:
        return self._transcript_stem + ".normalized.md"


@dataclass(frozen=True)
class Job:
    capture: Capture
    reread: bool


def parse_key(key: str) -> Capture | None:
    match = KEY_RE.match(key)
    if not match:
        return None
    device, stamp, capture_id = match.groups()
    at = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    return Capture(
        s3_key=key,
        device=device,
        capture_id=capture_id,
        captured_at=at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        date=at.astimezone(LOCAL_TZ).strftime("%Y-%m-%d"),
    )


def parse_message(body: str) -> tuple[list[Job], list[str]]:
    """Return the jobs in one SQS message body, and the keys skipped as not captures."""
    data = json.loads(body)
    if data.get("Event") == "s3:TestEvent":
        return [], []
    reread = bool(data.get("reread", False))
    jobs, skipped = [], []
    for record in data.get("Records", []):
        key = unquote_plus(record["s3"]["object"]["key"])
        capture = parse_key(key)
        if capture is None:
            skipped.append(key)
        else:
            jobs.append(Job(capture, reread))
    return jobs, skipped
