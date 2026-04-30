import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    news_api_key: str
    openai_api_key: str
    llm_provider: str
    default_news_query: str
    default_language: str
    default_page_size: int


def get_settings() -> Settings:
    return Settings(
        news_api_key=os.getenv("NEWS_API_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        default_news_query=os.getenv("DEFAULT_NEWS_QUERY", "technology"),
        default_language=os.getenv("DEFAULT_LANGUAGE", "en"),
        default_page_size=int(os.getenv("DEFAULT_PAGE_SIZE", "5")),
    )
