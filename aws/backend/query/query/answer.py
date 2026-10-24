"""The answer prompt (spec §5.4): the evidence boards, numbered with their dates, and the rules for using only them."""

from datetime import date
from pathlib import Path

from query.evidence import Board
from query.request import Turn
from query.understand import Intent

PROMPT_VERSION = "answer-v2"
PROMPT = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
FALLBACK = "Here are the boards I found."
MAX_TOKENS = 800
HISTORY_TURNS = 3

HOW = {
    "previous": "carried over from the previous question",
    "latest": "the project of the user's most recent board, because the question named none",
}


def nice_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d:%b} {d.year}"


def _project(intent: Intent, project: dict | None, how: str | None) -> str:
    if project is None:
        if intent.project_name:
            return (
                f'The question names "{intent.project_name}", which isn\'t a known project, so all boards were '
                "searched. Say so in your first sentence."
            )
        return "The evidence may come from several projects or from untitled boards."
    if how in HOW:
        return (
            f"Project: {project['display_name']} ({HOW[how]}). Say which project in your first sentence, "
            f'for example "Using {project["display_name"]}, your most recent board."'
        )
    return f"Project: {project['display_name']}."


def _history(history: list[Turn]) -> str:
    turns = history[-HISTORY_TURNS:]
    return "\n".join(f"Q: {t.question}\nA: {t.answer or '(no answer)'}" for t in turns) or "(none)"


def _edge(e: dict) -> str:
    return f"{e['src']} → {e['dst']}" + (f', labelled "{e["label"]}"' if e.get("label") else "")


def _board(n: int, b: Board) -> str:
    parts = [f"[{n}] The {nice_date(b.date)} board ({b.section}):", b.text.strip()]
    if b.todos is not None:
        lines = [
            ("☑ " if t["checked"] else "☐ ")
            + t["text"]
            + (f" (done since, on {nice_date(t['done_since'])})" if t["done_since"] else "")
            for t in b.todos
        ]
        parts.append("Todos as on this board:\n" + "\n".join(lines))
    if b.diff is not None:
        added = "\n".join(f"+ {_edge(e)}" for e in b.diff["added"]) or "(none)"
        removed = "\n".join(f"- {_edge(e)}" for e in b.diff["removed"]) or "(none)"
        parts.append(f"Edges added since the previous board:\n{added}\nEdges removed since the previous board:\n{removed}")
    return "\n\n".join(parts)


def build_prompt(
    question: str, intent: Intent, project: dict | None, how: str | None, history: list[Turn], boards: list[Board]
) -> str:
    return (
        PROMPT.replace("{{PROJECT}}", _project(intent, project, how))
        .replace("{{HISTORY}}", _history(history))
        .replace("{{EVIDENCE}}", "\n\n".join(_board(n, b) for n, b in enumerate(boards, 1)))
        .replace("{{QUESTION}}", question.strip())
    )
