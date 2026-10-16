"""A prompt-v2 transcript → title, sections, todos and diagram edges."""

import re
from dataclasses import dataclass

# Same grammar as eval/harness/harness/dataset.py, so ingestion reads boards the way the eval scored them.
EDGE_RE = re.compile(r'^\s*-\s*(.+?)\s*(?:→|->|=>)\s*(.+?)(?:\s*,\s*labell?ed\s*"(.+?)")?\s*$')
CHECKBOX_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.+?)\s*$")
ANNOTATION_RE = re.compile(r"\s*\([^)]*\)")
UNTITLED = "(untitled)"


@dataclass(frozen=True)
class Todo:
    text: str
    checked: bool


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    label: str | None


@dataclass(frozen=True)
class Section:
    kind: str  # "diagram", "todos" or "notes"
    text: str


@dataclass
class Board:
    title: str
    untitled: bool
    descriptive_name: str | None
    sections: list[Section]
    todos: list[Todo]
    edges: list[Edge]


def _node(name: str) -> str:
    return ANNOTATION_RE.sub("", name).strip()


def _blocks(lines: list[str]) -> list[list[str]]:
    """Split on `## ` headings; lines before the first heading form one headless block."""
    blocks: list[list[str]] = [[]]
    for line in lines:
        if line.startswith("## "):
            blocks.append([])
        blocks[-1].append(line)
    return [b for b in blocks if any(line.strip() for line in b)]


def _kind(block: list[str]) -> str:
    if block[0].strip() == "## Diagram":
        return "diagram"
    if any(CHECKBOX_RE.match(line) for line in block):
        return "todos"
    return "notes"


def _edges(block: list[str]) -> list[Edge]:
    edges, in_edges = [], False
    for line in block:
        if line.strip() == "Edges:":
            in_edges = True
        elif in_edges and (edge := EDGE_RE.match(line)):
            edges.append(Edge(_node(edge.group(1)), _node(edge.group(2)), edge.group(3)))
    return edges


def parse_board(md: str) -> Board:
    lines = md.splitlines()
    title, body = "", lines
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title, body = line[2:].strip(), lines[i + 1:]
            break
    untitled = UNTITLED in title
    descriptive_name = title.replace(UNTITLED, "").strip() if untitled else None

    sections, edges = [], []
    for block in _blocks(body):
        kind = _kind(block)
        sections.append(Section(kind, "\n".join(block).strip()))
        if kind == "diagram":
            edges.extend(_edges(block))
    todos = [Todo(m.group(2), m.group(1) != " ") for line in body if (m := CHECKBOX_RE.match(line))]
    return Board(title, untitled, descriptive_name, sections, todos, edges)
