"""POST /captures: validate the request and return a presigned S3 PUT URL."""

import base64
import binascii
import json
import re

DEVICE_ID_RE = re.compile(r"[a-z0-9-]{1,32}")
TRIGGERS = frozenset({"button", "ir", "serial"})


class ValidationError(Exception):
    pass


def parse_request(event: dict) -> tuple[str, str]:
    body = event.get("body")
    if not body:
        raise ValidationError("request body is required")
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body, validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            raise ValidationError("body is not valid base64")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise ValidationError("body is not valid JSON")
    if not isinstance(data, dict):
        raise ValidationError("body must be a JSON object")

    device_id = data.get("device_id")
    if not isinstance(device_id, str) or not DEVICE_ID_RE.fullmatch(device_id):
        raise ValidationError("device_id must match ^[a-z0-9-]{1,32}$")
    trigger = data.get("trigger")
    if not isinstance(trigger, str) or trigger not in TRIGGERS:
        raise ValidationError("trigger must be one of: button, ir, serial")
    return device_id, trigger


def authorize(event: dict, device_id: str, device_keys: dict[str, str]) -> bool:
    identity = (event.get("requestContext") or {}).get("identity") or {}
    key_id = identity.get("apiKeyId")
    return key_id is not None and device_keys.get(key_id) == device_id
