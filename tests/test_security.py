import jwt
import pytest

from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_the_plain_password():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert hashed.startswith("$2b$")


def test_verify_password_accepts_correct_and_rejects_wrong():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_same_password_gives_different_hashes():
    assert hash_password("secret123") != hash_password("secret123")


def test_token_round_trip():
    token = create_access_token(42)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"


def test_tampered_token_is_rejected():
    token = create_access_token(42)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token + "x")