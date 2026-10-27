"""A real offline runtime (SQLite, files, Qdrant in memory) in a temp dir, with a fake model server."""

import dataclasses
from pathlib import Path

from fakes import FakeLlm
from whiteborag_offline import OFFLINE_DIR, REPO_DIR
from whiteborag_offline.config import Config, Models, load_config
from whiteborag_offline.deps import Runtime, open_runtime

FIXTURES = REPO_DIR / "aws" / "backend" / "ingest" / "tests" / "fixtures"
ARCH = (FIXTURES / "architecture.md").read_text(encoding="utf-8")
# The first board of a project names it as `Name: rest`; the local reader picks projects from titles only.
NORMALIZED = "Project: whiteBORAG\n---\n" + ARCH.replace("White BORAH ", "whiteBORAG: ").replace("transform", "terraform")
KEY = "captures/cam-01/2026/10/15/20261015T084632Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg"
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"

MODELS = Models(check="vlm-check", transcribe="vlm", transcribe_mode="raw", ocr=None, ocr_prompt=None,
                text="llama", embed="emb")


def board_replies(check: str = "USABLE", transcript: str = ARCH, normalized: str = NORMALIZED):
    """Answer each model the way a working server would for the architecture board."""
    def reply(call: dict):
        if call["model"] == MODELS.check:
            return check
        if call["model"] == MODELS.transcribe:
            return transcript
        return normalized
    return reply


def config(tmp_path: Path, **models) -> Config:
    cfg = load_config(OFFLINE_DIR / "config.example.toml")
    return dataclasses.replace(cfg, data_dir=tmp_path, models=dataclasses.replace(MODELS, **models))


def runtime(tmp_path: Path, llm: FakeLlm | None = None, **models) -> Runtime:
    return open_runtime(config(tmp_path, **models), client=llm or FakeLlm(board_replies()), vectors_path=":memory:")
