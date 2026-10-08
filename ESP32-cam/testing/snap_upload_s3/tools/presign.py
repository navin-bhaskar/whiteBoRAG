# /// script
# requires-python = ">=3.9"
# dependencies = ["boto3"]
# ///
"""Generate a pre-signed S3 PUT URL for the ESP32-CAM test firmware.

    uv run tools/presign.py esp32-cam-whiteborag esp32cam/test.jpg --expires 3600

Paste the printed URL into the serial monitor. The ContentType signed here must
match UPLOAD_CONTENT_TYPE in config.h (image/jpeg). If --region is omitted the
bucket's region is looked up, since a wrong region invalidates the signature.
"""
import argparse

import boto3
from botocore.config import Config


def bucket_region(bucket):
    loc = boto3.client("s3").get_bucket_location(Bucket=bucket)["LocationConstraint"]
    return loc or "us-east-1"  # S3 reports us-east-1 as null


def main():
    p = argparse.ArgumentParser()
    p.add_argument("bucket")
    p.add_argument("key")
    p.add_argument("--expires", type=int, default=3600, help="seconds (max 604800)")
    p.add_argument("--region", default=None)
    args = p.parse_args()

    region = args.region or bucket_region(args.bucket)
    s3 = boto3.client(
        "s3",
        region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": args.bucket, "Key": args.key, "ContentType": "image/jpeg"},
        ExpiresIn=args.expires,
    )
    print(url)


if __name__ == "__main__":
    main()
