"""Spelling normalization (spec §4.3): the prompt, the reply parser, the guard and the project-name rules."""

import re
from dataclasses import dataclass
from pathlib import Path

from ingest.board import CHECKBOX_RE, parse_board

PROMPT_VERSION = "normalize-v1"
PROMPT = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
PROJECT_RE = re.compile(r"^Project:\s*(.+?)\s*$")
FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)\n?```$", re.DOTALL)


class NormalizationError(ValueError):
    """The reply doesn't follow the `Project:` / `---` / Markdown format."""


@dataclass(frozen=True)
class Normalized:
    chosen: str
    project_name: str | None
    rejected: bool


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "(none yet)"


def build_prompt(verbatim: str, project_names: list[str], todo_texts: list[str]) -> str:
    return (
        PROMPT.replace("{{PROJECTS}}", _bullets(project_names))
        .replace("{{TODOS}}", _bullets(todo_texts))
        .replace("{{TRANSCRIPT}}", verbatim.strip())
    )


def parse_response(text: str) -> tuple[str | None, str]:
    lines = text.strip().splitlines()
    if len(lines) < 3 or not (m := PROJECT_RE.match(lines[0])) or lines[1].strip() != "---":
        raise NormalizationError(f"unexpected reply start: {text[:80]!r}")
    body = "\n".join(lines[2:]).strip()
    if fenced := FENCE_RE.match(body):
        body = fenced.group(1).strip()
    project = m.group(1)
    return (None if project.lower() == "none" else project), body


def _checkbox_states(md: str) -> list[bool]:
    return [m.group(1) != " " for line in md.splitlines() if (m := CHECKBOX_RE.match(line))]


def _line_count(md: str) -> int:
    return sum(1 for line in md.splitlines() if line.strip())


def guard_ok(verbatim: str, normalized: str) -> bool:
    return (
        _checkbox_states(verbatim) == _checkbox_states(normalized)
        and _line_count(verbatim) == _line_count(normalized)
    )


def project_name(verbatim: str, chosen: str, nova_project: str | None) -> str | None:
    if parse_board(verbatim).untitled:
        return None
    before, colon, _ = parse_board(chosen).title.partition(":")
    if colon and before.strip():
        return before.strip()
    return nova_project


def decide(verbatim: str, reply: str | None) -> Normalized:
    if reply is not None:
        try:
            nova_project, body = parse_response(reply)
        except NormalizationError:
            pass
        else:
            if guard_ok(verbatim, body):
                return Normalized(body, project_name(verbatim, body, nova_project), False)
    return Normalized(verbatim, project_name(verbatim, verbatim, None), True)
