"""SQLite data access for daily email digests."""
import sqlite3
from datetime import datetime, timedelta, timezone

from config import Config


class DigestStore:
    """Read summarized articles and track digest sends."""

    def __init__(self, db_path=None):
        self.db_path = db_path or Config.CACHE_DB_PATH
        self.ensure_tables()

    def connect(self):
        """Create a SQLite connection."""
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_tables(self):
        """Create digest-related tables if needed."""
        with self.connect() as connection:
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS subscribers (
                    email TEXT PRIMARY KEY,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS digest_sends (
                    digest_id TEXT PRIMARY KEY,
                    recipient_email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    article_count INTEGER NOT NULL,
                    sent_at TEXT,
                    status TEXT NOT NULL,
                    provider TEXT,
                    error TEXT,
                    open_tracking_id TEXT,
                    opened_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    def add_subscriber(self, email):
        """Add or reactivate a subscriber."""
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO subscribers (email, is_active, created_at)
                VALUES (?, 1, ?)
                ON CONFLICT(email) DO UPDATE SET is_active = 1
                """,
                (email, now),
            )

    def get_active_subscribers(self):
        """Return active digest subscribers."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT email
                FROM subscribers
                WHERE is_active = 1
                ORDER BY created_at ASC
                """
            ).fetchall()

        subscribers = [row["email"] for row in rows]
        if subscribers:
            return subscribers

        return [Config.DIGEST_TO_EMAIL] if Config.DIGEST_TO_EMAIL else []

    def get_recent_articles(self, hours=24, limit=10):
        """Return unique processed articles from the last N hours."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    article_hash,
                    title,
                    source,
                    url,
                    published_at,
                    summary,
                    sentiment,
                    updated_at
                FROM processed_articles
                WHERE updated_at >= ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (since, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def digest_already_sent(self, digest_id):
        """Return whether a digest has already been sent successfully."""
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM digest_sends
                WHERE digest_id = ? AND status = 'sent'
                """,
                (digest_id,),
            ).fetchone()

        return row is not None

    def record_digest_attempt(
        self,
        digest_id,
        recipient_email,
        subject,
        article_count,
        status,
        provider,
        error=None,
        open_tracking_id=None,
    ):
        """Record a digest delivery attempt."""
        now = datetime.now(timezone.utc).isoformat()
        sent_at = now if status == "sent" else None

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO digest_sends (
                    digest_id,
                    recipient_email,
                    subject,
                    article_count,
                    sent_at,
                    status,
                    provider,
                    error,
                    open_tracking_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(digest_id) DO UPDATE SET
                    sent_at = excluded.sent_at,
                    status = excluded.status,
                    provider = excluded.provider,
                    error = excluded.error,
                    open_tracking_id = excluded.open_tracking_id
                """,
                (
                    digest_id,
                    recipient_email,
                    subject,
                    article_count,
                    sent_at,
                    status,
                    provider,
                    error,
                    open_tracking_id,
                    now,
                ),
            )
