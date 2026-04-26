from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_NEWS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/ainews.db")
    seed_path: Path = Path("./helm/ai-news/templates/configmap-seed.yaml")
    embed_allowed_origins: str = "https://hankel.ai,https://www.hankel.ai"
    log_level: str = "INFO"
    static_dir: Path = Path(__file__).parent / "static"
    llm_provider: str = "ollama"
    llm_model: str = "llama3.2"
    llm_base_url: str = ""
    llm_api_key: str = ""

    # -- embed --

    @property
    def embed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.embed_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
