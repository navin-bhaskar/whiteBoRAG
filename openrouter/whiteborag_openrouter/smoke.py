"""Check OpenRouter: list its models, flag configured ones it lacks, then ask the text model one short question.

Run: uv run --directory openrouter python -m whiteborag_openrouter.smoke
"""

from whiteborag_openrouter.server import CONFIG, EXAMPLE_CONFIG
from whiteborag_offline.config import load_config
from whiteborag_offline.keys import api_key
from whiteborag_offline.llm import LlmClient, LlmError


def main() -> int:
    cfg = load_config(CONFIG, EXAMPLE_CONFIG)
    client = LlmClient(cfg.llm_base_url, timeout_s=120, api_key=api_key(cfg.api_key_env))
    try:
        ids = set(client.models()) | set(client.models("embeddings/models"))
        print(f"{cfg.llm_base_url} lists {len(ids)} models")
        wanted = {m for m in (cfg.models.check, cfg.models.transcribe, cfg.models.ocr, cfg.models.text,
                              cfg.models.embed) if m}
        for model_id in sorted(wanted):
            print(f"  {'ok     ' if model_id in ids else 'MISSING'} {model_id}")
        reply = client.chat(cfg.models.text, "Reply with one word: ready?", max_tokens=20)
    except LlmError as exc:
        print(f"OpenRouter check failed: {exc}")
        return 1
    print(f"{cfg.models.text}: {reply.text!r} ({reply.latency_s:.1f}s, ${reply.cost_usd:.6f})")
    return 0 if wanted <= ids else 1


if __name__ == "__main__":
    raise SystemExit(main())
