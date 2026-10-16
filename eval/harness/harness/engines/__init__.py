"""OCR engines: a common result type, the engine protocol, and construction by ID."""

import hashlib
from dataclasses import dataclass
from typing import Protocol

import boto3

from harness.config import Config


@dataclass
class EngineResult:
    text: str
    raw: dict
    usage: dict
    cost_usd: float
    latency_s: float


class Engine(Protocol):
    id: str
    structured: bool

    def worst_case_cost(self) -> float: ...

    def run(self, image: bytes) -> EngineResult: ...


MODEL_IDS = ["nova-lite", "nova-pro", "nova-2-lite"]
ALL_ENGINES = ["textract", "textract-layout", "rekognition"] + [
    f"{kind}:{m}" for kind in ("bedrock", "hybrid") for m in MODEL_IDS
]


def engine_dir(engine_id: str) -> str:
    return engine_id.replace(":", "_")


def prompt_text(cfg: Config) -> str:
    return cfg.prompt_path.read_text(encoding="utf-8")


def prompt_hash(cfg: Config) -> str:
    return hashlib.sha256(prompt_text(cfg).encode("utf-8")).hexdigest()[:12]


def build_engines(ids: list[str], cfg: Config, session: boto3.Session) -> list[Engine]:
    from harness.engines import bedrock, hybrid, rekognition, textract

    expanded = ALL_ENGINES if "all" in ids else ids
    engines: list[Engine] = []
    for engine_id in expanded:
        kind, _, model_id = engine_id.partition(":")
        if engine_id == "textract":
            engines.append(textract.Textract(cfg, session))
        elif engine_id == "textract-layout":
            engines.append(textract.TextractLayout(cfg, session))
        elif engine_id == "rekognition":
            engines.append(rekognition.Rekognition(cfg, session))
        elif kind in ("bedrock", "hybrid") and model_id in cfg.models:
            cls = bedrock.Bedrock if kind == "bedrock" else hybrid.Hybrid
            engines.append(cls(cfg, session, cfg.models[model_id]))
        else:
            raise ValueError(f"unknown engine: {engine_id}")
    return engines
