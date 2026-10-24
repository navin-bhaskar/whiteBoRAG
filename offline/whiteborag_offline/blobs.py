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
        path = PurePosixPath(key)
        if "\\" in key or path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError(f"bad blob key: {key!r}")
        if key.startswith(CAPTURE_PREFIX):
            return "uploads", PurePosixPath(key.removeprefix(CAPTURE_PREFIX))
        return "derived", path

    def path_for(self, key: str) -> Path:
        area, rest = self._split(key)
        return self.data_dir / area / rest

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
        path = self.data_dir / area / rest
        if not path.exists():
            return
        if area == "uploads":
            target = self.data_dir / "rejected" / rest
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(path, target)
        else:
            path.unlink()
