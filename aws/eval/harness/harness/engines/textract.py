"""Textract DetectDocumentText (plain lines) and AnalyzeDocument LAYOUT (grouped lines)."""

import time

import boto3

from harness.config import Config
from harness.engines import EngineResult


def lines(resp: dict) -> list[str]:
    return [b["Text"] for b in resp["Blocks"] if b["BlockType"] == "LINE"]


def layout_text(resp: dict) -> str:
    by_id = {b["Id"]: b for b in resp["Blocks"] if "Id" in b}
    groups = []
    for block in resp["Blocks"]:
        if not block["BlockType"].startswith("LAYOUT_"):
            continue
        child_ids = [i for r in block.get("Relationships", []) if r["Type"] == "CHILD" for i in r["Ids"]]
        texts = [by_id[i]["Text"] for i in child_ids if by_id.get(i, {}).get("BlockType") == "LINE"]
        if texts:
            groups.append("\n".join(texts))
    return "\n\n".join(groups)


class Textract:
    id = "textract"
    structured = False

    def __init__(self, cfg: Config, session: boto3.Session):
        self.client = session.client("textract", region_name=cfg.region)
        self.cost = cfg.textract_detect_per_page * cfg.price_margin

    def worst_case_cost(self) -> float:
        return self.cost

    def run(self, image: bytes) -> EngineResult:
        start = time.perf_counter()
        resp = self.client.detect_document_text(Document={"Bytes": image})
        latency = time.perf_counter() - start
        return EngineResult("\n".join(lines(resp)), resp, {"pages": 1}, self.cost, latency)


class TextractLayout:
    id = "textract-layout"
    structured = False

    def __init__(self, cfg: Config, session: boto3.Session):
        self.client = session.client("textract", region_name=cfg.region)
        self.cost = cfg.textract_layout_per_page * cfg.price_margin

    def worst_case_cost(self) -> float:
        return self.cost

    def run(self, image: bytes) -> EngineResult:
        start = time.perf_counter()
        resp = self.client.analyze_document(Document={"Bytes": image}, FeatureTypes=["LAYOUT"])
        latency = time.perf_counter() - start
        return EngineResult(layout_text(resp), resp, {"pages": 1}, self.cost, latency)
