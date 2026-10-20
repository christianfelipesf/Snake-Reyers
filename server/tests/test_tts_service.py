from cobrinha_server.services.tts_service import (
    _restore_common_pt_br_accents,
    prepare_tts_input,
    safe_tts_chunks,
)


def test_restore_common_pt_br_accents_fixes_apple_words():
    assert _restore_common_pt_br_accents("maca") == "maçã"
    assert _restore_common_pt_br_accents("macas") == "maçãs"
    assert _restore_common_pt_br_accents("maça") == "maçã"
    assert _restore_common_pt_br_accents("maças") == "maçãs"
    assert _restore_common_pt_br_accents("Maca") == "Maçã"
    assert _restore_common_pt_br_accents("MACA") == "MAÇÃ"


def test_prepare_tts_input_keeps_portuguese_spelling():
    assert prepare_tts_input("A maca fugiu.") == "A maçã fugiu"
    assert prepare_tts_input("duas macas no mapa") == "duas maçãs no mapa"


def test_safe_tts_chunks_splits_long_text():
    chunks = safe_tts_chunks(
        "uma frase curta. " * 40,
        max_chars=80,
    )

    assert len(chunks) > 1
    assert all(len(chunk) <= 81 for chunk in chunks)
