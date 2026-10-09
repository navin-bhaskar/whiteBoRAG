import json
import re

import pytest

import handler


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "token")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setenv("BUCKET", "esp32-cam-whiteborag")
    monkeypatch.setenv("PREFIX", "captures/")
    monkeypatch.setenv("URL_TTL", "300")
    monkeypatch.setenv("DEVICE_KEYS", json.dumps({"key-1": "wb-cam-01"}))


def ev(body, key_id="key-1"):
    return {
        "body": json.dumps(body),
        "isBase64Encoded": False,
        "requestContext": {"identity": {"apiKeyId": key_id}},
    }


def call(event):
    resp = handler.lambda_handler(event, None)
    assert resp["headers"]["Content-Type"] == "application/json"
    return resp["statusCode"], json.loads(resp["body"])


def test_success(capsys):
    status, body = call(ev({"device_id": "wb-cam-01", "trigger": "button"}))

    assert status == 200
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", body["capture_id"])
    assert re.fullmatch(
        r"captures/wb-cam-01/\d{4}/\d{2}/\d{2}/\d{8}T\d{6}Z_" + body["capture_id"] + r"\.jpg",
        body["key"],
    )
    assert body["upload_url"].startswith(
        "https://esp32-cam-whiteborag.s3.ap-south-1.amazonaws.com/" + body["key"] + "?"
    )
    assert body["headers"] == {
        "Content-Type": "image/jpeg",
        "x-amz-meta-device-id": "wb-cam-01",
        "x-amz-meta-trigger": "button",
    }
    assert body["expires_in"] == 300

    log = json.loads(capsys.readouterr().out.strip())
    assert log == {
        "capture_id": body["capture_id"],
        "device_id": "wb-cam-01",
        "trigger": "button",
        "key": body["key"],
    }


def test_key_date_matches_ulid_time():
    _, body = call(ev({"device_id": "wb-cam-01", "trigger": "ir"}))
    # Both the key timestamp and the ULID come from the same clock reading,
    # so the key's date path must match its filename timestamp.
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/(\d{8})T", body["key"])
    assert m.group(1) + m.group(2) + m.group(3) == m.group(4)


def test_bad_body_is_400():
    status, body = call(ev({"device_id": "BAD", "trigger": "button"}))
    assert status == 400
    assert "device_id" in body["error"]


def test_null_body_is_400():
    event = ev({})
    event["body"] = None
    assert call(event)[0] == 400


def test_wrong_device_is_403():
    status, body = call(ev({"device_id": "wb-cam-02", "trigger": "button"}))
    assert status == 403
    assert body == {"error": "API key not authorized for device"}


def test_missing_key_id_is_403():
    event = ev({"device_id": "wb-cam-01", "trigger": "button"})
    del event["requestContext"]
    assert call(event)[0] == 403


def test_url_ttl_env(monkeypatch):
    monkeypatch.setenv("URL_TTL", "120")
    _, body = call(ev({"device_id": "wb-cam-01", "trigger": "serial"}))
    assert body["expires_in"] == 120
    assert "X-Amz-Expires=120" in body["upload_url"]
