import json

import pytest

from harness.dataset import Sample
from harness.engines import EngineResult
from harness.ledger import BudgetExceeded, Ledger
from harness.runner import run


class Fake:
    def __init__(self, id="fake", cost=0.01, fail_on=()):
        self.id, self.structured, self.cost, self.fail_on, self.calls = id, False, cost, set(fail_on), 0

    def worst_case_cost(self):
        return self.cost

    def run(self, image):
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("ThrottlingException")
        return EngineResult("hello", {"r": 1}, {"pages": 1}, self.cost, 0.1)


@pytest.fixture
def data(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    for n in ("a.jpg", "b.jpg"):
        (imgs / n).write_bytes(b"jpg")
    samples = [Sample(n, "g.md", "env", "") for n in ("a.jpg", "b.jpg")]
    return tmp_path, imgs, samples


def test_run_writes_layout_and_ledger(data):
    tmp, imgs, samples = data
    lg = Ledger(tmp / "ledger.jsonl", 5.0)
    st = run(tmp / "r", imgs, samples, [Fake("bedrock:x")], ["raw"], lg)
    assert (st.done, st.failed) == (2, 0) and lg.total() == pytest.approx(0.02)
    assert (tmp / "r/transcripts/bedrock_x/raw/a.md").read_text(encoding="utf-8") == "hello"
    assert json.loads((tmp / "r/responses/bedrock_x/raw/b.json").read_text(encoding="utf-8"))["ok"]


def test_resume_skips_completed(data):
    tmp, imgs, samples = data
    lg = Ledger(tmp / "l.jsonl", 5.0)
    eng = Fake()
    run(tmp / "r", imgs, samples, [eng], ["raw"], lg)
    st = run(tmp / "r", imgs, samples, [eng], ["raw"], lg)
    assert (st.done, st.skipped, eng.calls) == (0, 2, 2)


def test_failed_call_recorded_and_retried(data):
    tmp, imgs, samples = data
    lg = Ledger(tmp / "l.jsonl", 5.0)
    eng = Fake(fail_on={1})
    st = run(tmp / "r", imgs, samples, [eng], ["raw"], lg)
    assert (st.done, st.failed) == (1, 1) and lg.total() == pytest.approx(0.01)
    st = run(tmp / "r", imgs, samples, [eng], ["raw"], lg)
    assert (st.done, st.skipped, st.failed) == (1, 1, 0)


def test_preflight_refuses_without_calling(data):
    tmp, imgs, samples = data
    lg = Ledger(tmp / "l.jsonl", 5.0)
    lg.record({"cost_usd": 4.99})
    eng = Fake(cost=0.01)
    with pytest.raises(BudgetExceeded):
        run(tmp / "r", imgs, samples, [eng], ["raw"], lg)
    assert eng.calls == 0


def test_in_flight_stop_keeps_partial_run(data):
    tmp, imgs, samples = data
    lg = Ledger(tmp / "l.jsonl", 5.0)

    class Pricey(Fake):  # cheap estimate, expensive real cost
        def run(self, image):
            r = super().run(image)
            r.cost_usd = 4.9995  # 4.9995 + 0.001 > 5
            return r

    with pytest.raises(BudgetExceeded):
        run(tmp / "r", imgs, samples, [Pricey(cost=0.001)], ["raw"], lg)
    assert (tmp / "r/transcripts/fake/raw/a.md").exists()
    assert not (tmp / "r/transcripts/fake/raw/b.md").exists()


def test_billed_failure_is_charged(data):
    from harness.engines import EngineError

    tmp, imgs, samples = data
    lg = Ledger(tmp / "l.jsonl", 5.0)

    class HalfBilled(Fake):
        def run(self, image):
            raise EngineError("Bedrock AccessDenied after Textract", cost_usd=0.0018)

    st = run(tmp / "r", imgs, samples[:1], [HalfBilled()], ["raw"], lg)
    assert st.failed == 1 and lg.total() == pytest.approx(0.0018)
    resp = json.loads((tmp / "r/responses/fake/raw/a.json").read_text(encoding="utf-8"))
    assert resp["ok"] is False and resp["cost_usd"] == pytest.approx(0.0018)


def test_spend_recorded_even_if_writing_outputs_crashes(data, monkeypatch):
    import pathlib

    tmp, imgs, samples = data
    lg = Ledger(tmp / "l.jsonl", 5.0)
    real_write = pathlib.Path.write_text

    def failing_write(self, *args, **kwargs):
        if self.suffix == ".md":
            raise OSError("disk full")
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", failing_write)
    with pytest.raises(OSError):
        run(tmp / "r", imgs, samples[:1], [Fake()], ["raw"], lg)
    assert lg.total() == pytest.approx(0.01)
    assert not (tmp / "r/responses/fake/raw/a.json").exists()  # resume will redo it
