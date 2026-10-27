"""API keys from the environment, falling back to the repo-root .env (git-ignored). Never logged."""

import os
from pathlib import Path

from whiteborag_offline import REPO_DIR


class MissingKeyError(ValueError):
    """Neither the environment nor .env has the key."""


def _from_dotenv(name: str, dotenv: Path) -> str | None:
    if not dotenv.is_file():
        return None
    for line in dotenv.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key.strip() == name:
            return value.strip().strip('"').strip("'") or None
    return None


def api_key(env_name: str, dotenv: Path = REPO_DIR / ".env") -> str:
    key = os.environ.get(env_name) or _from_dotenv(env_name, dotenv)
    if not key:
        raise MissingKeyError(f"{env_name} is not set: put it in the environment or in {dotenv}")
    return key
