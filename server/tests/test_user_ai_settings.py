import os

from cobrinha_server.services import user_ai_settings


def test_user_key_is_saved_but_never_returned(tmp_path, monkeypatch):
    config_file = tmp_path / "social_text_ai.json"
    monkeypatch.setattr(user_ai_settings, "SOCIAL_TEXT_AI_CONFIG_FILE", config_file)
    monkeypatch.setattr(user_ai_settings.social_text_ai, "SOCIAL_TEXT_AI_CONFIG_FILE", config_file)

    status = user_ai_settings.update(
        {
            "api_key": "test-api-key-12345678901234567890",
            "enabled": True,
            "model": "gpt-4.1-mini",
        }
    )

    assert status["api_key_present"] is True
    assert "api_key" not in status
    assert "test-api-key" not in str(status)
    if os.name != "nt":
        assert config_file.stat().st_mode & 0o777 == 0o600


def test_user_key_can_be_removed(tmp_path, monkeypatch):
    config_file = tmp_path / "social_text_ai.json"
    monkeypatch.setattr(user_ai_settings, "SOCIAL_TEXT_AI_CONFIG_FILE", config_file)
    monkeypatch.setattr(user_ai_settings.social_text_ai, "SOCIAL_TEXT_AI_CONFIG_FILE", config_file)
    user_ai_settings.update(
        {
            "api_key": "test-api-key-12345678901234567890",
            "enabled": False,
        }
    )

    status = user_ai_settings.update(
        {"clear_key": True, "enabled": False}
    )

    assert status["api_key_present"] is False
