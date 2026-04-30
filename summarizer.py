"""News summarizer with multi-provider support."""
import asyncio
import hashlib
import re
import sqlite3
from datetime import datetime, timezone

from config import Config
from news_api import NewsAPI
from llm_providers import LLMProviders


def normalize_article_text(text):
    """Normalize article text before hashing."""
    return re.sub(r"\s+", " ", text).strip()


def hash_article_text(text):
    """Create a deterministic hash for normalized article text."""
    normalized_text = normalize_article_text(text)
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


class ArticleCache:
    """SQLite cache for processed article summaries."""

    def __init__(self, db_path=None):
        self.db_path = db_path or Config.CACHE_DB_PATH
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=10)

    def _init_db(self):
        """Create the cache table if it does not exist."""
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS processed_articles (
                        article_hash TEXT PRIMARY KEY,
                        normalized_text TEXT NOT NULL,
                        title TEXT,
                        source TEXT,
                        url TEXT,
                        published_at TEXT,
                        summary TEXT NOT NULL,
                        sentiment TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
        except sqlite3.Error as e:
            print(f"  ! Cache initialization failed: {e}")

    def get(self, article_hash):
        """Return a cached article result by hash, or None."""
        try:
            with self._connect() as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    """
                    SELECT title, source, url, published_at, summary, sentiment
                    FROM processed_articles
                    WHERE article_hash = ?
                    """,
                    (article_hash,),
                ).fetchone()

            if row is None:
                return None

            return dict(row)
        except sqlite3.Error as e:
            print(f"  ! Cache lookup failed: {e}")
            return None

    def save(self, article_hash, normalized_text, result):
        """Save a processed article result."""
        now = datetime.now(timezone.utc).isoformat()

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO processed_articles (
                        article_hash,
                        normalized_text,
                        title,
                        source,
                        url,
                        published_at,
                        summary,
                        sentiment,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(article_hash) DO UPDATE SET
                        normalized_text = excluded.normalized_text,
                        title = excluded.title,
                        source = excluded.source,
                        url = excluded.url,
                        published_at = excluded.published_at,
                        summary = excluded.summary,
                        sentiment = excluded.sentiment,
                        updated_at = excluded.updated_at
                    """,
                    (
                        article_hash,
                        normalized_text,
                        result["title"],
                        result["source"],
                        result["url"],
                        result["published_at"],
                        result["summary"],
                        result["sentiment"],
                        now,
                        now,
                    ),
                )
        except sqlite3.Error as e:
            print(f"  ! Cache save failed: {e}")


class NewsSummarizer:
    """Summarize news articles using multiple LLM providers."""

    def __init__(self, cache_path=None):
        self.news_api = NewsAPI()
        self.llm_providers = LLMProviders()
        self.cache = ArticleCache(cache_path)

    def summarize_article(self, article):
        """
        Summarize a single article.

        Args:
            article: Article dictionary

        Returns:
            Dictionary with summary and sentiment
        """
        title = article.get("title") or ""
        description = article.get("description") or ""
        content = article.get("content") or ""

        print(f"\nProcessing: {title[:60]}...")

        # Prepare text for summarization
        article_text = f"""Title: {title}
Description: {description}
Content: {content[:500]}"""  # Limit content length
        normalized_text = normalize_article_text(article_text)
        article_hash = hash_article_text(normalized_text)

        cached_result = self.cache.get(article_hash)
        if cached_result:
            print("  ✓ Loaded summary from cache")
            return cached_result

        # Step 1: Summarize with OpenAI (fast and cheap)
        try:
            print("  → Summarizing with OpenAI...")
            summary_prompt = f"""Summarize this news article in 2-3 sentences:

{article_text}"""

            summary = self.llm_providers.ask_openai(summary_prompt)
            print("  ✓ Summary generated")

        except Exception as e:
            print(f"  ✗ OpenAI summarization failed: {e}")
            # Fallback to Anthropic for summary
            print("  → Falling back to Anthropic for summary...")
            summary = self.llm_providers.ask_anthropic(summary_prompt)

        # Step 2: Analyze sentiment with Anthropic (better at nuance)
        # Note: Using Anthropic for sentiment analysis is a suggestion. You can use any LLM provider
        # that works best for your needs. For a free alternative to test LLMs without payment,
        # consider Cohere: https://dashboard.cohere.com/api-keys
        try:
            print("  → Analyzing sentiment with Anthropic...")
            sentiment_prompt = f"""Analyze the sentiment of this text: "{summary}"

Provide:
- Overall sentiment (positive/negative/neutral)
- Confidence (0-100%)
- Key emotional tone

Be concise (2-3 sentences)."""

            sentiment = self.llm_providers.ask_anthropic(sentiment_prompt)
            print("  ✓ Sentiment analyzed")

        except Exception as e:
            print(f"  ✗ Anthropic sentiment analysis failed: {e}")
            # If sentiment fails, use a fallback
            sentiment = "Unable to analyze sentiment"

        result = {
            "title": title,
            "source": article.get("source") or "Unknown",
            "url": article.get("url") or "",
            "summary": summary,
            "sentiment": sentiment,
            "published_at": article.get("published_at") or "",
        }
        self.cache.save(article_hash, normalized_text, result)

        return result

    def process_articles(self, articles):
        """
        Process multiple articles.

        Args:
            articles: List of article dictionaries

        Returns:
            List of processed articles
        """
        results = []

        for article in articles:
            try:
                result = self.summarize_article(article)
                results.append(result)
            except Exception as e:
                print(f"✗ Failed to process article: {e}")
                # Continue with next article

        return results

    def generate_report(self, results):
        """Generate a summary report."""
        print("\n" + "=" * 80)
        print("NEWS SUMMARY REPORT")
        print("=" * 80)

        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['title']}")
            print(f"   Source: {result['source']} | Published: {result['published_at']}")
            print(f"   URL: {result['url']}")
            print("\n   SUMMARY:")
            print(f"   {result['summary']}")
            print("\n   SENTIMENT:")
            print(f"   {result['sentiment']}")
            print(f"\n   {'-' * 76}")

        # Cost summary
        summary = self.llm_providers.cost_tracker.get_summary()
        print("\n" + "=" * 80)
        print("COST SUMMARY")
        print("=" * 80)
        print(f"Total requests: {summary['total_requests']}")
        print(f"Total cost: ${summary['total_cost']:.4f}")
        print(f"Total tokens: {summary['total_input_tokens'] + summary['total_output_tokens']:,}")
        print(f"  Input: {summary['total_input_tokens']:,}")
        print(f"  Output: {summary['total_output_tokens']:,}")
        print(f"Average cost per request: ${summary['average_cost']:.6f}")
        print("=" * 80)


class AsyncNewsSummarizer(NewsSummarizer):
    """Async version for processing multiple articles concurrently."""

    async def summarize_article_async(self, article):
        """Async version of summarize_article."""
        # Note: The LLM API calls themselves are not async in this simple version
        # For true async, you'd need to use aiohttp with the API endpoints directly
        # This version just allows concurrent processing of multiple articles
        return await asyncio.to_thread(self.summarize_article, article)

    async def process_articles_async(self, articles, max_concurrent=3):
        """
        Process articles concurrently.

        Args:
            articles: List of articles
            max_concurrent: Maximum concurrent processes

        Returns:
            List of results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(article):
            async with semaphore:
                return await self.summarize_article_async(article)

        tasks = [process_with_semaphore(article) for article in articles]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = [r for r in results if not isinstance(r, Exception)]

        return valid_results


async def test_async():
    """Test async version."""
    summarizer = AsyncNewsSummarizer()

    # Fetch more articles
    print("Fetching news articles...")
    articles = summarizer.news_api.fetch_top_headlines(
        category="technology", max_articles=5
    )

    if articles:
        print(f"\nProcessing {len(articles)} articles concurrently...")
        results = await summarizer.process_articles_async(articles, max_concurrent=3)
        summarizer.generate_report(results)


# Test the module
if __name__ == "__main__":
    summarizer = NewsSummarizer()

    # Fetch news
    print("Fetching news articles...")
    articles = summarizer.news_api.fetch_top_headlines(
        category="technology", max_articles=2
    )

    if not articles:
        print("No articles fetched. Check your News API key.")
    else:
        # Process articles
        print(f"\nProcessing {len(articles)} articles...")
        results = summarizer.process_articles(articles)

        # Generate report
        summarizer.generate_report(results)

    # Uncomment to test async version
    # asyncio.run(test_async())
