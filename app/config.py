from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    scheduler_enabled: bool = False  # true only in the running app, never in tests
    trust_proxy_headers: bool = False  # true only behind a proxy that sets X-Forwarded-For
    demo_mode: bool = False  # public demo: demo logins on the login page, data reset nightly

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_must_be_strong(cls, value: str) -> str:
        # Anyone who knows the secret can sign their own admin token, so refuse weak ones.
        if len(value) < 32 or "change-me" in value:
            raise ValueError(
                "JWT_SECRET must be at least 32 random characters. Generate one with: "
                'py -c "import secrets; print(secrets.token_hex(32))"'
            )
        return value

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql://", 1)
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


settings = Settings()
