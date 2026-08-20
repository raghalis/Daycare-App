from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:////data/access_window.db"

    session_secret: str
    session_ttl_hours: int = 12
    # Browsers drop Secure cookies over plain HTTP. Set to false only while
    # testing straight against the container, with no TLS in front of it yet.
    session_cookie_secure: bool = True

    stream_token_secret: str
    # Not the thing enforcing the cutoff (evaluate_access() re-runs against
    # the real schedule on every MediaMTX segment request regardless of this)
    # - it only bounds how long a captured token could be replayed. Long
    # enough here means the viewer never needs a disruptive mid-play reload.
    stream_token_ttl_seconds: int = 3600

    invite_ttl_days: int = 7

    app_timezone: str = "America/Los_Angeles"

    mediamtx_api_url: str = "http://access-window-mediamtx:9997"
    mediamtx_hls_base_url: str

    pushover_app_token: str | None = None

    seed_super_admin_email: str | None = None
    seed_super_admin_password: str | None = None


settings = Settings()
