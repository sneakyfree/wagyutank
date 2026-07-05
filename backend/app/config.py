from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./wagyutank.db"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 43200  # 30 days

    frontend_origin: str = "http://localhost:3000"

    # Stripe (real keys come from the lockbox / env, never committed)
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    platform_fee_bps: int = 0  # platform take-rate in basis points; 0 = free at launch

    # AI
    vision_api_key: str = ""
    ad_copy_api_key: str = ""


settings = Settings()
