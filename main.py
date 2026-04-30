from config import get_settings
from llm_providers import OpenAISummarizer
from news_api import NewsApiClient
from summarizer import summarize_articles


def main() -> None:
    settings = get_settings()

    news_client = NewsApiClient(settings.news_api_key)
    llm_provider = OpenAISummarizer(settings.openai_api_key)

    articles = news_client.fetch_articles(
        query=settings.default_news_query,
        language=settings.default_language,
        page_size=settings.default_page_size,
    )
    summaries = summarize_articles(articles, llm_provider)

    for item in summaries:
        print(f"\n{item['title']}")
        print(item["url"])
        print(item["summary"])


if __name__ == "__main__":
    main()
