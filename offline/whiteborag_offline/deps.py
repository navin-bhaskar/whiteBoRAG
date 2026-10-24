"""Wiring: the offline counterpart of ingest/aws.py and query/aws.py."""

from dataclasses import dataclass
from pathlib import Path

from ingest.pipeline import Deps as IngestDeps
from query.handler import Deps as QueryDeps

from whiteborag_offline.blobs import FileBlobs
from whiteborag_offline.config import Config
from whiteborag_offline.llm import LlmClient
from whiteborag_offline.models import LocalEmbedder, LocalReader, LocalText
from whiteborag_offline.store import SqliteStore
from whiteborag_offline.vectors import QdrantVectors

DB_NAME = "whiteborag.db"
QUERY_KEY_ID = "offline"  # the handler checks API Gateway's key id; the local server always passes this one


@dataclass
class Runtime:
    """Opened once per process: Qdrant local mode allows one client per directory, shared by ingest and query."""

    cfg: Config
    store: SqliteStore
    blobs: FileBlobs
    vectors: QdrantVectors
    client: LlmClient

    @property
    def db_path(self) -> Path | str:
        return self.cfg.data_dir / DB_NAME


def open_runtime(cfg: Config, client: LlmClient | None = None, vectors_path: Path | str | None = None) -> Runtime:
    for sub in ("uploads", "rejected", "derived"):
        (cfg.data_dir / sub).mkdir(parents=True, exist_ok=True)
    return Runtime(
        cfg=cfg,
        store=SqliteStore(cfg.data_dir / DB_NAME),
        blobs=FileBlobs(cfg.data_dir),
        vectors=QdrantVectors(vectors_path or cfg.data_dir / "vectors"),
        client=client or LlmClient(cfg.llm_base_url),
    )


def query_deps(rt: Runtime, base_url: str) -> QueryDeps:
    """Photo links point back at this server instead of presigned S3 URLs."""
    base = base_url.rstrip("/")
    return QueryDeps(
        store=rt.store,
        blobs=rt.blobs,
        llm=LocalText(rt.client, rt.cfg.models.text),
        embedder=LocalEmbedder(rt.client, rt.cfg.models.embed),
        search=rt.vectors,
        sign=lambda key: f"{base}/photos/{key}",
        query_key_id=QUERY_KEY_ID,
        origin="*",
    )


def ingest_deps(rt: Runtime) -> IngestDeps:
    return IngestDeps(
        store=rt.store,
        blobs=rt.blobs,
        reader=LocalReader(rt.client, rt.cfg.models, rt.cfg.max_tokens),
        embedder=LocalEmbedder(rt.client, rt.cfg.models.embed),
        vectors=rt.vectors,
    )
