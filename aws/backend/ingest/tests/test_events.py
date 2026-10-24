import json
from urllib.parse import quote_plus

from ingest.events import parse_key, parse_message

K = "captures/wb-cam-01/2026/10/15/20261015T073208Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg"


def body(*keys, **extra):
    return json.dumps({"Records": [{"s3": {"object": {"key": k}}} for k in keys], **extra})


def test_parse_key():
    c = parse_key(K)
    assert c.s3_key == K
    assert c.device == "wb-cam-01"
    assert c.capture_id == "01M4Z7KFZ5KHCYV4BWHM8RH7BF"
    assert c.captured_at == "2026-10-15T07:32:08Z"
    assert c.date == "2026-10-15"
    assert c.transcript_key == "transcripts/wb-cam-01/2026/10/15/20261015T073208Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.md"
    assert c.normalized_key.endswith("_01M4Z7KFZ5KHCYV4BWHM8RH7BF.normalized.md")


def test_ist_date_rolls_over():
    # 20:00 UTC is 01:30 the next day in India.
    c = parse_key("captures/wb-cam-01/2026/10/15/20261015T200000Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg")
    assert c.date == "2026-10-16"


def test_parse_key_rejects():
    assert parse_key("transcripts/x.md") is None
    assert parse_key(K.replace(".jpg", ".png")) is None
    assert parse_key(K.replace("_01M4Z7KFZ5KHCYV4BWHM8RH7BF", "_01M4Z7KFZ5KHCYV4BWHM8RH7B")) is None


def test_multi_record_body():
    other = K.replace("073208Z", "074627Z")
    jobs, skipped = parse_message(body(K, other))
    assert [j.capture.captured_at for j in jobs] == ["2026-10-15T07:32:08Z", "2026-10-15T07:46:27Z"]
    assert [j.reread for j in jobs] == [False, False]
    assert skipped == []


def test_url_encoded_key():
    jobs, _ = parse_message(body(quote_plus(K)))
    assert jobs[0].capture.capture_id == "01M4Z7KFZ5KHCYV4BWHM8RH7BF"
    assert jobs[0].capture.s3_key == K


def test_test_event():
    test_event = {"Service": "Amazon S3", "Event": "s3:TestEvent", "Bucket": "esp32-cam-whiteborag"}
    assert parse_message(json.dumps(test_event)) == ([], [])


def test_non_matching_key_skipped():
    assert parse_message(body("captures/bad.jpg")) == ([], ["captures/bad.jpg"])


def test_reread_flag():
    jobs, _ = parse_message(body(K, reread=True))
    assert jobs[0].reread is True
