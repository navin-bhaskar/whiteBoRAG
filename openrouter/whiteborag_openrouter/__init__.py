"""WhiteBoRAG OpenRouter: the offline server, queue and storage, with the models on OpenRouter."""

import sys
from pathlib import Path

OPENROUTER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = OPENROUTER_DIR.parent

# whiteborag_offline has no build-system either; importing it puts the shared ingest and query packages on sys.path.
if str(REPO_DIR / "offline") not in sys.path:
    sys.path.insert(0, str(REPO_DIR / "offline"))
