import dataclasses

import whiteborag_offline  # noqa: F401
from harness.engines.hybrid import HINT_INTRO
from ingest import PROMPTS_DIR as INGEST_PROMPTS

from fakes import FakeLlm
from helpers import MODELS
from whiteborag_offline import PROMPTS_DIR
from whiteborag_offline.llm import Completion
from whiteborag_offline.models import LocalEmbedder, LocalReader, LocalText

IMAGE = b"\xff\xd8img"
CHECK = (INGEST_PROMPTS / "check-v1.md").read_text(encoding="utf-8")
TRANSCRIBE = (INGEST_PROMPTS / "transcribe-v2.md").read_text(encoding="utf-8")
RESTRUCTURE = (PROMPTS_DIR / "restructure-v1.md").read_text(encoding="utf-8")


def _reader(llm, **models):
    return LocalReader(llm, dataclasses.replace(MODELS, **models), 1500)


def test_reader_check_uses_check_model_and_prompt():
    llm = FakeLlm("USABLE")
    assert _reader(llm).check(IMAGE).text == "USABLE"
    assert llm.calls == [{"model": "vlm-check", "prompt": CHECK, "image": IMAGE, "max_tokens": 1500}]


def test_reader_raw_transcribe():
    llm = FakeLlm("# Board")
    assert _reader(llm).transcribe(IMAGE).text == "# Board"
    assert llm.calls == [{"model": "vlm", "prompt": TRANSCRIBE, "image": IMAGE, "max_tokens": 1500}]


def test_reader_hybrid_vision_two_calls_in_order():
    llm = FakeLlm(lambda call: "line a\nline b" if call["model"] == "ocr" else "# Board")
    reply = _reader(llm, transcribe_mode="hybrid-vision", ocr="ocr", ocr_prompt="OCR:").transcribe(IMAGE)
    first, second = llm.calls
    assert (first["model"], first["prompt"], first["image"]) == ("ocr", "OCR:", IMAGE)
    assert second["model"] == "vlm"
    assert second["image"] == IMAGE
    assert second["prompt"] == TRANSCRIBE + "\n\n" + HINT_INTRO + "\nline a\nline b"
    assert reply.text == "# Board"


def test_reader_hybrid_text_second_call_has_no_image():
    llm = FakeLlm(lambda call: "line a" if call["model"] == "ocr" else "# Board")
    _reader(llm, transcribe_mode="hybrid-text", ocr="ocr", ocr_prompt="OCR:").transcribe(IMAGE)
    _, second = llm.calls
    assert second["image"] is None
    assert second["prompt"] == RESTRUCTURE + "\n\n---\nline a"


def test_reader_hybrid_ocr_truncation_carries_through():
    llm = FakeLlm(lambda call: Completion("line a", True, 0.1) if call["model"] == "ocr" else "# Board")
    reply = _reader(llm, transcribe_mode="hybrid-text", ocr="ocr", ocr_prompt="OCR:").transcribe(IMAGE)
    assert reply.truncated is True


def test_reader_strips_fences_and_flags_truncation():
    llm = FakeLlm(Completion("```markdown\n# Board\n```", True, 0.1))
    reply = _reader(llm).transcribe(IMAGE)
    assert (reply.text, reply.truncated) == ("# Board", True)


def test_reader_normalize_uses_text_model_without_image():
    llm = FakeLlm("Project: X\n---\n# Board")
    _reader(llm).normalize("PROMPT")
    assert llm.calls == [{"model": "llama", "prompt": "PROMPT", "image": None, "max_tokens": 1500}]


def test_embedder_returns_vector():
    llm = FakeLlm(dims=4)
    assert len(LocalEmbedder(llm, "emb").embed("text")) == 4


def test_text_ask_passes_max_tokens_and_keeps_fences():
    llm = FakeLlm('```json\n{"a": 1}\n```')
    reply = LocalText(llm, "llama").ask("Q", 300)
    assert llm.calls[0]["max_tokens"] == 300
    assert reply.text == '```json\n{"a": 1}\n```'
