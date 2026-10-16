"""Eval dataset: the manifest, and Markdown parsing shared by ground truth and LLM transcripts."""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

EDGE_RE = re.compile(r'^\s*-\s*(.+?)\s*(?:→|->|=>)\s*(.+?)(?:\s*,\s*labell?ed\s*"(.+?)")?\s*$')
CHECKBOX_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.+?)\s*$")
ANNOTATION_RE = re.compile(r"\s*\([^)]*\)")


@dataclass(frozen=True)
class Sample:
    image: str
    ground_truth: str
    environment: str
    notes: str


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    label: str | None


@dataclass(frozen=True)
class Checkbox:
    text: str
    checked: bool


@dataclass
class Parsed:
    edges: list[Edge] = field(default_factory=list)
    checkboxes: list[Checkbox] = field(default_factory=list)


def load_manifest(path: Path) -> list[Sample]:
    with open(path, encoding="utf-8", newline="") as f:
        return [
            Sample(row["image"], row["ground_truth"], row["environment"], row["notes"])
            for row in csv.DictReader(f)
        ]


def _node(name: str) -> str:
    return ANNOTATION_RE.sub("", name).strip()


def parse_markdown(md: str) -> Parsed:
    parsed = Parsed()
    in_edges = False
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_edges = False
        elif stripped == "Edges:":
            in_edges = True
            continue
        if box := CHECKBOX_RE.match(line):
            parsed.checkboxes.append(Checkbox(box.group(2), box.group(1) != " "))
        elif in_edges and (edge := EDGE_RE.match(line)):
            parsed.edges.append(Edge(_node(edge.group(1)), _node(edge.group(2)), edge.group(3)))
    return parsed
