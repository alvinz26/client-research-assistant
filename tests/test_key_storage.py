"""Saving the key from the page must not disturb the other settings in .env."""
import os

from research.config import KEY_NAME, remove_api_key, save_api_key


def test_save_and_remove_key_keep_other_settings(tmp_path, monkeypatch):
    monkeypatch.delenv(KEY_NAME, raising=False)
    (tmp_path / ".env.example").write_text("ANTHROPIC_API_KEY=\nMAX_SEARCHES=8\n", encoding="utf-8")
    env = tmp_path / ".env"

    save_api_key("sk-ant-first", env)  # no .env yet: created from the example
    save_api_key("sk-ant-second", env)  # replaced, not duplicated
    lines = env.read_text(encoding="utf-8").splitlines()
    assert lines.count("ANTHROPIC_API_KEY=sk-ant-second") == 1
    assert not any("sk-ant-first" in ln for ln in lines)
    assert "MAX_SEARCHES=8" in lines
    assert os.environ[KEY_NAME] == "sk-ant-second"

    remove_api_key(env)
    text = env.read_text(encoding="utf-8")
    assert "sk-ant" not in text and "MAX_SEARCHES=8" in text
    assert KEY_NAME not in os.environ
