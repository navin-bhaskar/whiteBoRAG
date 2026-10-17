"""S3 Vectors records (spec §4.8): one vector per board section, keyed `<capture_id>#<n>`."""

from ingest.board import Section
from ingest.events import Capture

NO_PROJECT = "none"


def label(display_name: str | None, title: str, descriptive_name: str | None) -> str:
    return display_name or f"no project: {descriptive_name or title}"


def embed_text(label: str, section: Section) -> str:
    return f"{label} — {section.kind} — {section.text}"


def vector_keys(capture_id: str, n: int) -> list[str]:
    return [f"{capture_id}#{i}" for i in range(n)]


def build_records(
    capture: Capture, project_key: str | None, sections: list[Section], embeddings: list[list[float]]
) -> list[dict]:
    """The `vectors` argument of s3vectors.put_vectors, one record per section."""
    keys = vector_keys(capture.capture_id, len(sections))
    return [
        {
            "key": key,
            "data": {"float32": embedding},
            "metadata": {
                # Filterable: the query side narrows by these.
                "project": project_key or NO_PROJECT,
                "date": capture.date,
                "section": section.kind,
                "device": capture.device,
                # Non-filterable (declared on the index): returned with results, never filtered on.
                "capture_id": capture.capture_id,
                "s3_key": capture.s3_key,
                "text": section.text,
            },
        }
        for key, section, embedding in zip(keys, sections, embeddings, strict=True)
    ]


def stale_keys(old: list[str], new: list[str]) -> list[str]:
    """Keys a previous ingest wrote that this one won't overwrite, so they must be deleted."""
    keep = set(new)
    return [key for key in old if key not in keep]
