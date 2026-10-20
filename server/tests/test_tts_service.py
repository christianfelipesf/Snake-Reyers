from cobrinha_server.services.tts_service import (
    _restore_common_pt_br_accents,
    prepare_tts_input,
)


def test_restore_common_pt_br_accents_fixes_apple_words():
    assert _restore_common_pt_br_accents("maca") == "maçã"
    assert _restore_common_pt_br_accents("macas") == "maçãs"
    assert _restore_common_pt_br_accents("maça") == "maçã"
    assert _restore_common_pt_br_accents("maças") == "maçãs"
    assert _restore_common_pt_br_accents("Maca") == "Maçã"
    assert _restore_common_pt_br_accents("MACA") == "MAÇÃ"


def test_prepare_tts_input_uses_apple_pronunciation():
    assert prepare_tts_input("A maca fugiu.") == "A massã fugiu"
    assert prepare_tts_input("duas macas no mapa") == "duas massãs no mapa"
