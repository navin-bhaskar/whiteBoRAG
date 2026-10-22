import json

from fakes import FakeEmbedder, InMemoryStore
from ingest.pipeline import Reply
from ingest.store import Project
from query.answer import FALLBACK
from query.evidence import NOTHING
from query.handler import Deps, handle
from query_fakes import FakeSearch, Seeded, board, hit

KEY_ID = "query-key"
ORIGIN = "http://localhost:8000"
TODOS = '{"intent":"todos","project_name":null,"follow_up":false}'


class FakeLlm:
    """Scripted replies, one per call, in order."""

    def __init__(self, *replies: str | None) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.max_tokens: list[int] = []

    def ask(self, prompt: str, max_tokens: int) -> Reply:
        self.prompts.append(prompt)
        self.max_tokens.append(max_tokens)
        return Reply(self.replies.pop(0), False)


class Raising:
    def ask(self, prompt: str, max_tokens: int) -> Reply:
        raise TimeoutError("bedrock read timed out")


def today() -> str:
    return "2026-10-21"


def ev(question: str = "what was the latest todo list?", key_id: str = KEY_ID, **extra) -> dict:
    return {"body": json.dumps({"question": question, **extra}), "requestContext": {"identity": {"apiKeyId": key_id}}}


def body(response: dict) -> dict:
    assert response["statusCode"] == 200, response
    return json.loads(response["body"])


def deps_with(store=None, blobs=None, llm=None, search=None) -> Deps:
    seeded = Seeded()
    return Deps(
        store=store if store is not None else seeded.store,
        blobs=blobs if blobs is not None else seeded.blobs,
        llm=llm or FakeLlm(TODOS, "The answer."),
        embedder=FakeEmbedder(),
        search=search or FakeSearch([]),
        sign=lambda key: "https://signed/" + key,
        query_key_id=KEY_ID,
        origin=ORIGIN,
    )


def seeded_deps(llm, days=("15", "17")) -> Deps:
    s = Seeded()
    for day in days:
        s.add(f"202610{day}T084632Z")
    return deps_with(s.store, s.blobs, llm)


def store_with(*projects: tuple[str, str]) -> InMemoryStore:
    store = InMemoryStore()
    for key, display in projects:
        store.create_project(Project(key, display, {display: 1}))
    return store


def test_device_key_rejected():
    out = handle(ev(key_id="device-key"), deps_with(), today)
    assert out["statusCode"] == 403 and out["headers"]["Access-Control-Allow-Origin"] == ORIGIN


def test_missing_request_context_rejected():
    assert handle({"body": "{}"}, deps_with(), today)["statusCode"] == 403


def test_bad_body_is_400_with_cors():
    out = handle(ev(""), deps_with(), today)
    assert out["statusCode"] == 400 and out["headers"]["Access-Control-Allow-Origin"] == ORIGIN
    assert "error" in json.loads(out["body"])


def test_unknown_requested_project_is_400():
    llm = FakeLlm(TODOS)
    assert handle(ev(project="zebra"), seeded_deps(llm), today)["statusCode"] == 400


def test_todos_end_to_end():
    llm = FakeLlm(TODOS, "Three todos.")
    out = body(handle(ev(), seeded_deps(llm), today))
    assert out["answer"] == "Three todos."
    assert out["project"] == {"key": "whiteborag", "display_name": "whiteBORAG", "how": "latest"}
    assert out["understood"]["intent"] == "todos" and out["understood"]["project"] == "whiteborag"
    assert out["clarify"] is None
    [source] = out["sources"]
    assert source["image_url"].startswith("https://signed/captures/")
    assert (source["date"], source["project"], source["section"]) == ("2026-10-17", "whiteBORAG", "todos")
    assert set(source) == {"capture_id", "captured_at", "date", "project", "section", "image_url"}
    assert llm.max_tokens[1] == 800 and "2026-10-21" in llm.prompts[0]


def test_sources_newest_first():
    llm = FakeLlm('{"intent":"todos","project_name":"whiteborag","date_from":"2026-10-01","date_to":"2026-10-31"}', "ok")
    out = body(handle(ev(), seeded_deps(llm, days=("15", "19", "17")), today))
    dates = [s["captured_at"] for s in out["sources"]]
    assert len(dates) == 3 and dates == sorted(dates, reverse=True)
    assert out["project"]["how"] == "named"


def test_requested_project_skips_matching():
    llm = FakeLlm('{"intent":"todos","project_name":"zebra"}', "ok")
    out = body(handle(ev(project="whiteborag"), seeded_deps(llm), today))
    assert out["project"]["key"] == "whiteborag" and out["answer"] == "ok"


def test_follow_up_uses_previous_project():
    llm = FakeLlm('{"intent":"search","project_name":null,"follow_up":true}', "ok")
    history = [{"question": "todos?", "understood": {"intent": "todos", "project": "whiteborag"}, "sources": []}]
    out = body(handle(ev("and now?", history=history), seeded_deps(llm), today))
    assert out["understood"]["intent"] == "todos" and out["project"]["how"] == "previous"


def test_clarify_makes_no_answer_call():
    llm = FakeLlm('{"intent":"diagram_latest","project_name":"tender crawler"}')
    store = store_with(("tendercrawler", "Tender crawler"), ("tendercrawlers", "Tender crawlers"))
    out = body(handle(ev("arch of tender crawler?"), deps_with(store=store, llm=llm), today))
    assert out["answer"] is None and out["sources"] == [] and out["project"] is None
    assert {o["key"] for o in out["clarify"]["options"]} == {"tendercrawler", "tendercrawlers"}
    assert len(llm.prompts) == 1


def test_nothing_found_skips_answer_call():
    s = Seeded()
    s.add("20261015T084632Z", board(todos=["[ ] Deploy lambda"]))
    llm = FakeLlm('{"intent":"diagram_latest","project_name":"whiteborag"}')
    out = body(handle(ev("diagram?"), deps_with(s.store, s.blobs, llm), today))
    assert out["answer"] == "whiteBORAG has no boards with a diagram yet."
    assert out["sources"] == [] and out["project"]["key"] == "whiteborag"
    assert len(llm.prompts) == 1


def test_latest_board_end_to_end():
    s = Seeded()
    s.add("20261015T084632Z")
    newest = s.add("20261019T084632Z", board("whiteBORAG goals"))
    llm = FakeLlm('{"intent":"board_latest","project_name":"whiteborag"}', "Goals.")
    out = body(handle(ev("what's on the latest board?"), deps_with(s.store, s.blobs, llm), today))
    assert out["answer"] == "Goals." and out["understood"]["intent"] == "board_latest"
    [source] = out["sources"]
    assert (source["capture_id"], source["section"]) == (newest, "board")
    assert "whiteBORAG goals" in llm.prompts[1]


def test_latest_board_nothing_found():
    s = Seeded()
    s.add("20261015T084632Z")
    llm = FakeLlm('{"intent":"board_latest","project_name":"whiteborag","date_from":"2026-10-20","date_to":"2026-10-20"}')
    out = body(handle(ev("latest board from 20 Oct?"), deps_with(s.store, s.blobs, llm), today))
    assert out["answer"] == "whiteBORAG has no boards yet." and out["sources"] == []


def test_empty_store():
    for reply in (TODOS, '{"intent":"diagram_history","project_name":null}', '{"intent":"search"}', "junk"):
        llm = FakeLlm(reply)
        out = body(handle(ev(), deps_with(store=InMemoryStore(), llm=llm), today))
        assert (out["answer"], out["sources"], out["clarify"]) == (NOTHING["empty"], [], None)
        assert len(llm.prompts) == 1


def test_search_end_to_end():
    llm = FakeLlm('{"intent":"search","project_name":null,"section":"notes"}', "Found it.")
    search = FakeSearch([hit(1, "soil sensor notes", project="none")])
    out = body(handle(ev("soil sensors?"), deps_with(store=store_with(("whiteborag", "whiteBORAG")), llm=llm, search=search), today))
    assert out["answer"] == "Found it." and out["project"] is None
    [source] = out["sources"]
    assert (source["project"], source["section"]) == (None, "notes")
    assert search.last_filter == {"section": {"$eq": "notes"}}


def test_search_finds_nothing():
    llm = FakeLlm('{"intent":"search"}')
    out = body(handle(ev("soil?"), deps_with(store=store_with(("whiteborag", "whiteBORAG")), llm=llm), today))
    assert (out["answer"], out["sources"]) == (NOTHING["search"], [])


def test_answer_reply_empty_uses_fallback():
    llm = FakeLlm(TODOS, None)
    out = body(handle(ev(), seeded_deps(llm), today))
    assert out["answer"] == FALLBACK and len(out["sources"]) == 1


def test_truncated_answer_uses_fallback():
    class Truncating(FakeLlm):
        def ask(self, prompt, max_tokens):
            reply = super().ask(prompt, max_tokens)
            return Reply(reply.text, len(self.prompts) == 2)

    out = body(handle(ev(), seeded_deps(Truncating(TODOS, "The list is: ...")), today))
    assert out["answer"] == FALLBACK


def test_bedrock_error_is_500_with_cors():
    out = handle(ev("q"), deps_with(llm=Raising()), today)
    assert out["statusCode"] == 500 and out["headers"]["Access-Control-Allow-Origin"] == ORIGIN
    assert json.loads(out["body"]) == {"error": "something went wrong"}


def test_one_log_line_without_question_or_key(capsys):
    llm = FakeLlm(TODOS, "ok")
    handle(ev("what was the SECRET todo list?"), seeded_deps(llm), today)
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert len(lines) == 1
    log = json.loads(lines[0])
    assert log["question_length"] == len("what was the SECRET todo list?")
    assert (log["status"], log["intent"], log["project"], log["how"], log["sources"]) == (200, "todos", "whiteborag", "latest", 1)
    assert "latency_ms" in log and "SECRET" not in lines[0] and KEY_ID not in lines[0]


def test_token_usage_logged(capsys):
    class Counting(FakeLlm):
        def tokens(self):
            return {"input": 10, "output": 2}

    handle(ev(), seeded_deps(Counting(TODOS, "ok")), today)
    assert json.loads(capsys.readouterr().out)["tokens"] == {"input": 10, "output": 2}
