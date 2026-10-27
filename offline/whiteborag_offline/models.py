"""Local model implementations of the shared interfaces: ingest's Reader and Embedder, query's Llm."""

from collections.abc import Callable

from harness.engines.hybrid import hint_prompt
from ingest import PROMPTS_DIR as INGEST_PROMPTS
from ingest.check import PROMPT_VERSION as CHECK_VERSION
from ingest.board import parse_board
from ingest.normalize import NormalizationError, parse_response, strip_fence
from ingest.pipeline import TRANSCRIBE_VERSION, Reply
from ingest.projects import match_project
from ingest.store import Project

from whiteborag_offline import PROMPTS_DIR
from whiteborag_offline.config import Models
from whiteborag_offline.llm import LlmClient

RESTRUCTURE_VERSION = "restructure-v1"


def _reply(text: str | None, truncated: bool) -> Reply:
    return Reply(strip_fence(text) if text is not None else None, truncated)


def title_project(title: str, projects: list[Project]) -> str | None:
    """The display name of the first known project that a window of the title fuzzy-matches. Windows run from
    one word up to the longest known name plus one (a name written as one word may be read as two), longest
    first at each position."""
    known = {p.key: [p.display_name, *p.aliases] for p in projects}
    longest = max((len(name.split()) for names in known.values() for name in names), default=1) + 1
    words = title.split()
    windows = [" ".join(words[i:i + n]) for i in range(len(words)) for n in range(longest, 0, -1)
               if i + n <= len(words)]
    for window in windows:
        if (key := match_project(window, known)) is not None:
            return next(p.display_name for p in projects if p.key == key)
    return None


class LocalReader:
    """Check, transcribe and normalize with local models. A hybrid transcribe is two calls: the OCR model
    reads the photo, then the transcribe model writes board Markdown from that text (and the photo, for
    hybrid-vision).

    Normalize keeps the model's spelling fixes but not its `Project:` pick, which local models get wrong: the line
    is rewritten from the title and the stored projects. New projects still come from a `Name: rest` title."""

    def __init__(self, client: LlmClient, models: Models, max_tokens: int,
                 projects: Callable[[], list[Project]]) -> None:
        self.client, self.models, self.max_tokens, self.projects = client, models, max_tokens, projects
        self.check_prompt = (INGEST_PROMPTS / f"{CHECK_VERSION}.md").read_text(encoding="utf-8")
        self.transcribe_prompt = (INGEST_PROMPTS / f"{TRANSCRIBE_VERSION}.md").read_text(encoding="utf-8")
        self.restructure_prompt = (PROMPTS_DIR / f"{RESTRUCTURE_VERSION}.md").read_text(encoding="utf-8")

    def _chat(self, model: str, prompt: str, image: bytes | None):
        return self.client.chat(model, prompt, image=image, max_tokens=self.max_tokens)

    def check(self, image: bytes) -> Reply:
        c = self._chat(self.models.check, self.check_prompt, image)
        return _reply(c.text, c.truncated)

    def transcribe(self, image: bytes) -> Reply:
        mode, model = self.models.transcribe_mode, self.models.transcribe
        if mode == "raw":
            c = self._chat(model, self.transcribe_prompt, image)
            return _reply(c.text, c.truncated)
        ocr = self._chat(self.models.ocr, self.models.ocr_prompt or "Transcribe all text in this image.", image)
        text = ocr.text or ""
        if mode == "hybrid-vision":
            c = self._chat(model, hint_prompt(self.transcribe_prompt, text.splitlines()), image)
        else:
            c = self._chat(model, f"{self.restructure_prompt}\n\n---\n{text}", None)
        return _reply(c.text, c.truncated or ocr.truncated)

    def normalize(self, prompt: str) -> Reply:
        c = self._chat(self.models.text, prompt, None)
        reply = _reply(c.text, c.truncated)
        try:
            _, body = parse_response(reply.text or "")
        except NormalizationError:
            return reply
        project = title_project(parse_board(body).title, self.projects())
        return Reply(f"Project: {project or 'none'}\n---\n{body}", reply.truncated)


class LocalEmbedder:
    def __init__(self, client: LlmClient, model: str) -> None:
        self.client, self.model = client, model

    def embed(self, text: str) -> list[float]:
        return self.client.embed(self.model, text)


class LocalText:
    """query.handler's Llm: one text prompt, the reply as the model wrote it (the query code parses it)."""

    def __init__(self, client: LlmClient, model: str) -> None:
        self.client, self.model = client, model

    def ask(self, prompt: str, max_tokens: int) -> Reply:
        c = self.client.chat(self.model, prompt, max_tokens=max_tokens)
        return Reply(c.text, c.truncated)
