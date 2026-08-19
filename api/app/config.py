from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:////data/access_window.db"

    session_secret: str
    session_ttl_hours: int = 12

    stream_token_secret: str
    stream_token_ttl_seconds: int = 90

    invite_ttl_days: int = 7

    app_timezone: str = "America/Los_Angeles"

    mediamtx_api_url: str = "http://mediamtx:9997"
    mediamtx_hls_base_url: str

    pushover_app_token: str | None = None

    seed_super_admin_email: str | None = None
    seed_super_admin_password: str | None = None


settings = Settings()
