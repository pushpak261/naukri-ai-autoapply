import pytest

from libs.common.security import ENC_PREFIX, decrypt_value, encrypt_value


def test_round_trip():
    token = encrypt_value("hunter2")
    assert token.startswith(ENC_PREFIX)
    assert decrypt_value(token) == "hunter2"


def test_decrypt_non_encrypted_passthrough():
    assert decrypt_value("plain-text") == "plain-text"


def test_empty_value_passthrough():
    assert encrypt_value("") == ""
    assert decrypt_value("") == ""


def test_tampered_token_fails_safe():
    token = encrypt_value("secret")
    bad = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert decrypt_value(bad) == ""
