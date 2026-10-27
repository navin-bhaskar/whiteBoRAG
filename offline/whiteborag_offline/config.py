"""Settings from a config.toml (git-ignored), falling back to its config.example.toml. offline/ by default;
openrouter/ passes its own files."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from whiteborag_offline import OFFLINE_DIR

DEFAULT_CONFIG = OFFLINE_DIR / "config.toml"
EXAMPLE_CONFIG = OFFLINE_DIR / "config.example.toml"
TRANSCRIBE_MODES = ("raw", "hybrid-text", "hybrid-vision")
PROJECT_PICKS = ("title", "model")  # title: match the title against stored projects; model: keep the model's pick


@dataclass(frozen=True)
class Models:
    check: str
    transcribe: str
    transcribe_mode: str  # "raw" | "hybrid-text" | "hybrid-vision"
    ocr: str | None       # the OCR model that feeds a hybrid transcribe
    ocr_prompt: str | None
    text: str
    embed: str
    project_pick: str = "title"


@dataclass(frozen=True)
class Config:
    llm_base_url: str
    models: Models
    data_dir: Path
    host: str
    port: int
    devices: dict[str, str]  # device key -> device id
    max_tokens: int
    api_key_env: str | None = None  # the environment variable (or .env entry) holding the API key


def load_config(path: Path = DEFAULT_CONFIG, example: Path = EXAMPLE_CONFIG) -> Config:
    """data_dir is relative to the directory of the file actually loaded."""
    chosen = path if path.exists() else example
    with open(chosen, "rb") as f:
        raw = tomllib.load(f)
    m = raw["models"]
    if m["transcribe_mode"] not in TRANSCRIBE_MODES:
        raise ValueError(f"transcribe_mode must be one of {TRANSCRIBE_MODES}")
    if m.get("project_pick", "title") not in PROJECT_PICKS:
        raise ValueError(f"project_pick must be one of {PROJECT_PICKS}")
    models = Models(
        check=m["check"],
        transcribe=m["transcribe"],
        transcribe_mode=m["transcribe_mode"],
        ocr=m.get("ocr") or None,
        ocr_prompt=m.get("ocr_prompt") or None,
        text=m["text"],
        embed=m["embed"],
        project_pick=m.get("project_pick", "title"),
    )
    return Config(
        llm_base_url=raw["llm_base_url"],
        models=models,
        data_dir=(chosen.parent / raw["data_dir"]).resolve(),
        host=raw["host"],
        port=raw["port"],
        devices=dict(raw["devices"]),
        max_tokens=raw["max_tokens"],
        api_key_env=raw.get("api_key_env") or None,
    )
