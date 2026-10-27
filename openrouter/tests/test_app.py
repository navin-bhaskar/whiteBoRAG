import dataclasses

from fastapi.testclient import TestClient

from whiteborag_openrouter import OPENROUTER_DIR
from whiteborag_offline.config import load_config
from whiteborag_offline.deps import open_runtime
from whiteborag_offline.llm import Completion
from whiteborag_offline.server import create_app

EXAMPLE = OPENROUTER_DIR / "config.example.toml"


class FakeClient:
    def chat(self, model, prompt, image=None, max_tokens=1500):
        return Completion("reply", False, 0.1)

    def embed(self, model, text):
        return [0.1] * 8


def test_example_config_points_at_openrouter():
    cfg = load_config(EXAMPLE)
    assert cfg.llm_base_url == "https://openrouter.ai/api/v1"
    assert cfg.data_dir == OPENROUTER_DIR / "data"
    assert cfg.models.project_pick == "model"
    assert cfg.api_key_env == "OPENROUTER_API_KEY"


def test_app_starts_with_fake_client(tmp_path):
    cfg = dataclasses.replace(load_config(EXAMPLE), data_dir=tmp_path)
    rt = open_runtime(cfg, client=FakeClient(), vectors_path=":memory:")
    with TestClient(create_app(cfg, rt, start_worker=False)) as client:
        assert client.get("/health").status_code == 200
