"""Which project a question is about (spec §5.2). An uncertain name asks the user instead of guessing."""

import re
from collections.abc import Callable
from dataclasses import dataclass

from rapidfuzz import fuzz

from ingest.projects import canonical_key
from ingest.store import Project
from query.request import BadRequest, Turn

CONFIDENT = 85
CLOSE = 5
SUGGEST = 70
MAX_SUGGESTIONS = 3
# Partial scoring finds "crawler" in "tendercrawler", but it gives unrelated short names
# around 80 ("zebra" against "whiteborag"), so only a near-exact substring counts.
PARTIAL_MIN_LENGTH = 4
PARTIAL_COUNTS = 90
LEADING_THE_RE = re.compile(r"^\s*the\s+", re.IGNORECASE)


@dataclass(frozen=True)
class Resolution:
    project: str | None
    how: str | None  # "named", "previous" or "latest"
    clarify: dict | None


def _score(name: str, candidate: str) -> float:
    score = fuzz.ratio(name, candidate)
    if len(name) >= PARTIAL_MIN_LENGTH and len(candidate) >= PARTIAL_MIN_LENGTH:
        partial = fuzz.partial_ratio(name, candidate)
        if partial >= PARTIAL_COUNTS:
            score = max(score, partial)
    return score


def rank_projects(name: str, known: dict[str, list[str]]) -> list[tuple[str, float]]:
    """Every known project scored against `name` by its best key or alias, best first."""
    key = canonical_key(LEADING_THE_RE.sub("", name))
    scored = [
        (project, max(_score(key, c) for c in [project, *map(canonical_key, aliases)]))
        for project, aliases in known.items()
    ]
    return sorted(scored, key=lambda s: s[1], reverse=True)


def _options(keys: list[str], by_key: dict[str, Project]) -> list[dict]:
    return [{"key": k, "display_name": by_key[k].display_name} for k in keys]


def _by_name(name: str, intent: str, by_key: dict[str, Project]) -> Resolution:
    ranked = rank_projects(name, {k: list(p.aliases) for k, p in by_key.items()})
    if not ranked:
        return Resolution(None, None, None)
    best = ranked[0][1]
    close = [k for k, s in ranked if s >= CONFIDENT and best - s <= CLOSE]
    if len(close) == 1:
        return Resolution(close[0], "named", None)
    # A search filters by project only on a confident match; otherwise it searches every board.
    if intent == "search":
        return Resolution(None, None, None)
    if close:
        clarify = {"message": "Which project did you mean?", "options": _options(close, by_key)}
    elif best >= SUGGEST:
        near = [k for k, s in ranked if s >= SUGGEST][:MAX_SUGGESTIONS]
        clarify = {"message": f'Did you mean {" or ".join(by_key[k].display_name for k in near)}?',
                   "options": _options(near, by_key)}
    else:
        everything = sorted(by_key, key=lambda k: by_key[k].display_name.lower())
        clarify = {"message": f'I don\'t know a project called "{name}". Which one did you mean?',
                   "options": _options(everything, by_key)}
    return Resolution(None, None, clarify)


def resolve(
    name: str | None,
    intent: str,
    requested: str | None,
    history: list[Turn],
    projects: list[Project],
    latest_project: Callable[[], str | None],
    follow_up: bool = False,
) -> Resolution:
    by_key = {p.key: p for p in projects}

    # A clarify pick carries the key itself, so it never goes through name matching again.
    if requested is not None:
        if requested not in by_key:
            raise BadRequest(f"unknown project {requested!r}")
        return Resolution(requested, "named", None)

    if name and name.strip():
        return _by_name(name.strip(), intent, by_key)

    # A project renamed or merged since the last turn no longer exists; resolve as if there were none.
    previous = history[-1].understood.get("project") if history else None
    if isinstance(previous, str) and previous in by_key and (follow_up or intent != "search"):
        return Resolution(previous, "previous", None)

    if intent == "search":
        return Resolution(None, None, None)

    latest = latest_project()
    if latest in by_key:
        return Resolution(latest, "latest", None)
    return Resolution(None, None, None)
