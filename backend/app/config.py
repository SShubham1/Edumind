from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables / .env."""

    app_name: str = "EduMind API"
    environment: str = "development"
    database_url: str = "sqlite:///./edumind.db"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Simple Bayesian Knowledge Tracing defaults. A later version can fit these
    # per topic from historical data (see services/mastery.py).
    bkt_prior: float = 0.30
    bkt_learn: float = 0.18
    bkt_guess: float = 0.20
    bkt_slip: float = 0.10

    # Recommendation weights for R(t) = w1(1-M) + w2*F + w3*D + w4*W
    rec_weight_mastery: float = 0.45
    rec_weight_revision: float = 0.20
    rec_weight_difficulty: float = 0.15
    rec_weight_weakness: float = 0.20
    revision_window_days: float = 14.0

    # Server-side LLM configuration. Never expose this key to the browser.
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0
    # Quiz generation is longer than a plan or a card. Give it its own timeout
    # and token budget so reasoning-capable models have room to finish.
    llm_quiz_timeout_seconds: float = 90.0
    llm_quiz_max_tokens: int = 4000

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
