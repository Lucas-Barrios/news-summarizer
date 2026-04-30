"""Daily email digest job."""
import argparse
import hashlib
import logging
import sys
import time
from datetime import date

from config import Config
from digest_builder import (
    build_digest_subject,
    build_html_digest,
    build_text_digest,
    rank_articles,
)
from digest_data import DigestStore
from email_sender import EmailDeliveryError, get_email_sender
from pipeline import configure_logging, pipeline_lock


logger = logging.getLogger("news_summarizer.digest")


def build_digest_id(recipient_email, articles, run_date=None):
    """Build a deterministic digest id for duplicate-send prevention."""
    run_date = run_date or date.today()
    article_hashes = ",".join(article["article_hash"] for article in articles)
    raw = f"{recipient_email}|{run_date.isoformat()}|{article_hashes}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_tracking_url(digest_id):
    """Return an open-tracking placeholder URL."""
    return f"{Config.DIGEST_BASE_URL.rstrip('/')}/api/digest/open/{digest_id}.gif"


def send_daily_digest(
    hours=24,
    max_articles=None,
    provider=None,
    dry_run=False,
    retries=2,
):
    """Send daily digest emails for active subscribers."""
    configure_logging()
    store = DigestStore()
    max_articles = max_articles or Config.DIGEST_MAX_ARTICLES
    articles = rank_articles(store.get_recent_articles(hours=hours, limit=50), max_articles)
    subscribers = store.get_active_subscribers()

    if not articles:
        logger.info("No recent articles available for digest")
        return {"status": "skipped", "reason": "no_articles", "sent": 0}

    if not subscribers:
        logger.info("No active digest subscribers configured")
        return {"status": "skipped", "reason": "no_subscribers", "sent": 0}

    sender = get_email_sender(provider)
    subject = build_digest_subject()
    sent = 0
    failed = 0
    skipped = 0

    for recipient in subscribers:
        digest_id = build_digest_id(recipient, articles)
        if store.digest_already_sent(digest_id):
            logger.info("Digest already sent recipient=%s digest_id=%s", recipient, digest_id)
            skipped += 1
            continue

        tracking_url = build_tracking_url(digest_id)
        html_body = build_html_digest(articles, subject, tracking_pixel_url=tracking_url)
        text_body = build_text_digest(articles, subject)

        if dry_run:
            logger.info("Dry run digest recipient=%s subject=%s", recipient, subject)
            skipped += 1
            continue

        for attempt in range(1, retries + 2):
            try:
                sender.send(recipient, subject, html_body, text_body)
                store.record_digest_attempt(
                    digest_id=digest_id,
                    recipient_email=recipient,
                    subject=subject,
                    article_count=len(articles),
                    status="sent",
                    provider=sender.provider_name,
                    open_tracking_id=digest_id,
                )
                logger.info("Digest sent recipient=%s articles=%s", recipient, len(articles))
                sent += 1
                break
            except EmailDeliveryError as e:
                logger.warning(
                    "Digest send failed recipient=%s attempt=%s error=%s",
                    recipient,
                    attempt,
                    e,
                )
                if attempt > retries:
                    store.record_digest_attempt(
                        digest_id=digest_id,
                        recipient_email=recipient,
                        subject=subject,
                        article_count=len(articles),
                        status="failed",
                        provider=sender.provider_name,
                        error=str(e),
                        open_tracking_id=digest_id,
                    )
                    failed += 1
                else:
                    time.sleep(2**attempt)

    status = "success" if failed == 0 else "partial_failure"
    return {"status": status, "sent": sent, "failed": failed, "skipped": skipped}


def main():
    """CLI entry point for daily digest sends."""
    parser = argparse.ArgumentParser(description="Send daily news digest emails.")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--max-articles", type=int, default=Config.DIGEST_MAX_ARTICLES)
    parser.add_argument("--provider", choices=["smtp", "sendgrid"], default=Config.EMAIL_PROVIDER)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        with pipeline_lock(lock_file=Config.DIGEST_LOCK_FILE):
            result = send_daily_digest(
                hours=args.hours,
                max_articles=args.max_articles,
                provider=args.provider,
                dry_run=args.dry_run,
            )
    except Exception:
        logger.exception("Digest job failed")
        sys.exit(1)

    print(result)
    sys.exit(0 if result["status"] in {"success", "skipped"} else 1)


if __name__ == "__main__":
    main()
