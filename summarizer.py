from typing import Protocol


class SummarizerProvider(Protocol):
    def summarize(self, text: str) -> str:
        pass


def build_article_text(article: dict) -> str:
    title = article.get("title") or ""
    description = article.get("description") or ""
    content = article.get("content") or ""
    return "\n\n".join(part for part in [title, description, content] if part)


def summarize_articles(
    articles: list[dict],
    provider: SummarizerProvider,
) -> list[dict[str, str]]:
    summaries = []

    for article in articles:
        article_text = build_article_text(article)
        if not article_text:
            continue

        summaries.append(
            {
                "title": article.get("title") or "Untitled",
                "url": article.get("url") or "",
                "summary": provider.summarize(article_text),
            }
        )

    return summaries
