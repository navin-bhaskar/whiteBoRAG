"""Harness configuration: region, budget, models and prices from config.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = PACKAGE_DIR / "config.toml"
EVAL_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ModelConfig:
    id: str
    profile: str
    input_per_1k: float
    output_per_1k: float


@dataclass(frozen=True)
class Config:
    region: str
    budget_usd: float
    price_margin: float
    max_tokens: int
    worst_case_input_tokens: int
    prompt_path: Path
    prices_verified_on: str
    textract_detect_per_page: float
    textract_layout_per_page: float
    rekognition_per_image: float
    models: dict[str, ModelConfig]


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    prices = raw["prices"]
    models = {
        model_id: ModelConfig(model_id, m["profile"], m["input_per_1k"], m["output_per_1k"])
        for model_id, m in raw["models"].items()
    }
    return Config(
        region=raw["region"],
        budget_usd=raw["budget_usd"],
        price_margin=raw["price_margin"],
        max_tokens=raw["max_tokens"],
        worst_case_input_tokens=raw["worst_case_input_tokens"],
        prompt_path=PACKAGE_DIR / "prompts" / raw["prompt"],
        prices_verified_on=prices["verified_on"],
        textract_detect_per_page=prices["textract_detect_per_page"],
        textract_layout_per_page=prices["textract_layout_per_page"],
        rekognition_per_image=prices["rekognition_detect_text_per_image"],
        models=models,
    )
