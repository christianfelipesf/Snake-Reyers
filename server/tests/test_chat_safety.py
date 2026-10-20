from cobrinha_server.services.chat_safety import comment_is_eligible


def test_comment_rejects_numbers():
    assert comment_is_eligible("cobra 123") is False
    assert comment_is_eligible("salve 7") is False


def test_comment_rejects_weird_characters():
    assert comment_is_eligible("oi cobra 😁") is False
    assert comment_is_eligible("oi #cobra") is False
    assert comment_is_eligible("cobra ★ linda") is False


def test_comment_rejects_same_word_three_times():
    assert comment_is_eligible("oi oi oi") is False
    assert comment_is_eligible("cobra vai cobra vai cobra") is False
    assert comment_is_eligible("vai vai vai cobra") is False


def test_comment_accepts_portuguese_letters_and_common_punctuation():
    assert comment_is_eligible("oi, cobrinha!") is True
    assert comment_is_eligible("voce esta bem?") is True
    assert comment_is_eligible("maçã não é fácil.") is True
