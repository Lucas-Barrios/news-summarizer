"""Configuration management for news summarizer."""
import os

from dotenv import load_dotenv


# Load environment variables
load_dotenv()


class Config:
    """Application configuration."""

    # API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    NEWS_API_KEY = os.getenv("NEWS_API_KEY")

    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    # API Configuration
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

    # Models
    OPENAI_MODEL = "gpt-4o-mini"
    ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

    # Cost Control
    DAILY_BUDGET = float(os.getenv("DAILY_BUDGET", "5.00"))
    CACHE_DB_PATH = os.getenv("CACHE_DB_PATH", "article_cache.sqlite3")
    PIPELINE_LOCK_FILE = os.getenv("PIPELINE_LOCK_FILE", "pipeline.lock")
    PIPELINE_LOG_FILE = os.getenv("PIPELINE_LOG_FILE", "pipeline.log")
    SCHEDULE_CATEGORY = os.getenv("SCHEDULE_CATEGORY", "technology")
    SCHEDULE_ARTICLE_LIMIT = int(os.getenv("SCHEDULE_ARTICLE_LIMIT", "5"))
    SCHEDULE_INTERVAL_MINUTES = int(os.getenv("SCHEDULE_INTERVAL_MINUTES", "60"))

    # Email Digest
    DIGEST_FROM_EMAIL = os.getenv("DIGEST_FROM_EMAIL", "")
    DIGEST_TO_EMAIL = os.getenv("DIGEST_TO_EMAIL", "")
    DIGEST_MAX_ARTICLES = int(os.getenv("DIGEST_MAX_ARTICLES", "5"))
    DIGEST_BASE_URL = os.getenv("DIGEST_BASE_URL", "http://localhost:8000")
    DIGEST_LOCK_FILE = os.getenv("DIGEST_LOCK_FILE", "digest.lock")
    DIGEST_SEND_HOUR_UTC = int(os.getenv("DIGEST_SEND_HOUR_UTC", "8"))
    EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")

    # Rate Limits (requests per minute)
    OPENAI_RPM = 500
    ANTHROPIC_RPM = 50
    NEWS_API_RPM = 100

    @classmethod
    def validate(cls):
        """Validate that required configuration is present."""
        required = [
            ("OPENAI_API_KEY", cls.OPENAI_API_KEY),
            ("ANTHROPIC_API_KEY", cls.ANTHROPIC_API_KEY),
            ("NEWS_API_KEY", cls.NEWS_API_KEY),
        ]

        missing = [name for name, value in required if not value]

        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

        print(f"✓ Configuration validated for {cls.ENVIRONMENT} environment")


# Validate on import
Config.validate()
