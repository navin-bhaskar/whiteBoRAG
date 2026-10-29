"""An OpenAI-compatible chat and embeddings client: LM Studio, llama-server, OpenRouter or anything alike."""

import base64
import time
from dataclasses import dataclass

import httpx


class LlmError(Exception):
    """The model server failed or was unreachable."""


@dataclass(frozen=True)
class Completion:
    text: str | None  # None: the model returned no text
    truncated: bool
    latency_s: float
    cost_usd: float = 0.0  # what the server reports in usage.cost (OpenRouter); local servers report none


RETRY_STATUSES = {429, 500, 502, 503, 504}
KEYED_RETRY_DELAYS_S = (5, 20)  # OpenRouter's upstream providers rate-limit (429) for a few seconds at a time


class LlmClient:
    # Local models are slow and may be loaded on the first call, so the timeout is generous.
    # A billed server (one with a key) is retried after a rate limit or server error; a local one fails at once.
    def __init__(self, base_url: str, timeout_s: float = 600, transport: httpx.BaseTransport | None = None,
                 api_key: str | None = None, retry_delays_s: tuple[float, ...] | None = None) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = httpx.Client(base_url=base_url.rstrip("/") + "/", timeout=timeout_s, transport=transport,
                                 headers=headers)
        self._key = api_key
        self.retry_delays_s = retry_delays_s if retry_delays_s is not None else (
            KEYED_RETRY_DELAYS_S if api_key else ())

    def _redact(self, text: str) -> str:
        return text.replace(self._key, "<key>") if self._key else text

    def _post(self, path: str, body: dict) -> dict:
        for delay in (*self.retry_delays_s, None):
            try:
                resp = self.http.post(path, json=body)
            except httpx.HTTPError as exc:
                raise LlmError(self._redact(f"{path}: {exc!r}")) from exc
            if resp.status_code not in RETRY_STATUSES or delay is None:
                break
            time.sleep(delay)
        if resp.status_code != 200:
            raise LlmError(f"{path}: HTTP {resp.status_code} {self._redact(resp.text)[:300]}")
        return resp.json()

    def chat(self, model: str, prompt: str, image: bytes | None = None, max_tokens: int = 1500) -> Completion:
        content: str | list[dict] = prompt
        if image is not None:
            url = "data:image/jpeg;base64," + base64.b64encode(image).decode()
            content = [{"type": "image_url", "image_url": {"url": url}}, {"type": "text", "text": prompt}]
        start = time.perf_counter()
        data = self._post("chat/completions", {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": max_tokens,
        })
        latency = time.perf_counter() - start
        try:
            choice = data["choices"][0]
        except (KeyError, IndexError) as exc:
            raise LlmError(f"no choices in response: {self._redact(str(data))[:300]}") from exc
        text = (choice.get("message") or {}).get("content") or None
        cost = float((data.get("usage") or {}).get("cost") or 0.0)
        return Completion(text, choice.get("finish_reason") == "length", latency, cost)

    def embed(self, model: str, text: str) -> list[float]:
        data = self._post("embeddings", {"model": model, "input": text})
        try:
            return data["data"][0]["embedding"]
        except (KeyError, IndexError) as exc:
            raise LlmError(f"no embedding in response: {self._redact(str(data))[:300]}") from exc

    def models(self, path: str = "models") -> list[str]:
        """Model ids from a catalogue; OpenRouter lists embedding models apart, at embeddings/models."""
        try:
            resp = self.http.get(path)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LlmError(f"{path}: {exc!r}") from exc
        return [m["id"] for m in resp.json().get("data", [])]
