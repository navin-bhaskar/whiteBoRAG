import base64
import json

import httpx
import pytest

from whiteborag_offline.llm import LlmClient, LlmError


def _client(handler) -> LlmClient:
    return LlmClient("http://llm.test/v1", transport=httpx.MockTransport(handler))


def _reply(text: str, finish: str = "stop") -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": text}, "finish_reason": finish}]})


def test_chat_sends_image_as_data_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return _reply("board")

    result = _client(handler).chat("vlm", "read it", image=b"\xff\xd8jpeg")
    body = seen["body"]
    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert body["model"] == "vlm"
    assert body["temperature"] == 0
    assert body["max_tokens"] == 1500
    assert body["messages"][0]["content"] == [
        {"type": "image_url",
         "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8jpeg").decode()}},
        {"type": "text", "text": "read it"},
    ]
    assert result.text == "board"
    assert result.truncated is False


def test_chat_text_only_sends_string_content():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return _reply("ok")

    _client(handler).chat("llm", "hello", max_tokens=50)
    assert seen["body"]["messages"][0]["content"] == "hello"
    assert seen["body"]["max_tokens"] == 50


def test_truncated_when_finish_reason_length():
    result = _client(lambda r: _reply("cut", "length")).chat("llm", "x")
    assert result.truncated is True


def test_empty_content_is_none():
    result = _client(lambda r: _reply("")).chat("llm", "x")
    assert result.text is None


def test_http_error_raises_llm_error():
    with pytest.raises(LlmError):
        _client(lambda r: httpx.Response(500, text="model not loaded")).chat("llm", "x")


def test_connect_error_raises_llm_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LlmError):
        _client(handler).chat("llm", "x")


def test_embed_returns_vector():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})

    assert _client(handler).embed("emb", "text") == [0.1, 0.2]
    assert seen["url"] == "http://llm.test/v1/embeddings"
    assert seen["body"] == {"model": "emb", "input": "text"}


def _keyed(handler, key: str | None = "k-123") -> LlmClient:
    return LlmClient("http://llm.test/v1", transport=httpx.MockTransport(handler), api_key=key)


def test_api_key_sent_as_bearer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return _reply("ok")

    _keyed(handler).chat("m", "hi")
    assert seen["auth"] == "Bearer k-123"


def test_no_key_sends_no_auth_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return _reply("ok")

    _keyed(handler, key=None).chat("m", "hi")
    assert seen["auth"] is None


def test_error_message_never_contains_key():
    client = _keyed(lambda request: httpx.Response(401, json={"error": "bad key k-123"}))
    with pytest.raises(LlmError) as info:
        client.chat("m", "hi")
    assert "401" in str(info.value)
    assert "k-123" not in str(info.value)


def test_cost_read_from_usage():
    body = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"cost": 0.00042}}
    assert _keyed(lambda request: httpx.Response(200, json=body)).chat("m", "hi").cost_usd == 0.00042


def test_cost_missing_is_zero():
    assert _keyed(lambda request: _reply("ok")).chat("m", "hi").cost_usd == 0.0


def test_null_content_is_no_text():
    body = {"choices": [{"message": {"content": None, "reasoning": "thinking"}, "finish_reason": "stop"}]}
    assert _keyed(lambda request: httpx.Response(200, json=body)).chat("m", "hi").text is None


def test_models_lists_another_catalogue():
    def handler(request):
        assert request.url.path == "/v1/embeddings/models"
        return httpx.Response(200, json={"data": [{"id": "amazon/titan-embed-text-v2"}]})

    assert _client(handler).models("embeddings/models") == ["amazon/titan-embed-text-v2"]
