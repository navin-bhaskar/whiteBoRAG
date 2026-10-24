"""Textract lines passed to a Nova model as hints alongside the image."""

import time

import boto3

from harness.config import Config, ModelConfig
from harness.engines import EngineError, EngineResult, prompt_text, textract
from harness.engines.bedrock import Converser, converse_text, strip_fences

HINT_INTRO = "These are OCR lines from the same image. Use them as hints; the image is authoritative:"


def hint_prompt(base: str, lines: list[str]) -> str:
    return base + "\n\n" + HINT_INTRO + "\n" + "\n".join(lines)


class Hybrid:
    structured = True

    def __init__(self, cfg: Config, session: boto3.Session, model: ModelConfig):
        self.id = f"hybrid:{model.id}"
        self.textract = textract.Textract(cfg, session)
        self.converser = Converser(cfg, session, model)
        self.prompt = prompt_text(cfg)

    def worst_case_cost(self) -> float:
        return self.textract.worst_case_cost() + self.converser.worst_case_cost()

    def run(self, image: bytes) -> EngineResult:
        start = time.perf_counter()
        ocr = self.textract.run(image)
        try:
            resp, usage, cost = self.converser.call(image, hint_prompt(self.prompt, ocr.text.splitlines()))
        except Exception as exc:
            raise EngineError(f"Bedrock failed after Textract: {exc!r}", ocr.cost_usd) from exc
        latency = time.perf_counter() - start
        try:
            text = converse_text(resp)
        except (KeyError, IndexError) as exc:
            raise EngineError(f"no text in response (stopReason={resp.get('stopReason')})",
                              ocr.cost_usd + cost) from exc
        return EngineResult(
            strip_fences(text),
            {"textract": ocr.raw, "bedrock": resp},
            {**usage, "pages": 1},
            ocr.cost_usd + cost,
            latency,
        )
