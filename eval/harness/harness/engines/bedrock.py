"""Nova vision models through the Bedrock Converse API."""

import re
import time

import boto3

from harness.config import Config, ModelConfig
from harness.engines import EngineError, EngineResult, prompt_text
from harness.ledger import bedrock_cost

FENCE_RE = re.compile(r"^\s*```[\w-]*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


def strip_fences(text: str) -> str:
    match = FENCE_RE.match(text)
    return (match.group(1) if match else text).strip()


def converse_text(resp: dict) -> str:
    return resp["output"]["message"]["content"][0]["text"]


class Converser:
    """One Converse call with an image and a text prompt, priced from the response usage."""

    def __init__(self, cfg: Config, session: boto3.Session, model: ModelConfig):
        self.client = session.client("bedrock-runtime", region_name=cfg.region)
        self.cfg, self.model = cfg, model

    def worst_case_cost(self) -> float:
        return bedrock_cost(self.model, self.cfg.worst_case_input_tokens, self.cfg.max_tokens,
                            self.cfg.price_margin)

    def call(self, image: bytes, prompt: str) -> tuple[dict, dict, float]:
        resp = self.client.converse(
            modelId=self.model.profile,
            messages=[{"role": "user", "content": [
                {"image": {"format": "jpeg", "source": {"bytes": image}}},
                {"text": prompt},
            ]}],
            inferenceConfig={"maxTokens": self.cfg.max_tokens, "temperature": 0},
        )
        usage = {"input_tokens": resp["usage"]["inputTokens"],
                 "output_tokens": resp["usage"]["outputTokens"]}
        cost = bedrock_cost(self.model, usage["input_tokens"], usage["output_tokens"],
                            self.cfg.price_margin)
        return resp, usage, cost


class Bedrock:
    structured = True

    def __init__(self, cfg: Config, session: boto3.Session, model: ModelConfig):
        self.id = f"bedrock:{model.id}"
        self.converser = Converser(cfg, session, model)
        self.prompt = prompt_text(cfg)

    def worst_case_cost(self) -> float:
        return self.converser.worst_case_cost()

    def run(self, image: bytes) -> EngineResult:
        start = time.perf_counter()
        resp, usage, cost = self.converser.call(image, self.prompt)
        latency = time.perf_counter() - start
        try:
            text = converse_text(resp)
        except (KeyError, IndexError) as exc:
            raise EngineError(f"no text in response (stopReason={resp.get('stopReason')})", cost) from exc
        return EngineResult(strip_fences(text), resp, usage, cost, latency)
