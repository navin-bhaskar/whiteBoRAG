import pytest
from harness.engines import EngineError
from harness.engines.hybrid import HINT_INTRO

from fakes import FakeLlm
from whiteborag_offline.eval.engines import LocalHybridText, LocalHybridVision, LocalRaw, OcrCache
from whiteborag_offline.llm import Completion, LlmError

IMAGE = b"\xff\xd8image-bytes"


def test_local_raw_sends_image_and_transcribe_prompt():
    llm = FakeLlm("```markdown\n# Board\n- item\n```")
    engine = LocalRaw(llm, "qwen", "qwen3-vl", "TRANSCRIBE PROMPT")
    result = engine.run(IMAGE)
    assert engine.id == "local:qwen"
    assert llm.calls == [{"model": "qwen3-vl", "prompt": "TRANSCRIBE PROMPT", "image": IMAGE, "max_tokens": 1500}]
    assert result.text == "# Board\n- item"
    assert result.cost_usd == 0.0
    assert engine.worst_case_cost() == 0.0


def test_hybrid_vision_uses_cached_ocr_as_hints(tmp_path):
    cache = OcrCache(tmp_path)
    cache.put("glm", IMAGE, "line one\nline two")
    llm = FakeLlm("# Board")
    engine = LocalHybridVision(llm, "glm", "qwen3-vl", "TRANSCRIBE PROMPT", cache)
    engine.run(IMAGE)
    (call,) = llm.calls
    assert engine.id == "local-hv:glm"
    assert call["model"] == "qwen3-vl"
    assert call["image"] == IMAGE
    assert call["prompt"].startswith("TRANSCRIBE PROMPT")
    assert call["prompt"].endswith(HINT_INTRO + "\nline one\nline two")


def test_hybrid_text_sends_no_image(tmp_path):
    cache = OcrCache(tmp_path)
    cache.put("glm", IMAGE, "line one")
    llm = FakeLlm("# Board")
    engine = LocalHybridText(llm, "glm", "llama", "RESTRUCTURE PROMPT", cache)
    engine.run(IMAGE)
    (call,) = llm.calls
    assert engine.id == "local-ht:glm"
    assert call["image"] is None
    assert call["model"] == "llama"
    assert "RESTRUCTURE PROMPT" in call["prompt"]
    assert call["prompt"].endswith("line one")


@pytest.mark.parametrize("cls", [LocalHybridText, LocalHybridVision])
def test_hybrid_cache_miss_raises_engine_error(tmp_path, cls):
    llm = FakeLlm()
    engine = cls(llm, "glm", "m", "P", OcrCache(tmp_path))
    with pytest.raises(EngineError) as info:
        engine.run(IMAGE)
    assert info.value.cost_usd == 0.0
    assert llm.calls == []


def test_llm_error_becomes_engine_error():
    engine = LocalRaw(FakeLlm(LlmError("down")), "qwen", "m", "P")
    with pytest.raises(EngineError):
        engine.run(IMAGE)


def test_empty_reply_becomes_engine_error():
    engine = LocalRaw(FakeLlm(""), "qwen", "m", "P")
    with pytest.raises(EngineError):
        engine.run(IMAGE)


def test_ocr_cache_roundtrip_keyed_by_bytes(tmp_path):
    cache = OcrCache(tmp_path)
    assert cache.get("glm", IMAGE) is None
    cache.put("glm", IMAGE, "text")
    assert cache.get("glm", IMAGE) == "text"
    assert cache.get("glm", IMAGE + b"x") is None
    assert cache.get("other", IMAGE) is None


def test_local_raw_reports_cost():
    llm = FakeLlm(Completion("# Board", False, 1.0, 0.003))
    assert LocalRaw(llm, "nova", "amazon/nova-2-lite-v1", "P").run(IMAGE).cost_usd == 0.003
