"""Test doubles shared by the offline tests."""

from whiteborag_offline.llm import Completion, LlmError


class FakeLlm:
    """Records each call; answers chat from `replies` (a str, a callable, or an exception) and embeds deterministically."""

    def __init__(self, replies=None, dims: int = 8) -> None:
        self.replies = replies if replies is not None else "reply"
        self.dims = dims
        self.calls: list[dict] = []

    def chat(self, model: str, prompt: str, image: bytes | None = None, max_tokens: int = 1500) -> Completion:
        call = {"model": model, "prompt": prompt, "image": image, "max_tokens": max_tokens}
        self.calls.append(call)
        reply = self.replies(call) if callable(self.replies) else self.replies
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, Completion):
            return reply
        return Completion(reply or None, False, 0.5)

    def embed(self, model: str, text: str) -> list[float]:
        if isinstance(self.replies, LlmError):
            raise self.replies
        seed = sum(text.encode()) or 1
        return [((seed * (i + 3)) % 97) / 97 + 0.01 for i in range(self.dims)]
