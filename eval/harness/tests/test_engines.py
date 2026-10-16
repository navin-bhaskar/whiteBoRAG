import boto3
import pytest

from harness.config import load_config
from harness.engines import ALL_ENGINES, build_engines, engine_dir
from harness.engines import bedrock, hybrid, rekognition, textract


def _session():
    return boto3.Session(region_name="ap-south-1")


def test_textract_lines():
    resp = {"Blocks": [{"BlockType": "PAGE"}, {"BlockType": "LINE", "Text": "RAG revision"},
                       {"BlockType": "WORD", "Text": "RAG"}, {"BlockType": "LINE", "Text": "what is chunking?"}]}
    assert textract.lines(resp) == ["RAG revision", "what is chunking?"]


def test_textract_layout_text():
    resp = {"Blocks": [
        {"BlockType": "LAYOUT_TITLE", "Id": "t", "Relationships": [{"Type": "CHILD", "Ids": ["l1"]}]},
        {"BlockType": "LAYOUT_TEXT", "Id": "x", "Relationships": [{"Type": "CHILD", "Ids": ["l2", "l3"]}]},
        {"BlockType": "LINE", "Id": "l1", "Text": "RAG revision"},
        {"BlockType": "LINE", "Id": "l2", "Text": "a"}, {"BlockType": "LINE", "Id": "l3", "Text": "b"}]}
    assert textract.layout_text(resp) == "RAG revision\n\na\nb"


def test_rekognition_lines():
    resp = {"TextDetections": [{"Type": "LINE", "DetectedText": "RAG revision:"},
                               {"Type": "WORD", "DetectedText": "RAG"}]}
    assert rekognition.lines(resp) == ["RAG revision:"]


def test_strip_fences():
    assert bedrock.strip_fences("```markdown\n# T\n- a\n```\n") == "# T\n- a"
    assert bedrock.strip_fences("# T") == "# T"


def test_converse_text():
    assert bedrock.converse_text({"output": {"message": {"content": [{"text": "# T"}]}}}) == "# T"


def test_hint_prompt():
    assert hybrid.hint_prompt("P", ["a", "b"]).endswith("the image is authoritative:\na\nb")


def test_build_engines_all():
    engines = build_engines(["all"], load_config(), _session())
    assert [e.id for e in engines] == ALL_ENGINES and len(engines) == 9
    assert {e.id for e in engines if e.structured} == {i for i in ALL_ENGINES if ":" in i}


def test_build_engines_unknown():
    with pytest.raises(ValueError):
        build_engines(["bedrock:claude"], load_config(), _session())


def test_engine_dir():
    assert engine_dir("hybrid:nova-pro") == "hybrid_nova-pro"


def test_worst_case_costs_are_bounded():
    for e in build_engines(["all"], load_config(), _session()):
        assert 0 < e.worst_case_cost() < 0.02


class _FakeConverser:
    def __init__(self, resp=None, error=None):
        self.resp, self.error = resp, error

    def worst_case_cost(self):
        return 0.01

    def call(self, image, prompt):
        if self.error:
            raise self.error
        return self.resp, {"input_tokens": 1, "output_tokens": 1}, 0.0025


def test_bedrock_unparseable_response_still_reports_cost():
    from harness.engines import EngineError
    eng = build_engines(["bedrock:nova-lite"], load_config(), _session())[0]
    eng.converser = _FakeConverser(resp={"output": {"message": {"content": []}}, "stopReason": "guardrail_intervened"})
    with pytest.raises(EngineError) as exc:
        eng.run(b"img")
    assert exc.value.cost_usd == 0.0025


def test_hybrid_bedrock_failure_reports_textract_cost():
    from harness.engines import EngineError, EngineResult

    class FakeTextract:
        def worst_case_cost(self):
            return 0.0018

        def run(self, image):
            return EngineResult("line", {}, {"pages": 1}, 0.0018, 0.1)

    eng = build_engines(["hybrid:nova-lite"], load_config(), _session())[0]
    eng.textract = FakeTextract()
    eng.converser = _FakeConverser(error=RuntimeError("AccessDeniedException"))
    with pytest.raises(EngineError) as exc:
        eng.run(b"img")
    assert exc.value.cost_usd == 0.0018
