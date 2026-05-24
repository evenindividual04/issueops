import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application configuration — loaded from environment variables."""

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN", None)

    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    MIN_CONFIDENCE: float = float(os.getenv("MIN_CONFIDENCE", "0.75"))

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def validate(self) -> bool:
        if not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        return True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
