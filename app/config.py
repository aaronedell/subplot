"""Application configuration loaded from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ──────────────────────────────────────────────────────────────────
    SUBPLOT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    SUBPLOT_ENCRYPTION_KEY: str = ""
    DATABASE_URL: str = "sqlite:///./subplot.db"

    # ── JWT ──────────────────────────────────────────────────────────────────
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # ── Twilio ────────────────────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # ── SmolVM ────────────────────────────────────────────────────────────────
    SMOLVM_BINARY: str = "~/.local/bin/smolvm"
    SMOLVM_PACKED_AGENT: str = "./smolvm/subplot-agent"

    # ── AWS (production) ──────────────────────────────────────────────────────
    AWS_REGION: str = "us-east-1"
    AWS_PROFILE: str = "personal"
    PINPOINT_APP_ID: str = ""
    AGENTCORE_ENDPOINT: str = ""


settings = Settings()
