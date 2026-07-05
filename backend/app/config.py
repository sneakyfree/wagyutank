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

    # AI — product API keys (Anthropic sk-ant-api03-…), NOT the Max-plan OAuth token.
    vision_api_key: str = ""       # Job 1: pedigree extraction from screenshots
    ad_copy_api_key: str = ""      # Job 2: ad copy + translation
    vision_model: str = "claude-sonnet-5"
    ad_copy_model: str = "claude-haiku-4-5-20251001"


settings = Settings()
