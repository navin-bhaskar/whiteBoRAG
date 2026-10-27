"""The offline server with this folder's config: models on OpenRouter, data in openrouter/data.

Run: uv run --directory openrouter python -m whiteborag_openrouter.server
"""

from whiteborag_openrouter import OPENROUTER_DIR
from whiteborag_offline import server

CONFIG = OPENROUTER_DIR / "config.toml"
EXAMPLE_CONFIG = OPENROUTER_DIR / "config.example.toml"


def main() -> None:
    server.main(CONFIG, EXAMPLE_CONFIG)


if __name__ == "__main__":
    main()
