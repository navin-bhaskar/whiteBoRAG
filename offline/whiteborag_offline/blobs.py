"""Blobs on disk. Photos (`captures/…`) live in uploads/, everything else the pipeline writes in derived/.

Deleting a photo moves it to rejected/ instead: the shared pipeline deletes photos the check model calls
unusable, and offline the user wants to see what it threw out.
"""

import shutil
from pathlib import Path, PurePosixPath

from ingest.events import CAPTURE_PREFIX


class FileBlobs:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def _split(self, key: str) -> tuple[str, PurePosixPath]:
        # Plain relative segments only: an empty one ("//"), a drive ("C:") or a backslash would let the
        # joined path escape data_dir on Windows.
        parts = key.split("/")
        if "\\" in key or any(p in ("", ".", "..") or ":" in p for p in parts):
            raise ValueError(f"bad blob key: {key!r}")
        if key.startswith(CAPTURE_PREFIX):
            return "uploads", PurePosixPath(key.removeprefix(CAPTURE_PREFIX))
        return "derived", PurePosixPath(key)

    def path_for(self, key: str) -> Path:
        area, rest = self._split(key)
        base = (self.data_dir / area).resolve()
        path = (base / rest).resolve()
        if not path.is_relative_to(base):
            raise ValueError(f"bad blob key: {key!r}")
        return path

    def get_bytes(self, key: str) -> bytes | None:
        path = self.path_for(key)
        return path.read_bytes() if path.exists() else None

    def get_text(self, key: str) -> str | None:
        path = self.path_for(key)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def put_bytes(self, key: str, data: bytes) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def put_text(self, key: str, text: str) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def delete(self, key: str) -> None:
        area, rest = self._split(key)
        path = self.path_for(key)
        if not path.exists():
            return
        if area == "uploads":
            target = self.data_dir / "rejected" / rest
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(path, target)
        else:
            path.unlink()
