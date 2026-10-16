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
