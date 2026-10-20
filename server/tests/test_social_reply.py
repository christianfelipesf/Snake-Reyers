from cobrinha_server.services import social_text_ai
from cobrinha_server.services.social_reply import (
    build_gift_reply,
    build_main_reply,
)


def _enable_test_ai(monkeypatch) -> None:
    monkeypatch.setattr(
        social_text_ai,
        "load_config",
        lambda: {
            "enabled": True,
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "timeout": 2.0,
            "max_chars": 150,
        },
    )


def _reply_result(monkeypatch, comment: str) -> tuple[str, str]:
    _enable_test_ai(monkeypatch)
    calls = []

    def fake_ai(payload):
        calls.append(payload)
        return "IA_CHAMADA"

    reply = build_main_reply(
        display_name="Ana",
        comment=comment,
        user_key="user-1",
        ai_transport=fake_ai,
    )

    return "ia" if calls else "local", reply


def test_simple_greetings_use_local_reply(monkeypatch):
    for comment in (
        "oi",
        "Oi",
        "oii",
        "oiii",
        "olá",
        "ola",
        "olaa",
        "bom dia",
        "bom diaa",
        "boa tarde",
        "boa noite",
        "tudo bem",
        "td bem",
        "como vai",
        "e ai",
        "eai",
        "eae",
        "opa",
        "salve",
    ):
        source, reply = _reply_result(monkeypatch, comment)
        assert source == "local"
        assert "Cobrinha" not in reply
        assert "arena" not in reply


def test_non_greeting_uses_ai_reply(monkeypatch):
    source, _reply = _reply_result(monkeypatch, "qual seu nome?")
    assert source == "ia"


def test_gift_reply_uses_ai_reply(monkeypatch):
    _enable_test_ai(monkeypatch)
    calls = []

    def fake_ai(payload):
        calls.append(payload)
        return "Ana, valeu pela Rose. Minha cauda ate ficou elegante."

    reply = build_gift_reply(
        display_name="Ana",
        gift_name="Rose",
        gift_count=2,
        user_key="user-1",
        ai_transport=fake_ai,
    )

    assert calls
    assert reply == "Ana, valeu pela Rose. Minha cauda ate ficou elegante."
    assert "Evento do sistema: presente recebido" in calls[0]["prompt"]
    assert "Presente:Rose" in calls[0]["prompt"]
    assert "Quantidade:2" in calls[0]["prompt"]
