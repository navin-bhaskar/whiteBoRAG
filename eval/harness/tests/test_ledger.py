import json

import pytest

from harness.config import ModelConfig
from harness.ledger import BudgetExceeded, Ledger, bedrock_cost

LITE = ModelConfig("nova-lite", "p", 0.00006, 0.00024)


def test_bedrock_cost():
    assert bedrock_cost(LITE, 1000, 1000, 1.2) == pytest.approx(0.00036)


def test_ledger_total_and_record(tmp_path):
    lg = Ledger(tmp_path / "ledger.jsonl", 5.0)
    assert lg.total() == 0
    lg.record({"engine": "textract", "cost_usd": 0.0018})
    lg.record({"engine": "bedrock:nova-lite", "cost_usd": 0.0005})
    assert lg.total() == pytest.approx(0.0023)
    first = json.loads((tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "ts" in first


def test_total_survives_new_instance(tmp_path):
    Ledger(tmp_path / "l.jsonl", 5.0).record({"cost_usd": 1.0})
    assert Ledger(tmp_path / "l.jsonl", 5.0).total() == 1.0


def test_ensure_room(tmp_path):
    lg = Ledger(tmp_path / "l.jsonl", 5.0)
    lg.record({"cost_usd": 4.99})
    lg.ensure_room(0.01)
    with pytest.raises(BudgetExceeded):
        lg.ensure_room(0.02)
