import pytest

from whiteborag_offline.keys import MissingKeyError, api_key

ENV = "OPENROUTER_API_KEY"


def test_env_wins_over_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"{ENV}=from-file\n", encoding="utf-8")
    monkeypatch.setenv(ENV, "from-env")
    assert api_key(ENV, tmp_path / ".env") == "from-env"


def test_dotenv_used_when_env_missing(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"# the OpenRouter key\n\n{ENV}=abc\nOTHER=x\n", encoding="utf-8")
    monkeypatch.delenv(ENV, raising=False)
    assert api_key(ENV, tmp_path / ".env") == "abc"


def test_api_key_missing_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    with pytest.raises(MissingKeyError, match=ENV):
        api_key(ENV, tmp_path / ".env")
