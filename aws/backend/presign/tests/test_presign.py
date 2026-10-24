from urllib.parse import parse_qs, urlsplit

import pytest

from handler import make_s3_client, presign

BUCKET = "esp32-cam-whiteborag"
KEY = "captures/wb-cam-01/2026/10/08/20261008T133454Z_01JA2B3C4D5E6F7G8H9J0K1M2N.jpg"


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "token")
    return make_s3_client("ap-south-1")


def test_presign(s3):
    url, headers = presign(s3, BUCKET, KEY, "wb-cam-01", "button", 300)
    parts = urlsplit(url)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}

    assert parts.scheme == "https"
    assert parts.netloc == f"{BUCKET}.s3.ap-south-1.amazonaws.com"
    assert parts.path == "/" + KEY
    assert query["X-Amz-Algorithm"] == "AWS4-HMAC-SHA256"
    assert query["X-Amz-Expires"] == "300"
    assert query["X-Amz-SignedHeaders"].split(";") == [
        "content-type",
        "host",
        "x-amz-meta-device-id",
        "x-amz-meta-trigger",
    ]
    assert "X-Amz-Security-Token" in query
    assert headers == {
        "Content-Type": "image/jpeg",
        "x-amz-meta-device-id": "wb-cam-01",
        "x-amz-meta-trigger": "button",
    }


def test_presign_ttl(s3):
    url, _ = presign(s3, BUCKET, KEY, "wb-cam-01", "ir", 60)
    assert parse_qs(urlsplit(url).query)["X-Amz-Expires"] == ["60"]
