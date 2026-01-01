# Configuration - to be filled from config_py.txt

import os
from typing import Optional
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application configuration settings."""

    # API Keys & Tokens
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN", None)

    # Server Configuration
    API_TITLE: str = "GitHub Issue Analyzer API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "AI-powered GitHub issue analysis using Google Gemini"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    RELOAD: bool = os.getenv("RELOAD", "true").lower() == "true"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # CORS Configuration
    ALLOWED_ORIGINS: list = [
        "http://localhost:8501",
        "http://localhost:3000",
        "http://0.0.0.0:8501",
        os.getenv("FRONTEND_URL", "http://localhost:8501"),
    ]

    # Cache Configuration
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "false").lower() == "true"
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "86400"))  # 24 hours

    # GitHub API Configuration
    GITHUB_API_BASE_URL: str = "https://api.github.com"
    GITHUB_API_TIMEOUT: int = 10
    GITHUB_RATE_LIMIT_THRESHOLD: int = 100  # Warn if below this

    # LLM Configuration
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    LLM_TIMEOUT: int = 30

    # Content Limits
    MAX_ISSUE_BODY_LENGTH: int = 8000  # Characters
    MAX_COMMENTS_COUNT: int = 20
    MAX_COMMENT_LENGTH: int = 1000  # Characters per comment

    # Request Configuration
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 1

    # Database Configuration (SQLite for simplicity)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./github_analyzer.db"
    )

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Feature Flags
    ENABLE_ANALYTICS: bool = True
    ENABLE_BATCH_PROCESSING: bool = True
    ENABLE_EXPORT: bool = True

    def validate(self) -> bool:
        """Validate required configuration."""
        if not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        return True


@lru_cache()
def get_settings() -> Settings:
    """Get application settings (cached singleton)."""
    return Settings()


# Export settings instance
settings = get_settings()