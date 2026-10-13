"""End-to-end check of the deployed capture API (spec §6).

Usage (from repo root):
    uv run --project backend/presign python infra/scripts/smoke.py

Uploads one tiny object under captures/<device>/..., verifies it, then
permanently deletes that object version so the archive stays clean.
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request

import boto3

BUCKET = "esp32-cam-whiteborag"
JPEG = b"\xff\xd8\xff\xd9"  # smallest valid JPEG markers (SOI + EOI)


def tf_outputs():
    out = subprocess.run(
        ["terraform", "-chdir=infra", "output", "-json"],
        check=True, capture_output=True, text=True,
    ).stdout
    data = json.loads(out)
    return data["api_base_url"]["value"], data["api_keys"]["value"]


def request(method, url, body=None, headers=None):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def post_captures(base, payload, key=None):
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["x-api-key"] = key
    return request("POST", f"{base}/captures", json.dumps(payload).encode(), headers)


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not cond else ""))
    return cond


def main():
    base, keys = tf_outputs()
    device, key = next(iter(keys.items()))
    ok = True

    status, body = post_captures(base, {"device_id": device, "trigger": "serial"})
    ok &= check("no API key -> 403", status == 403, f"{status} {body!r}")

    status, body = post_captures(base, {"device_id": "wb-cam-zz", "trigger": "serial"}, key)
    ok &= check("key for another device -> 403", status == 403, f"{status} {body!r}")

    status, body = post_captures(base, {"device_id": device, "trigger": "wave"}, key)
    ok &= check("invalid trigger -> 400", status == 400, f"{status} {body!r}")

    status, body = post_captures(base, {"device_id": device, "trigger": "serial"}, key)
    if not check("valid request -> 200", status == 200, f"{status} {body!r}"):
        sys.exit(1)
    resp = json.loads(body)

    status, body = request("PUT", resp["upload_url"], JPEG, resp["headers"])
    ok &= check("PUT with returned headers -> 200", status == 200, f"{status} {body[:300]!r}")

    s3 = boto3.client("s3", region_name="ap-south-1")
    head = s3.head_object(Bucket=BUCKET, Key=resp["key"])
    ok &= check(
        "object metadata matches",
        head["Metadata"] == {"device-id": device, "trigger": "serial"}
        and head["ContentType"] == "image/jpeg",
        f"{head['Metadata']} {head['ContentType']}",
    )

    # The bucket is unversioned today; if versioning is ever enabled, delete
    # the specific version so no delete marker or old version is left behind.
    version = {"VersionId": head["VersionId"]} if "VersionId" in head else {}
    s3.delete_object(Bucket=BUCKET, Key=resp["key"], **version)
    print(f"cleaned up {resp['key']}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
