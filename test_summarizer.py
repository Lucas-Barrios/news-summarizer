"""Unit tests for news summarizer."""
from unittest.mock import Mock, patch

import pytest

from news_api import NewsAPI
from digest_builder import build_digest_subject, build_html_digest, rank_articles
from digest_data import DigestStore
from llm_providers import LLMProviders, CostTracker, count_tokens
from pipeline import PipelineLockError, pipeline_lock
from summarizer import NewsSummarizer, hash_article_text, normalize_article_text


class TestCostTracker:
    """Test cost tracking functionality."""

    def test_track_request(self):
        """Test tracking a single request."""
        tracker = CostTracker()
        cost = tracker.track_request("openai", "gpt-4o-mini", 100, 500)

        assert cost > 0
        assert tracker.total_cost == cost
        assert len(tracker.requests) == 1

    def test_get_summary(self):
        """Test summary generation."""
        tracker = CostTracker()
        tracker.track_request("openai", "gpt-4o-mini", 100, 200)
        tracker.track_request("anthropic", "claude-3-5-sonnet-20241022", 150, 300)

        summary = tracker.get_summary()

        assert summary["total_requests"] == 2
        assert summary["total_cost"] > 0
        assert summary["total_input_tokens"] == 250
        assert summary["total_output_tokens"] == 500

    def test_budget_check(self):
        """Test budget checking."""
        tracker = CostTracker()

        # Should not raise for small amount
        tracker.track_request("openai", "gpt-4o-mini", 100, 100)
        tracker.check_budget(10.00)  # Should pass

        # Should raise for exceeding budget
        tracker.total_cost = 15.00
        with pytest.raises(Exception, match="budget.*exceeded"):
            tracker.check_budget(10.00)


class TestTokenCounting:
    """Test token counting."""

    def test_count_tokens(self):
        """Test token counting function."""
        text = "Hello, how are you?"
        count = count_tokens(text)

        assert count > 0
        assert count < len(text)  # Should be less than character count


class TestNewsAPI:
    """Test News API integration."""

    @patch("news_api.requests.get")
    def test_fetch_top_headlines(self, mock_get):
        """Test fetching headlines."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "articles": [
                {
                    "title": "Test Article",
                    "description": "Test description",
                    "content": "Test content",
                    "url": "https://example.com",
                    "source": {"name": "Test Source"},
                    "publishedAt": "2026-01-19",
                }
            ],
        }
        mock_get.return_value = mock_response

        api = NewsAPI()
        articles = api.fetch_top_headlines(max_articles=1)

        assert len(articles) == 1
        assert articles[0]["title"] == "Test Article"
        assert articles[0]["source"] == "Test Source"


class TestLLMProviders:
    """Test LLM provider integration."""

    @patch("llm_providers.OpenAI")
    def test_ask_openai(self, mock_openai_class):
        """Test OpenAI integration."""
        # Mock OpenAI client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Test response"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        providers = LLMProviders()
        providers.openai_client = mock_client

        response = providers.ask_openai("Test prompt")

        assert response == "Test response"
        assert mock_client.chat.completions.create.called


class TestNewsSummarizer:
    """Test news summarizer."""

    def test_initialization(self, tmp_path):
        """Test summarizer initialization."""
        summarizer = NewsSummarizer(cache_path=tmp_path / "cache.sqlite3")

        assert summarizer.news_api is not None
        assert summarizer.llm_providers is not None

    @patch.object(LLMProviders, "ask_openai")
    @patch.object(LLMProviders, "ask_anthropic")
    def test_summarize_article(self, mock_anthropic, mock_openai, tmp_path):
        """Test article summarization."""
        mock_openai.return_value = "Test summary"
        mock_anthropic.return_value = "Positive sentiment"

        summarizer = NewsSummarizer(cache_path=tmp_path / "cache.sqlite3")
        article = {
            "title": "Test Article",
            "description": "Test description",
            "content": "Test content",
            "url": "https://example.com",
            "source": "Test Source",
            "published_at": "2026-01-19",
        }

        result = summarizer.summarize_article(article)

        assert result["title"] == "Test Article"
        assert result["summary"] == "Test summary"
        assert result["sentiment"] == "Positive sentiment"
        assert mock_openai.called
        assert mock_anthropic.called

    def test_article_hash_normalizes_whitespace(self):
        """Test hashes are stable across whitespace differences."""
        text_a = "Title: Test Article\nDescription: Some text"
        text_b = "Title:   Test   Article   \n\nDescription: Some text"

        assert normalize_article_text(text_b) == "Title: Test Article Description: Some text"
        assert hash_article_text(text_a) == hash_article_text(text_b)

    @patch.object(LLMProviders, "ask_openai")
    @patch.object(LLMProviders, "ask_anthropic")
    def test_summarize_article_uses_cache(self, mock_anthropic, mock_openai, tmp_path):
        """Test identical articles are returned from cache without another LLM call."""
        mock_openai.return_value = "Cached summary"
        mock_anthropic.return_value = "Cached sentiment"

        summarizer = NewsSummarizer(cache_path=tmp_path / "cache.sqlite3")
        article = {
            "title": "Test Article",
            "description": "Test description",
            "content": "Test content",
            "url": "https://example.com",
            "source": "Test Source",
            "published_at": "2026-01-19",
        }
        same_article_different_spacing = {
            "title": "Test   Article",
            "description": "Test     description",
            "content": "Test content",
            "url": "https://example.com/duplicate",
            "source": "Other Source",
            "published_at": "2026-01-20",
        }

        first_result = summarizer.summarize_article(article)
        second_result = summarizer.summarize_article(same_article_different_spacing)

        assert first_result == second_result
        assert mock_openai.call_count == 1
        assert mock_anthropic.call_count == 1


class TestPipelineLock:
    """Test scheduled-run lock behavior."""

    def test_pipeline_lock_prevents_duplicate_runs(self, tmp_path):
        """Test a second lock cannot be acquired while the first is active."""
        lock_file = tmp_path / "pipeline.lock"

        with pipeline_lock(lock_file=lock_file):
            with pytest.raises(PipelineLockError):
                with pipeline_lock(lock_file=lock_file):
                    pass

    def test_pipeline_lock_removes_lock_file(self, tmp_path):
        """Test the lock file is cleaned up after a run."""
        lock_file = tmp_path / "pipeline.lock"

        with pipeline_lock(lock_file=lock_file):
            assert lock_file.exists()

        assert not lock_file.exists()


class TestEmailDigest:
    """Test daily email digest helpers."""

    def test_rank_articles_limits_by_latest_publish_date(self):
        """Test digest ranking and truncation."""
        articles = [
            {"title": "Old", "published_at": "2026-01-01T00:00:00Z"},
            {"title": "New", "published_at": "2026-01-02T00:00:00Z"},
        ]

        ranked = rank_articles(articles, limit=1)

        assert ranked == [{"title": "New", "published_at": "2026-01-02T00:00:00Z"}]

    def test_build_html_digest_escapes_article_content(self):
        """Test the HTML digest is readable and escapes unsafe content."""
        subject = build_digest_subject()
        html = build_html_digest(
            [
                {
                    "title": "<script>alert(1)</script>",
                    "source": "Test Source",
                    "published_at": "2026-01-01",
                    "summary": "Summary",
                    "sentiment": "Neutral",
                    "url": "https://example.com",
                }
            ],
            subject,
        )

        assert "Daily AI News" in html
        assert "&lt;script&gt;" in html
        assert "<script>alert(1)</script>" not in html

    def test_digest_store_tracks_sent_digest(self, tmp_path):
        """Test sent digest tracking prevents duplicate sends."""
        store = DigestStore(db_path=tmp_path / "digest.sqlite3")

        store.record_digest_attempt(
            digest_id="digest-1",
            recipient_email="user@example.com",
            subject="Daily AI News",
            article_count=2,
            status="sent",
            provider="smtp",
            open_tracking_id="digest-1",
        )

        assert store.digest_already_sent("digest-1")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
