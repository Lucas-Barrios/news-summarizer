from summarizer import build_article_text, summarize_articles


class FakeProvider:
    def summarize(self, text: str) -> str:
        return f"summary: {text[:10]}"


def test_build_article_text_joins_available_fields() -> None:
    article = {
        "title": "Headline",
        "description": "Short description",
        "content": "Full content",
    }

    assert build_article_text(article) == "Headline\n\nShort description\n\nFull content"


def test_summarize_articles_returns_summary_payload() -> None:
    articles = [{"title": "Headline", "url": "https://example.com", "content": "News body"}]

    result = summarize_articles(articles, FakeProvider())

    assert result == [
        {
            "title": "Headline",
            "url": "https://example.com",
            "summary": "summary: Headline\n\nN",
        }
    ]
