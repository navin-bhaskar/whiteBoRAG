"""WhiteBorag ingest Lambda: turn each capture into transcripts, projects, todos and vectors."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"
