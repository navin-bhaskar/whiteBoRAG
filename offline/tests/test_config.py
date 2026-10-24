from whiteborag_offline import OFFLINE_DIR
from whiteborag_offline.config import load_config


def test_example_config_loads():
    cfg = load_config(OFFLINE_DIR / "config.example.toml")
    assert cfg.models.transcribe_mode in {"raw", "hybrid-text", "hybrid-vision"}
    assert cfg.data_dir.is_absolute()
    assert cfg.data_dir.name == "data"
    assert cfg.llm_base_url == "http://localhost:1234/v1"
    assert cfg.devices == {"change-me-device-key": "cam-01"}


def test_empty_ocr_is_none(tmp_path):
    text = (OFFLINE_DIR / "config.example.toml").read_text(encoding="utf-8")
    path = tmp_path / "c.toml"
    path.write_text(text, encoding="utf-8")
    cfg = load_config(path)
    assert cfg.models.ocr is None
    assert cfg.models.ocr_prompt is None


def test_missing_config_falls_back_to_example(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.port == 8080


def test_shared_packages_importable():
    import ingest.pipeline  # noqa: F401
    import query.handler  # noqa: F401
    import harness.runner  # noqa: F401
