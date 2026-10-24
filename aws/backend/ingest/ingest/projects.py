"""Project identity (spec §4.5): canonical keys, fuzzy matching and the display-name vote."""

import re
from collections import Counter

from rapidfuzz import fuzz

THRESHOLD = 85
NON_WORD_RE = re.compile(r"[\W_]+")


def canonical_key(name: str) -> str:
    return NON_WORD_RE.sub("", name.lower())


def match_project(name: str, known: dict[str, list[str]]) -> str | None:
    """The known project key whose key or aliases best match `name`, if the best ratio reaches THRESHOLD."""
    key = canonical_key(name)
    best, best_score = None, 0.0
    for project, aliases in known.items():
        score = max(fuzz.ratio(key, candidate) for candidate in [project, *map(canonical_key, aliases)])
        if score > best_score:
            best, best_score = project, score
    return best if best_score >= THRESHOLD else None


def summarize(links: list[tuple[str, str]], pinned: str | None) -> tuple[dict[str, int], str]:
    """(captured_at, spelling) links → spelling counts and the display name: pinned, else most common, ties to the latest."""
    aliases = Counter(spelling for _, spelling in links)
    latest = {spelling: max(at for at, s in links if s == spelling) for spelling in aliases}
    display = pinned or max(aliases, key=lambda s: (aliases[s], latest[s]))
    return dict(aliases), display
