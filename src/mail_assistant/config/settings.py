from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MAIL_ASSISTANT_",
        extra="ignore",
    )

    data_dir: Path = Field(
        default=Path.home() / ".mail_assistant",
        description="Directory for local SQLite DB, OAuth token cache, and logs.",
    )

    google_client_secret_file: Path = Field(
        default=Path.home() / ".mail_assistant" / "google_client_secret.json",
        description="OAuth desktop-app client secret downloaded from Google Cloud Console.",
    )

    anthropic_api_key: str = Field(
        default="",
        description="Claude API key. Loaded from MAIL_ASSISTANT_ANTHROPIC_API_KEY or .env.",
    )

    no_reply_threshold_days: int = Field(
        default=4,
        description="Flag outbound emails awaiting a reply after this many days.",
    )

    sync_window_days: int = Field(
        default=30,
        description="Default lookback window for `mail-assistant sync init`.",
    )

    web_host: str = "127.0.0.1"
    web_port: int = 8765

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mail.db"


def load_settings() -> Settings:
    return Settings()
