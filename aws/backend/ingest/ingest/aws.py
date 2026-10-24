"""The real implementations of the pipeline's interfaces: DynamoDB, S3, Bedrock and S3 Vectors."""

import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.config import Config
from botocore.exceptions import ClientError

from ingest import PROMPTS_DIR
from ingest.check import PROMPT_VERSION as CHECK_VERSION
from ingest.normalize import strip_fence
from ingest.pipeline import TRANSCRIBE_VERSION, Deps, Reply
from ingest.store import CaptureRecord, Conflict, Link, Project
from ingest.todos import Sighting, TodoItem

MAX_TOKENS = 1500
BEDROCK_CONFIG = Config(retries={"mode": "adaptive", "max_attempts": 4}, read_timeout=60)
EMBED_DIMENSIONS = 1024


def _plain(value):
    """DynamoDB returns numbers as Decimal; turn them back into ints (the table stores no floats)."""
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


class DynamoStore:
    """The single-table layout of spec §5, with conditional writes on `version`."""

    def __init__(self, table_name: str) -> None:
        self.table = boto3.resource("dynamodb").Table(table_name)

    # Helpers

    def _put(self, item: dict, condition: str | None = None, values: dict | None = None) -> None:
        kwargs = {"Item": item}
        if condition:
            kwargs["ConditionExpression"] = condition
        if values:
            kwargs["ExpressionAttributeValues"] = values
        self._conditional(self.table.put_item, **kwargs)

    def _delete(self, pk: str, sk: str, version: int | None = None) -> None:
        kwargs = {"Key": {"pk": pk, "sk": sk}}
        if version is not None:
            kwargs["ConditionExpression"] = "attribute_not_exists(pk) OR version = :v"
            kwargs["ExpressionAttributeValues"] = {":v": version}
        self._conditional(self.table.delete_item, **kwargs)

    @staticmethod
    def _conditional(call, **kwargs) -> None:
        try:
            call(**kwargs)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise Conflict(str(exc)) from exc
            raise

    def _query(self, pk: str, sk_prefix: str) -> list[dict]:
        items, kwargs = [], {"KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(sk_prefix)}
        while True:
            page = self.table.query(**kwargs)
            items += [_plain(i) for i in page["Items"]]
            if "LastEvaluatedKey" not in page:
                return items
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def _get(self, pk: str) -> dict | None:
        item = self.table.get_item(Key={"pk": pk, "sk": "META"}).get("Item")
        return _plain(item) if item else None

    # Projects: PROJECT#<key> / META

    @staticmethod
    def _project(item: dict) -> Project:
        return Project(
            key=item["pk"].removeprefix("PROJECT#"),
            display_name=item["display_name"],
            aliases=item.get("aliases", {}),
            pinned_name=item.get("pinned_name"),
            created_at=item.get("created_at", ""),
            version=item["version"],
        )

    @staticmethod
    def _project_item(p: Project, version: int) -> dict:
        item = {"pk": f"PROJECT#{p.key}", "sk": "META", "display_name": p.display_name, "aliases": p.aliases,
                "created_at": p.created_at, "version": version}
        if p.pinned_name is not None:
            item["pinned_name"] = p.pinned_name
        return item

    def list_projects(self) -> list[Project]:
        items, kwargs = [], {"FilterExpression": Attr("sk").eq("META") & Attr("pk").begins_with("PROJECT#")}
        while True:
            page = self.table.scan(**kwargs)
            items += [self._project(_plain(i)) for i in page["Items"]]
            if "LastEvaluatedKey" not in page:
                return items
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def get_project(self, key: str) -> Project | None:
        item = self._get(f"PROJECT#{key}")
        return self._project(item) if item else None

    def create_project(self, p: Project) -> None:
        self._put(self._project_item(p, p.version), "attribute_not_exists(pk)")

    def save_project(self, p: Project) -> None:
        self._put(self._project_item(p, p.version + 1), "version = :v", {":v": p.version})

    def delete_project(self, key: str, version: int) -> None:
        self._delete(f"PROJECT#{key}", "META", version)

    # Links: PROJECT#<key> / CAPTURE#<captured_at>#<capture_id>

    def project_links(self, key: str) -> list[Link]:
        return [
            Link(key, i["captured_at"], i["capture_id"], i["date"], i["title_as_seen"], i["project_name_as_seen"])
            for i in self._query(f"PROJECT#{key}", "CAPTURE#")
        ]

    def put_link(self, link: Link) -> None:
        self._put({
            "pk": f"PROJECT#{link.project_key}", "sk": f"CAPTURE#{link.captured_at}#{link.capture_id}",
            "captured_at": link.captured_at, "capture_id": link.capture_id, "date": link.date,
            "title_as_seen": link.title_as_seen, "project_name_as_seen": link.project_name_as_seen,
        })

    def delete_link(self, link: Link) -> None:
        self._delete(f"PROJECT#{link.project_key}", f"CAPTURE#{link.captured_at}#{link.capture_id}")

    # Todos: PROJECT#<key> / TODO#<todo_id>

    def list_todos(self, project_key: str) -> list[TodoItem]:
        return [
            TodoItem(
                todo_id=i["sk"].removeprefix("TODO#"),
                sightings={cid: Sighting(cid, s["date"], s["captured_at"], s["checked"], s["text_as_seen"])
                           for cid, s in i["sightings"].items()},
                version=i["version"],
                text=i["text"],
                first_seen=i["first_seen"],
                state=i["state"],
                completed_on=i.get("completed_on"),
            )
            for i in self._query(f"PROJECT#{project_key}", "TODO#")
        ]

    def save_todo(self, project_key: str, item: TodoItem) -> None:
        record = {
            "pk": f"PROJECT#{project_key}", "sk": f"TODO#{item.todo_id}",
            "text": item.text, "first_seen": item.first_seen, "state": item.state,
            "completed_on": item.completed_on, "version": item.version + 1,
            "sightings": {cid: {"date": s.date, "captured_at": s.captured_at, "checked": s.checked,
                                "text_as_seen": s.text_as_seen} for cid, s in item.sightings.items()},
        }
        if item.version == 0:
            self._put(record, "attribute_not_exists(pk)")
        else:
            self._put(record, "version = :v", {":v": item.version})

    def delete_todo(self, project_key: str, todo_id: str, version: int) -> None:
        self._delete(f"PROJECT#{project_key}", f"TODO#{todo_id}", version)

    # Captures: CAPTURE#<capture_id> / META

    def get_capture(self, capture_id: str) -> CaptureRecord | None:
        item = self._get(f"CAPTURE#{capture_id}")
        if item is None:
            return None
        fields = {k: v for k, v in item.items() if k not in ("pk", "sk")}
        return CaptureRecord(**fields)

    def put_capture(self, rec: CaptureRecord) -> None:
        self._put({"pk": f"CAPTURE#{rec.capture_id}", "sk": "META", **vars(rec)})

    def delete_capture(self, capture_id: str) -> None:
        self._delete(f"CAPTURE#{capture_id}", "META")


class S3Blobs:
    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self.s3 = boto3.client("s3")

    def get_bytes(self, key: str) -> bytes | None:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            # NoSuchKey needs s3:ListBucket; without it a missing key looks like AccessDenied.
            if exc.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    def get_text(self, key: str) -> str | None:
        data = self.get_bytes(key)
        return data.decode("utf-8") if data is not None else None

    def put_text(self, key: str, text: str) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=text.encode("utf-8"),
                           ContentType="text/markdown; charset=utf-8")

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=key)


class BedrockReader:
    """Nova via Converse, with the same request shape as the eval harness Converser.

    Nova 2 Lite reads the board; the photo check needs Nova Pro, the only Nova model that spotted
    a finger over the board in testing (2026-10-19).
    """

    def __init__(self, model_id: str, check_model_id: str) -> None:
        self.model_id = model_id
        self.check_model_id = check_model_id
        self.client = boto3.client("bedrock-runtime", config=BEDROCK_CONFIG)
        self.transcribe_prompt = (PROMPTS_DIR / f"{TRANSCRIBE_VERSION}.md").read_text(encoding="utf-8")
        self.check_prompt = (PROMPTS_DIR / f"{CHECK_VERSION}.md").read_text(encoding="utf-8")

    def _converse(self, content: list[dict], model_id: str | None = None) -> Reply:
        resp = self.client.converse(
            modelId=model_id or self.model_id,
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0},
        )
        try:
            text = strip_fence(resp["output"]["message"]["content"][0]["text"])
        except (KeyError, IndexError):
            text = None
        return Reply(text, resp.get("stopReason") == "max_tokens")

    def check(self, image: bytes) -> Reply:
        return self._converse([{"image": {"format": "jpeg", "source": {"bytes": image}}},
                               {"text": self.check_prompt}], self.check_model_id)

    def transcribe(self, image: bytes) -> Reply:
        return self._converse([{"image": {"format": "jpeg", "source": {"bytes": image}}},
                               {"text": self.transcribe_prompt}])

    def normalize(self, prompt: str) -> Reply:
        return self._converse([{"text": prompt}])


class TitanEmbedder:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.client = boto3.client("bedrock-runtime", config=BEDROCK_CONFIG)

    def embed(self, text: str) -> list[float]:
        resp = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps({"inputText": text, "dimensions": EMBED_DIMENSIONS, "normalize": True}),
        )
        return json.loads(resp["body"].read())["embedding"]


class S3VectorIndex:
    def __init__(self, bucket: str, index: str) -> None:
        self.where = {"vectorBucketName": bucket, "indexName": index}
        self.client = boto3.client("s3vectors")

    def put(self, records: list[dict]) -> None:
        self.client.put_vectors(**self.where, vectors=records)

    def delete(self, keys: list[str]) -> None:
        if keys:
            self.client.delete_vectors(**self.where, keys=keys)

    def get(self, keys: list[str]) -> list[dict]:
        return self.client.get_vectors(**self.where, keys=keys, returnData=True, returnMetadata=True)["vectors"]


def build_deps() -> Deps:
    env = os.environ
    return Deps(
        store=DynamoStore(env["TABLE"]),
        blobs=S3Blobs(env["BUCKET"]),
        reader=BedrockReader(env["NOVA_MODEL"], env["CHECK_MODEL"]),
        embedder=TitanEmbedder(env["EMBED_MODEL"]),
        vectors=S3VectorIndex(env["VECTOR_BUCKET"], env["VECTOR_INDEX"]),
    )
