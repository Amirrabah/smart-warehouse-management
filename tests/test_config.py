import pytest
from pydantic import ValidationError

from app.config import Settings

DB = "postgresql://u:p@localhost:5432/db"
STRONG = "x" * 32


def make(**overrides) -> Settings:
    values = {"database_url": DB, "jwt_secret": STRONG} | overrides
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("secret", ["", "change-me", "x" * 31])
def test_short_jwt_secret_is_refused(secret):
    # Anyone who guesses the secret can sign their own admin token.
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make(jwt_secret=secret)


def test_32_character_secret_is_accepted():
    assert make(jwt_secret="x" * 32).jwt_secret == "x" * 32


def test_placeholder_secret_is_refused_even_if_long():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make(jwt_secret="change-me-change-me-change-me-change-me")


def test_railway_database_url_gets_psycopg_driver():
    assert make(database_url="postgres://u:p@h:5432/db").database_url.startswith(
        "postgresql+psycopg://"
    )


def test_demo_mode_is_off_by_default():
    assert make().demo_mode is False
