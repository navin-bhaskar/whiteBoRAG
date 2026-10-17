import json
from pathlib import Path

from fakes import FakeBlobs, FakeEmbedder, FakeReader, FakeVectors, InMemoryStore
from ingest.handler import handle
from ingest.pipeline import Deps, Reply

ARCH = (Path(__file__).parent / "fixtures" / "architecture.md").read_text(encoding="utf-8")
GOOD = "captures/wb-cam-01/2026/10/15/20261015T084632Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg"
OTHER = "captures/wb-cam-01/2026/10/15/20261015T090000Z_01M4Z7KFZ5KHCYV4BWHM8RH7BG.jpg"


def now() -> str:
    return "2026-10-17T10:00:00Z"


def deps(files=None) -> Deps:
    return Deps(
        store=InMemoryStore(),
        blobs=FakeBlobs({GOOD: b"jpeg", OTHER: b"jpeg"} if files is None else files),
        reader=FakeReader(Reply(ARCH, False), Reply("Project: whiteBORAG\n---\n" + ARCH, False)),
        embedder=FakeEmbedder(),
        vectors=FakeVectors(),
    )


def sqs(*messages: tuple[str, str]) -> dict:
    """SQS event whose records each carry an S3 notification for one key."""
    return {
        "Records": [
            {"messageId": mid, "body": json.dumps({"Records": [{"s3": {"object": {"key": key}}}]})}
            for mid, key in messages
        ]
    }


def log_lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


def test_failure_reported_per_message():
    d = deps()
    embed = d.embedder.embed

    def fail_for_second(text):
        if len(d.store.captures) == 1:
            raise RuntimeError("bedrock throttled")
        return embed(text)

    d.embedder.embed = fail_for_second
    assert handle(sqs(("m1", GOOD), ("m2", OTHER)), d, now) == {"batchItemFailures": [{"itemIdentifier": "m2"}]}


def test_test_event_succeeds():
    event = {"Records": [{"messageId": "m1", "body": json.dumps({"Event": "s3:TestEvent"})}]}
    assert handle(event, deps(), now) == {"batchItemFailures": []}


def test_missing_image_is_skipped(capsys):
    assert handle(sqs(("m1", GOOD)), deps(files={}), now) == {"batchItemFailures": []}
    [line] = log_lines(capsys)
    assert line["outcome"] == "skipped_missing_image"


def test_log_line(capsys):
    d = deps()
    handle(sqs(("m1", GOOD)), d, now)
    [line] = log_lines(capsys)
    assert {"capture_id", "outcome", "project", "todos", "vectors", "normalization_rejected", "reused"} <= set(line)
    assert (line["outcome"], line["project"], line["todos"], line["vectors"]) == ("ingested", "whiteborag", 3, 2)

    d.embedder.embed = lambda text: (_ for _ in ()).throw(RuntimeError("boom"))
    handle(sqs(("m2", GOOD)), d, now)
    [line] = log_lines(capsys)
    assert line["outcome"] == "failed"
    assert "boom" in line["error"]


def test_bad_key_logged_skipped(capsys):
    assert handle(sqs(("m1", "captures/not-a-capture.txt")), deps(), now) == {"batchItemFailures": []}
    [line] = log_lines(capsys)
    assert line["outcome"] == "skipped_bad_key"
    assert line["key"] == "captures/not-a-capture.txt"
