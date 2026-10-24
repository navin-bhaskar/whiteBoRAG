"""Offline settings from offline/config.toml (git-ignored), falling back to config.example.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from whiteborag_offline import OFFLINE_DIR

DEFAULT_CONFIG = OFFLINE_DIR / "config.toml"
EXAMPLE_CONFIG = OFFLINE_DIR / "config.example.toml"
TRANSCRIBE_MODES = ("raw", "hybrid-text", "hybrid-vision")


@dataclass(frozen=True)
class Models:
    check: str
    transcribe: str
    transcribe_mode: str  # "raw" | "hybrid-text" | "hybrid-vision"
    ocr: str | None       # the OCR model that feeds a hybrid transcribe
    ocr_prompt: str | None
    text: str
    embed: str


@dataclass(frozen=True)
class Config:
    llm_base_url: str
    models: Models
    data_dir: Path
    host: str
    port: int
    devices: dict[str, str]  # device key -> device id
    max_tokens: int


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    with open(path if path.exists() else EXAMPLE_CONFIG, "rb") as f:
        raw = tomllib.load(f)
    m = raw["models"]
    if m["transcribe_mode"] not in TRANSCRIBE_MODES:
        raise ValueError(f"transcribe_mode must be one of {TRANSCRIBE_MODES}")
    models = Models(
        check=m["check"],
        transcribe=m["transcribe"],
        transcribe_mode=m["transcribe_mode"],
        ocr=m.get("ocr") or None,
        ocr_prompt=m.get("ocr_prompt") or None,
        text=m["text"],
        embed=m["embed"],
    )
    return Config(
        llm_base_url=raw["llm_base_url"],
        models=models,
        data_dir=(OFFLINE_DIR / raw["data_dir"]).resolve(),
        host=raw["host"],
        port=raw["port"],
        devices=dict(raw["devices"]),
        max_tokens=raw["max_tokens"],
    )
