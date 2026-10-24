"""WhiteBoRAG offline: the AWS pipeline's shared logic with local models and storage."""

import sys
from pathlib import Path

OFFLINE_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = OFFLINE_DIR.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# The ingest and query projects have no build-system, so they can't be path dependencies.
for _shared in (REPO_DIR / "aws" / "backend" / "query", REPO_DIR / "aws" / "backend" / "ingest"):
    if str(_shared) not in sys.path:
        sys.path.insert(0, str(_shared))
