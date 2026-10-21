"""The real implementations of the handler's interfaces: Nova 2 Lite, S3 Vectors search and S3 signing.

The store, transcripts and embedder are ingest's own, so both Lambdas read the data the same way.
"""

import os
from collections.abc import Callable

import boto3
from botocore.config import Config

from ingest.aws import DynamoStore, S3Blobs, TitanEmbedder
from ingest.pipeline import Reply
from query.handler import Deps

# Two model calls must fit in the 28 s Lambda timeout, so each gives up quickly.
BEDROCK_CONFIG = Config(read_timeout=10, retries={"max_attempts": 2})
SIGNED_URL_SECONDS = 900


class NovaText:
    """A text-only Converse call. Counts tokens so the handler can log them per request."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.client = boto3.client("bedrock-runtime", config=BEDROCK_CONFIG)
        self.usage = {"input": 0, "output": 0}

    def ask(self, prompt: str, max_tokens: int) -> Reply:
        resp = self.client.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
        )
        usage = resp.get("usage", {})
        self.usage["input"] += usage.get("inputTokens", 0)
        self.usage["output"] += usage.get("outputTokens", 0)
        try:
            text = resp["output"]["message"]["content"][0]["text"]
        except (KeyError, IndexError):
            text = None
        return Reply(text, resp.get("stopReason") == "max_tokens")

    def tokens(self) -> dict:
        """Tokens used since the last call to tokens(): one request's worth."""
        used, self.usage = self.usage, {"input": 0, "output": 0}
        return used


class S3VectorSearch:
    def __init__(self, bucket: str, index: str) -> None:
        self.where = {"vectorBucketName": bucket, "indexName": index}
        self.client = boto3.client("s3vectors")

    def query(self, vector: list[float], top_k: int, filter: dict | None) -> list[dict]:
        args = {"topK": top_k, "queryVector": {"float32": vector}, "returnMetadata": True, "returnDistance": True}
        if filter is not None:
            args["filter"] = filter
        return self.client.query_vectors(**self.where, **args)["vectors"]


def signer(bucket: str) -> Callable[[str], str]:
    """Signs a 15-minute GET URL with the Lambda role's credentials; no network call."""
    s3 = boto3.client("s3")
    return lambda key: s3.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=SIGNED_URL_SECONDS
    )


def build_deps() -> Deps:
    env = os.environ
    return Deps(
        store=DynamoStore(env["TABLE"]),
        blobs=S3Blobs(env["BUCKET"]),
        llm=NovaText(env["NOVA_MODEL"]),
        embedder=TitanEmbedder(env["EMBED_MODEL"]),
        search=S3VectorSearch(env["VECTOR_BUCKET"], env["VECTOR_INDEX"]),
        sign=signer(env["BUCKET"]),
        query_key_id=env["QUERY_KEY_ID"],
        origin=env.get("ALLOWED_ORIGIN", "http://localhost:8000"),
    )
