import base64
import json

import pytest

from handler import ValidationError, parse_request


def event(body, b64=False):
    if not isinstance(body, str) and body is not None:
        body = json.dumps(body)
    if b64 and body is not None:
        body = base64.b64encode(body.encode()).decode()
    return {"body": body, "isBase64Encoded": b64}


def test_valid_request():
    assert parse_request(event({"device_id": "wb-cam-01", "trigger": "button"})) == (
        "wb-cam-01",
        "button",
    )


@pytest.mark.parametrize("trigger", ["button", "ir", "serial"])
def test_all_triggers_accepted(trigger):
    assert parse_request(event({"device_id": "a", "trigger": trigger}))[1] == trigger


def test_base64_body():
    ev = event({"device_id": "wb-cam-01", "trigger": "ir"}, b64=True)
    assert parse_request(ev) == ("wb-cam-01", "ir")


def test_max_length_device_id():
    assert parse_request(event({"device_id": "a" * 32, "trigger": "ir"}))[0] == "a" * 32


@pytest.mark.parametrize(
    "body",
    [
        None,
        "",
        "not json",
        "[]",
        '"x"',
        "42",
        {},
        {"device_id": "wb-cam-01"},
        {"trigger": "button"},
        {"device_id": "WB-CAM-01", "trigger": "button"},
        {"device_id": "wb_cam", "trigger": "button"},
        {"device_id": "", "trigger": "button"},
        {"device_id": "a" * 33, "trigger": "button"},
        {"device_id": "wb-cam-01\n", "trigger": "button"},
        {"device_id": 123, "trigger": "button"},
        {"device_id": "wb-cam-01", "trigger": "Button"},
        {"device_id": "wb-cam-01", "trigger": "wave"},
        {"device_id": "wb-cam-01", "trigger": ["button"]},
    ],
)
def test_invalid_requests(body):
    with pytest.raises(ValidationError):
        parse_request(event(body))


def test_invalid_base64_body():
    with pytest.raises(ValidationError):
        parse_request({"body": "%%%not-base64", "isBase64Encoded": True})
