"""Qdrant in embedded local mode, standing in for S3 Vectors on both the ingest and the query side.

Records and results keep the S3 Vectors shapes, so the shared code reads them unchanged.
"""

import threading
import uuid
from pathlib import Path

from qdrant_client import QdrantClient, models

from whiteborag_offline.store import _locked


def _point_id(key: str) -> str:
    """Qdrant ids must be UUIDs or integers; the vector key itself rides in the payload."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _condition(clause: dict) -> models.FieldCondition:
    if len(clause) != 1:
        raise ValueError(f"unsupported filter clause: {clause!r}")
    ((field, test),) = clause.items()
    if not isinstance(test, dict) or list(test) != ["$eq"]:
        raise ValueError(f"unsupported filter clause: {clause!r}")
    return models.FieldCondition(key=field, match=models.MatchValue(value=test["$eq"]))


def to_qdrant_filter(f: dict | None) -> models.Filter | None:
    """The two shapes evidence._search_filter builds: {"field": {"$eq": v}} and {"$and": [those]}."""
    if f is None:
        return None
    if list(f) == ["$and"]:
        return models.Filter(must=[_condition(c) for c in f["$and"]])
    if any(k.startswith("$") for k in f):
        raise ValueError(f"unsupported filter: {f!r}")
    return models.Filter(must=[_condition(f)])


class QdrantVectors:
    """One embedded client shared by the ingest worker and request threads; local mode isn't thread-safe,
    so every call holds a lock."""

    def __init__(self, path: Path | str, collection: str = "boards") -> None:
        self.client = (QdrantClient(location=":memory:", force_disable_check_same_thread=True) if str(path) == ":memory:"
                       else QdrantClient(path=str(path), force_disable_check_same_thread=True))
        self.collection = collection
        self.lock = threading.Lock()

    def close(self) -> None:
        self.client.close()

    def _exists(self) -> bool:
        return self.client.collection_exists(self.collection)

    @_locked
    def put(self, records: list[dict]) -> None:
        if not records:
            return
        if not self._exists():
            size = len(records[0]["data"]["float32"])
            self.client.create_collection(
                self.collection, vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE))
        self.client.upsert(self.collection, points=[
            models.PointStruct(id=_point_id(r["key"]), vector=r["data"]["float32"],
                               payload={**r["metadata"], "key": r["key"]})
            for r in records
        ])

    @_locked
    def delete(self, keys: list[str]) -> None:
        if keys and self._exists():
            self.client.delete(self.collection, points_selector=models.PointIdsList(points=[_point_id(k) for k in keys]))

    @_locked
    def get(self, keys: list[str]) -> list[dict]:
        if not keys or not self._exists():
            return []
        points = self.client.retrieve(self.collection, ids=[_point_id(k) for k in keys],
                                      with_payload=True, with_vectors=True)
        out = []
        for p in points:
            meta = dict(p.payload)
            key = meta.pop("key")
            out.append({"key": key, "data": {"float32": list(p.vector)}, "metadata": meta})
        return out

    @_locked
    def query(self, vector: list[float], top_k: int, filter: dict | None) -> list[dict]:
        if not self._exists():
            return []
        hits = self.client.query_points(self.collection, query=vector, limit=top_k,
                                        query_filter=to_qdrant_filter(filter), with_payload=True).points
        out = []
        for h in hits:
            meta = dict(h.payload)
            key = meta.pop("key")
            out.append({"key": key, "distance": 1.0 - h.score, "metadata": meta})  # S3 Vectors: cosine distance
        return out
