"""Check the model server: list its models, then ask the text model one short question.

Run: uv run --directory offline python -m whiteborag_offline.smoke
"""

from whiteborag_offline.config import load_config
from whiteborag_offline.llm import LlmClient, LlmError


def main() -> int:
    cfg = load_config()
    client = LlmClient(cfg.llm_base_url, timeout_s=300)
    try:
        ids = client.models()
        print(f"{cfg.llm_base_url} lists {len(ids)} models:")
        for model_id in ids:
            print(f"  {model_id}")
        reply = client.chat(cfg.models.text, "Reply with one word: ready?", max_tokens=20)
    except LlmError as exc:
        print(f"model server check failed: {exc}")
        return 1
    print(f"{cfg.models.text}: {reply.text!r} ({reply.latency_s:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
