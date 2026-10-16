"""Cost of each billable call, and the append-only ledger that enforces the budget."""

import json
from datetime import UTC, datetime
from pathlib import Path

from harness.config import ModelConfig

# Float sums like 4.99 + 0.01 land a hair above 5.0; ignore differences below this.
EPSILON = 1e-9


class BudgetExceeded(Exception):
    pass


def bedrock_cost(model: ModelConfig, input_tokens: int, output_tokens: int, margin: float) -> float:
    return (input_tokens * model.input_per_1k + output_tokens * model.output_per_1k) / 1000 * margin


class Ledger:
    def __init__(self, path: Path, budget_usd: float):
        self.path = path
        self.budget_usd = budget_usd

    def total(self) -> float:
        if not self.path.exists():
            return 0.0
        with open(self.path, encoding="utf-8") as f:
            return sum(json.loads(line)["cost_usd"] for line in f if line.strip())

    def record(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), **entry}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str, ensure_ascii=False) + "\n")

    def ensure_room(self, cost: float) -> None:
        total = self.total()
        if total + cost > self.budget_usd + EPSILON:
            raise BudgetExceeded(
                f"budget cap reached: ledger total ${total:.4f} + next ${cost:.4f} "
                f"> cap ${self.budget_usd:.2f}"
            )
