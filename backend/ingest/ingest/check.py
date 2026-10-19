"""The photo check (prompt check-v1): is the whole board readable, before anything is transcribed?"""

import re

PROMPT_VERSION = "check-v1"

# Anything that does not start with UNUSABLE counts as usable, so an odd reply never deletes a real board.
UNUSABLE_RE = re.compile(r"^[`\s]*UNUSABLE\b[\s:\-–—]*(.*?)[`\s]*$", re.IGNORECASE | re.DOTALL)


def unusable_reason(reply: str | None) -> str | None:
    """The model's reason when it judged the photo unusable, else None."""
    match = UNUSABLE_RE.match(reply or "")
    return match.group(1) if match else None
