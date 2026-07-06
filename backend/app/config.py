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

    # Advertising — free during launch to build the audience; flip to False to charge.
    ads_free_launch: bool = True

    # Super-admin bootstrap — accounts with these emails are promoted to admin on migrate.
    admin_emails: str = "grant@wagyutank.com,johnsmithkit05@gmail.com"

    # ---- AI providers (swappable via AI_PROVIDER; template fallback if unconfigured) ----
    ai_provider: str = "anthropic"   # anthropic | openai | windymind

    # Anthropic — pay-as-you-go PRODUCT key (sk-ant-api03-…), NOT the Max-plan OAuth token.
    # Haiku for BOTH jobs during testing so all Haiku spend is attributable to WagyuTank.
    anthropic_api_key: str = ""
    anthropic_vision_model: str = "claude-haiku-4-5"
    anthropic_adcopy_model: str = "claude-haiku-4-5"

    # OpenAI-compatible (also drives Windy Mind — just point base_url at its gateway)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_vision_model: str = "gpt-4o-mini"
    openai_adcopy_model: str = "gpt-4o-mini"

    # Windy Mind (Grant's free-compute gateway; OpenAI-compatible assumed). Spring-loaded.
    windymind_api_key: str = ""
    windymind_base_url: str = ""
    windymind_vision_model: str = ""
    windymind_adcopy_model: str = ""


settings = Settings()
