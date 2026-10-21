"""Boards seeded through ingest's own pipeline, so the store holds exactly what ingest writes."""

from pathlib import Path

from fakes import FakeBlobs, FakeEmbedder, FakeReader, FakeVectors, InMemoryStore
from ingest.events import Job, parse_key
from ingest.pipeline import Deps, Reply, ingest_capture

FIXTURES = Path(__file__).parents[2] / "ingest" / "tests" / "fixtures"
ARCH = (FIXTURES / "architecture.md").read_text(encoding="utf-8")


def board(title: str = "whiteBORAG architecture", todos: list[str] = (), edges: list[str] = ()) -> str:
    """A board in transcript Markdown: todos like "[x] Ship it", edges like 'A → B, labelled "x"'."""
    md = f"# {title}\n"
    if edges:
        md += "\n## Diagram\n" + "".join(f"- {box}\n" for e in edges for box in e.split(",")[0].split(" → "))
        md += "\nEdges:\n" + "".join(f"- {e}\n" for e in edges)
    if todos:
        md += "\n## TODO\n" + "".join(f"- {t}\n" for t in todos)
    return md


class Seeded:
    def __init__(self) -> None:
        self.store = InMemoryStore()
        self.blobs = FakeBlobs()
        self.vectors = FakeVectors()
        self.ids: list[str] = []

    def add(self, stamp: str, md: str = ARCH, project: str = "whiteBORAG") -> str:
        """Ingest one board captured at stamp ("20261015T084632Z"); returns its capture_id."""
        capture_id = "01M4Z7KFZ5KHCYV4BWHM8R" + f"{len(self.ids):04d}"
        key = f"captures/wb-cam-01/{stamp[:4]}/{stamp[4:6]}/{stamp[6:8]}/{stamp}_{capture_id}.jpg"
        self.blobs.files[key] = b"jpeg"
        reader = FakeReader(Reply(md, False), Reply(f"Project: {project}\n---\n{md}", False))
        deps = Deps(self.store, self.blobs, reader, FakeEmbedder(), self.vectors)
        out = ingest_capture(deps, Job(parse_key(key), False), lambda: "2026-10-20T10:00:00Z")
        assert out.status == "ingested", out
        self.ids.append(capture_id)
        return capture_id
