"""Shared pipeline execution for CLI, web, and scheduled jobs."""
import asyncio
import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from config import Config
from summarizer import AsyncNewsSummarizer, NewsSummarizer


logger = logging.getLogger("news_summarizer.pipeline")


def configure_logging(log_file=None):
    """Configure pipeline logging once."""
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s - %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file or Config.PIPELINE_LOG_FILE)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


@dataclass
class PipelineRunResult:
    """Summary of one pipeline run."""

    status: str
    category: str
    requested_articles: int
    fetched_articles: int
    processed_articles: int
    async_processing: bool
    started_at: str
    finished_at: str
    duration_seconds: float
    cost_summary: dict
    results: list
    error: str | None = None

    def to_dict(self):
        """Return a JSON-serializable result."""
        return asdict(self)


class PipelineLockError(Exception):
    """Raised when another pipeline run already holds the lock."""


@contextmanager
def pipeline_lock(lock_file=None, stale_after_seconds=3600):
    """
    Use a simple atomic file lock to avoid duplicate scheduled runs.

    This is intentionally process-safe on a single machine. For multiple VMs or
    containers, move this lock into shared infrastructure such as Redis,
    Postgres advisory locks, or the task queue itself.
    """
    path = lock_file or Config.PIPELINE_LOCK_FILE
    lock_fd = None

    try:
        try:
            lock_fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = {
                "pid": os.getpid(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            os.write(lock_fd, json.dumps(payload).encode("utf-8"))
        except FileExistsError as exc:
            age = time.time() - os.path.getmtime(path)
            if age > stale_after_seconds:
                logger.warning("Removing stale pipeline lock: %s", path)
                os.unlink(path)
                lock_fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            else:
                raise PipelineLockError("Pipeline is already running") from exc

        yield
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


def _run_sync(category, max_articles):
    summarizer = NewsSummarizer()
    articles = summarizer.news_api.fetch_top_headlines(
        category=category,
        max_articles=max_articles,
    )
    results = summarizer.process_articles(articles) if articles else []
    return summarizer, articles, results


async def _run_async(category, max_articles, max_concurrent):
    summarizer = AsyncNewsSummarizer()
    articles = summarizer.news_api.fetch_top_headlines(
        category=category,
        max_articles=max_articles,
    )
    results = (
        await summarizer.process_articles_async(
            articles,
            max_concurrent=max_concurrent,
        )
        if articles
        else []
    )
    return summarizer, articles, results


def run_pipeline(
    category=None,
    max_articles=None,
    async_processing=False,
    max_concurrent=3,
    lock_file=None,
):
    """
    Run the news summarization pipeline with logging and duplicate-run locking.

    The existing article cache remains inside NewsSummarizer.summarize_article(),
    so scheduled runs can safely see repeated articles without reprocessing them.
    """
    configure_logging()

    category = category or Config.SCHEDULE_CATEGORY
    max_articles = max_articles or Config.SCHEDULE_ARTICLE_LIMIT
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Pipeline starting category=%s max_articles=%s async=%s",
        category,
        max_articles,
        async_processing,
    )

    try:
        with pipeline_lock(lock_file=lock_file):
            if async_processing:
                summarizer, articles, results = asyncio.run(
                    _run_async(category, max_articles, max_concurrent)
                )
            else:
                summarizer, articles, results = _run_sync(category, max_articles)

            cost_summary = summarizer.llm_providers.cost_tracker.get_summary()
            duration = time.monotonic() - started
            finished_at = datetime.now(timezone.utc).isoformat()

            run_result = PipelineRunResult(
                status="success",
                category=category,
                requested_articles=max_articles,
                fetched_articles=len(articles),
                processed_articles=len(results),
                async_processing=async_processing,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=round(duration, 3),
                cost_summary=cost_summary,
                results=results,
            )

            logger.info(
                "Pipeline completed fetched=%s processed=%s cost=%.6f duration=%.3fs",
                run_result.fetched_articles,
                run_result.processed_articles,
                cost_summary.get("total_cost", 0.0),
                duration,
            )
            return run_result

    except PipelineLockError as e:
        duration = time.monotonic() - started
        logger.warning("Pipeline skipped: %s", e)
        return PipelineRunResult(
            status="skipped",
            category=category,
            requested_articles=max_articles,
            fetched_articles=0,
            processed_articles=0,
            async_processing=async_processing,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=round(duration, 3),
            cost_summary={},
            results=[],
            error=str(e),
        )

    except Exception as e:
        duration = time.monotonic() - started
        logger.exception("Pipeline failed")
        return PipelineRunResult(
            status="failed",
            category=category,
            requested_articles=max_articles,
            fetched_articles=0,
            processed_articles=0,
            async_processing=async_processing,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=round(duration, 3),
            cost_summary={},
            results=[],
            error=str(e),
        )


if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps(result.to_dict(), indent=2))
