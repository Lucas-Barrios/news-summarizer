"""Standalone in-app scheduler for automatic pipeline runs."""
import argparse
import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import Config
from pipeline import configure_logging, run_pipeline


logger = logging.getLogger("news_summarizer.scheduler")


def scheduled_job(category=None, max_articles=None, async_processing=False):
    """Scheduled job function that triggers one pipeline run."""
    result = run_pipeline(
        category=category or Config.SCHEDULE_CATEGORY,
        max_articles=max_articles or Config.SCHEDULE_ARTICLE_LIMIT,
        async_processing=async_processing,
    )

    if result.status == "failed":
        logger.error("Scheduled pipeline failed: %s", result.error)
    elif result.status == "skipped":
        logger.warning("Scheduled pipeline skipped: %s", result.error)
    else:
        logger.info(
            "Scheduled pipeline succeeded: processed=%s cost=%.6f",
            result.processed_articles,
            result.cost_summary.get("total_cost", 0.0),
        )

    return result


def build_scheduler(interval_minutes=None, category=None, max_articles=None):
    """Build the APScheduler instance."""
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_job,
        trigger=IntervalTrigger(
            minutes=interval_minutes or Config.SCHEDULE_INTERVAL_MINUTES
        ),
        id="news_summarizer_pipeline",
        name="News summarizer pipeline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        kwargs={
            "category": category or Config.SCHEDULE_CATEGORY,
            "max_articles": max_articles or Config.SCHEDULE_ARTICLE_LIMIT,
            "async_processing": False,
        },
    )
    return scheduler


def main():
    """Run the in-app scheduler process."""
    parser = argparse.ArgumentParser(description="Run the news summarizer scheduler.")
    parser.add_argument("--run-once", action="store_true", help="Run one job and exit.")
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=Config.SCHEDULE_INTERVAL_MINUTES,
        help="Interval between scheduled runs.",
    )
    parser.add_argument(
        "--category",
        default=Config.SCHEDULE_CATEGORY,
        help="News category to process.",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=Config.SCHEDULE_ARTICLE_LIMIT,
        help="Number of articles per run.",
    )
    args = parser.parse_args()

    configure_logging()
    logger.info("Scheduler starting")

    if args.run_once:
        result = scheduled_job(
            category=args.category,
            max_articles=args.max_articles,
        )
        sys.exit(0 if result.status == "success" else 1)

    scheduler = build_scheduler(
        interval_minutes=args.interval_minutes,
        category=args.category,
        max_articles=args.max_articles,
    )

    def shutdown(signum, _frame):
        logger.info("Scheduler received signal %s; shutting down", signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info(
        "Scheduler configured interval=%s minutes category=%s max_articles=%s",
        args.interval_minutes,
        args.category,
        args.max_articles,
    )
    scheduler.start()


if __name__ == "__main__":
    main()
