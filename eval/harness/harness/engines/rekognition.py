"""Rekognition DetectText: the baseline, limited to about 100 words per image."""

import time

import boto3

from harness.config import Config
from harness.engines import EngineResult


def lines(resp: dict) -> list[str]:
    return [d["DetectedText"] for d in resp["TextDetections"] if d["Type"] == "LINE"]


class Rekognition:
    id = "rekognition"
    structured = False

    def __init__(self, cfg: Config, session: boto3.Session):
        self.client = session.client("rekognition", region_name=cfg.region)
        self.cost = cfg.rekognition_per_image * cfg.price_margin

    def worst_case_cost(self) -> float:
        return self.cost

    def run(self, image: bytes) -> EngineResult:
        start = time.perf_counter()
        resp = self.client.detect_text(Image={"Bytes": image})
        latency = time.perf_counter() - start
        return EngineResult("\n".join(lines(resp)), resp, {"images": 1}, self.cost, latency)
