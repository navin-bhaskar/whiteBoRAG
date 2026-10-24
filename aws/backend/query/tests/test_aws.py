from query.aws import NovaText, S3VectorSearch


class FakeVectorsClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def query_vectors(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"vectors": [{"key": "k", "metadata": {}, "distance": 0.1}]}


class FakeBedrock:
    def __init__(self, resp: dict) -> None:
        self.resp = resp
        self.calls: list[dict] = []

    def converse(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return self.resp


def search_with_fake() -> tuple[S3VectorSearch, FakeVectorsClient]:
    search = S3VectorSearch.__new__(S3VectorSearch)
    search.where = {"vectorBucketName": "vb", "indexName": "captures"}
    search.client = FakeVectorsClient()
    return search, search.client


def nova_with(resp: dict) -> NovaText:
    nova = NovaText.__new__(NovaText)
    nova.model_id, nova.client, nova.usage = "m", FakeBedrock(resp), {"input": 0, "output": 0}
    return nova


def test_vector_query_shape():
    search, client = search_with_fake()
    assert search.query([0.5], 8, {"project": {"$eq": "x"}}) == [{"key": "k", "metadata": {}, "distance": 0.1}]
    assert client.calls[0] == {
        "vectorBucketName": "vb", "indexName": "captures", "topK": 8, "queryVector": {"float32": [0.5]},
        "returnMetadata": True, "returnDistance": True, "filter": {"project": {"$eq": "x"}},
    }


def test_vector_query_without_filter_omits_it():
    search, client = search_with_fake()
    search.query([0.5], 8, None)
    assert "filter" not in client.calls[0]


def test_nova_reply_and_tokens():
    nova = nova_with({"output": {"message": {"content": [{"text": "hi"}]}}, "stopReason": "end_turn",
                      "usage": {"inputTokens": 100, "outputTokens": 7}})
    reply = nova.ask("p", 800)
    assert (reply.text, reply.truncated) == ("hi", False)
    assert nova.client.calls[0]["inferenceConfig"] == {"maxTokens": 800, "temperature": 0}
    nova.ask("p", 800)
    assert nova.tokens() == {"input": 200, "output": 14} and nova.tokens() == {"input": 0, "output": 0}


def test_nova_truncated_and_empty():
    reply = nova_with({"output": {"message": {"content": []}}, "stopReason": "max_tokens"}).ask("p", 5)
    assert (reply.text, reply.truncated) == (None, True)
