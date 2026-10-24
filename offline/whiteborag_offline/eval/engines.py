"""Harness engines for local models behind an OpenAI-compatible server. Every call costs $0."""

import hashlib
from pathlib import Path

from harness.engines import EngineError, EngineResult
from harness.engines.bedrock import strip_fences
from harness.engines.hybrid import hint_prompt

from whiteborag_offline.llm import Completion, LlmClient, LlmError


class OcrCache:
    """Plain-OCR text per candidate, keyed by the image bytes (the runner hands engines bytes, not names)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, cand_id: str, image: bytes) -> Path:
        return self.root / cand_id / f"{hashlib.sha256(image).hexdigest()[:16]}.txt"

    def get(self, cand_id: str, image: bytes) -> str | None:
        path = self._path(cand_id, image)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def put(self, cand_id: str, image: bytes, text: str) -> None:
        path = self._path(cand_id, image)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _call(client: LlmClient, model: str, prompt: str, image: bytes | None) -> Completion:
    try:
        reply = client.chat(model, prompt, image=image)
    except LlmError as exc:
        raise EngineError(str(exc), 0.0) from exc
    if reply.text is None:
        raise EngineError(f"{model} returned no text", 0.0)
    return reply


def _result(reply: Completion, model: str, latency_s: float) -> EngineResult:
    return EngineResult(strip_fences(reply.text), {"model": model, "truncated": reply.truncated}, {}, 0.0, latency_s)


class _Local:
    structured = True

    def worst_case_cost(self) -> float:
        return 0.0


class LocalRaw(_Local):
    """The candidate reads the photo and writes board Markdown itself."""

    def __init__(self, client: LlmClient, cand_id: str, model: str, prompt: str) -> None:
        self.id = f"local:{cand_id}"
        self.client, self.model, self.prompt = client, model, prompt

    def run(self, image: bytes) -> EngineResult:
        reply = _call(self.client, self.model, self.prompt, image)
        return _result(reply, self.model, reply.latency_s)


class _Hybrid(_Local):
    """A second model turns the candidate's cached OCR into board Markdown. It never runs the OCR model itself,
    so a pass over the images keeps one model loaded."""

    kind = ""

    def __init__(self, client: LlmClient, cand_id: str, model: str, prompt: str, cache: OcrCache) -> None:
        self.id = f"{self.kind}:{cand_id}"
        self.cand_id, self.client, self.model, self.prompt, self.cache = cand_id, client, model, prompt, cache

    def _ocr(self, image: bytes) -> str:
        text = self.cache.get(self.cand_id, image)
        if text is None:
            raise EngineError(f"no cached OCR for this image; run `bakeoff ocr --candidate {self.cand_id}` first", 0.0)
        return text


class LocalHybridVision(_Hybrid):
    """OCR lines as hints next to the image, as the AWS hybrid engine does with Textract."""

    kind = "local-hv"

    def run(self, image: bytes) -> EngineResult:
        lines = self._ocr(image).splitlines()
        reply = _call(self.client, self.model, hint_prompt(self.prompt, lines), image)
        return _result(reply, self.model, reply.latency_s)


class LocalHybridText(_Hybrid):
    """OCR text alone to a text model, which never sees the photo."""

    kind = "local-ht"

    def run(self, image: bytes) -> EngineResult:
        text = self._ocr(image)
        reply = _call(self.client, self.model, f"{self.prompt}\n\n---\n{text}", None)
        return _result(reply, self.model, reply.latency_s)
