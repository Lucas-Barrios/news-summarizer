"""Topic extraction and trend analytics for processed articles."""
import math
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

from config import Config


STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "and",
    "are",
    "article",
    "been",
    "being",
    "but",
    "can",
    "could",
    "from",
    "has",
    "have",
    "into",
    "its",
    "more",
    "new",
    "news",
    "not",
    "over",
    "said",
    "that",
    "the",
    "their",
    "this",
    "through",
    "was",
    "were",
    "which",
    "will",
    "with",
    "would",
}


def normalize_topic(topic):
    """Normalize a topic for stable storage and matching."""
    topic = re.sub(r"[^a-zA-Z0-9\s-]", " ", topic or "").lower()
    topic = re.sub(r"\s+", " ", topic).strip()
    return topic


def canonical_article_fingerprint(article):
    """Build a near-duplicate fingerprint from stable article fields."""
    raw = " ".join(
        [
            article.get("title") or "",
            article.get("source") or "",
        ]
    )
    normalized = normalize_topic(raw)
    tokens = [token for token in normalized.split() if token not in STOPWORDS]
    return " ".join(tokens[:12])


def extract_named_entities(text):
    """
    Extract simple named entities using capitalization patterns.

    This is an MVP heuristic. It catches names such as "OpenAI", "Apple",
    "Vision Pro", and "NetherRealm Studios" without adding a heavy NLP model.
    """
    candidates = re.findall(
        r"\b(?:[A-Z][a-zA-Z0-9]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-zA-Z0-9]+|[A-Z]{2,}))*",
        text or "",
    )
    entities = []
    for candidate in candidates:
        normalized = normalize_topic(candidate)
        if len(normalized) >= 3 and normalized not in STOPWORDS:
            entities.append(normalized)
    return entities


def extract_keywords(text, max_keywords=12):
    """Extract simple keyword topics from article text."""
    normalized = normalize_topic(text)
    words = [
        word
        for word in normalized.split()
        if len(word) >= 4 and word not in STOPWORDS and not word.isdigit()
    ]

    unigram_counts = Counter(words)
    bigrams = [
        f"{words[index]} {words[index + 1]}"
        for index in range(len(words) - 1)
        if words[index] != words[index + 1]
    ]
    bigram_counts = Counter(bigrams)

    scored = {}
    for keyword, count in unigram_counts.items():
        scored[keyword] = count
    for phrase, count in bigram_counts.items():
        scored[phrase] = count * 1.6

    return [
        topic
        for topic, _score in sorted(
            scored.items(),
            key=lambda item: (item[1], len(item[0])),
            reverse=True,
        )[:max_keywords]
    ]


def extract_topics(article, max_topics=15):
    """Extract keywords and named entities from a processed article."""
    text = " ".join(
        [
            article.get("title") or "",
            article.get("summary") or "",
            article.get("sentiment") or "",
            article.get("normalized_text") or "",
        ]
    )
    topics = []

    for entity in extract_named_entities(text):
        topics.append({"topic": entity, "type": "entity", "weight": 1.4})

    for keyword in extract_keywords(text, max_keywords=max_topics):
        topics.append({"topic": keyword, "type": "keyword", "weight": 1.0})

    deduped = {}
    for topic in topics:
        normalized = normalize_topic(topic["topic"])
        if not normalized or normalized in STOPWORDS:
            continue
        existing = deduped.get(normalized)
        if existing is None or topic["weight"] > existing["weight"]:
            deduped[normalized] = {
                "topic": normalized,
                "type": topic["type"],
                "weight": topic["weight"],
            }

    return list(deduped.values())[:max_topics]


class AnalyticsStore:
    """SQLite storage and trend calculation for article topics."""

    def __init__(self, db_path=None):
        self.db_path = db_path or Config.CACHE_DB_PATH
        self.ensure_schema()

    def connect(self):
        """Create a SQLite connection."""
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_schema(self):
        """Create analytics tables and indexes."""
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
                CREATE TABLE IF NOT EXISTS article_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_hash TEXT NOT NULL,
                    article_fingerprint TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    topic_type TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    source TEXT,
                    category TEXT,
                    article_published_at TEXT,
                    article_updated_at TEXT NOT NULL,
                    extracted_at TEXT NOT NULL,
                    UNIQUE(article_hash, topic)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_article_topics_window
                ON article_topics(article_updated_at, topic)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_article_topics_filters
                ON article_topics(source, category)
                """
            )

    def get_processed_articles(self, since_hours=None, limit=500):
        """Load processed articles from the cache table."""
        params = []
        where = ""
        if since_hours:
            since = (
                datetime.now(timezone.utc) - timedelta(hours=since_hours)
            ).isoformat()
            where = "WHERE updated_at >= ?"
            params.append(since)

        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    article_hash,
                    normalized_text,
                    title,
                    source,
                    url,
                    published_at,
                    summary,
                    sentiment,
                    updated_at
                FROM processed_articles
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def store_article_topics(self, article, topics, category=None):
        """Store extracted topics for one processed article."""
        now = datetime.now(timezone.utc).isoformat()
        fingerprint = canonical_article_fingerprint(article)

        with self.connect() as connection:
            for topic in topics:
                connection.execute(
                    """
                    INSERT INTO article_topics (
                        article_hash,
                        article_fingerprint,
                        topic,
                        topic_type,
                        weight,
                        source,
                        category,
                        article_published_at,
                        article_updated_at,
                        extracted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(article_hash, topic) DO UPDATE SET
                        topic_type = excluded.topic_type,
                        weight = excluded.weight,
                        source = excluded.source,
                        category = COALESCE(excluded.category, article_topics.category),
                        article_published_at = excluded.article_published_at,
                        article_updated_at = excluded.article_updated_at,
                        extracted_at = excluded.extracted_at
                    """,
                    (
                        article["article_hash"],
                        fingerprint,
                        topic["topic"],
                        topic["type"],
                        topic["weight"],
                        article.get("source"),
                        category,
                        article.get("published_at"),
                        article["updated_at"],
                        now,
                    ),
                )

    def extract_and_store_topics(self, since_hours=24, category=None, limit=500):
        """Extract and store topics for recent processed articles."""
        articles = self.get_processed_articles(since_hours=since_hours, limit=limit)
        stored_topics = 0

        for article in articles:
            topics = extract_topics(article)
            self.store_article_topics(article, topics, category=category)
            stored_topics += len(topics)

        return {"articles_processed": len(articles), "topics_stored": stored_topics}

    def calculate_trending_topics(
        self,
        window_hours=24,
        limit=10,
        source=None,
        category=None,
    ):
        """
        Calculate trending topics.

        Score formula:
        trend_strength = weighted_frequency * recency_factor * source_diversity_factor

        - weighted_frequency: sum of extraction weights across deduped articles
        - recency_factor: 0.5 to 1.0 based on average article age in the window
        - source_diversity_factor: 1 + log(unique_sources)
        """
        since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
        params = [since]
        filters = ["article_updated_at >= ?"]

        if source:
            filters.append("source = ?")
            params.append(source)
        if category:
            filters.append("category = ?")
            params.append(category)

        where = " AND ".join(filters)

        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    topic,
                    topic_type,
                    COUNT(DISTINCT article_fingerprint) AS article_count,
                    COUNT(DISTINCT source) AS source_count,
                    SUM(weight) AS weighted_frequency,
                    MAX(article_updated_at) AS latest_seen_at,
                    AVG((julianday('now') - julianday(article_updated_at)) * 24.0)
                        AS average_age_hours
                FROM article_topics
                WHERE {where}
                GROUP BY topic, topic_type
                HAVING article_count > 0
                """,
                params,
            ).fetchall()

        trends = []
        for row in rows:
            weighted_frequency = row["weighted_frequency"] or 0.0
            source_count = row["source_count"] or 1
            average_age = max(row["average_age_hours"] or 0.0, 0.0)
            recency_factor = max(0.5, 1 - (average_age / max(window_hours, 1)))
            source_diversity_factor = 1 + math.log(source_count)
            trend_strength = (
                weighted_frequency * recency_factor * source_diversity_factor
            )

            trends.append(
                {
                    "topic": row["topic"],
                    "topic_type": row["topic_type"],
                    "trend_strength": round(trend_strength, 4),
                    "article_count": row["article_count"],
                    "source_count": source_count,
                    "weighted_frequency": round(weighted_frequency, 4),
                    "recency_factor": round(recency_factor, 4),
                    "source_diversity_factor": round(source_diversity_factor, 4),
                    "latest_seen_at": row["latest_seen_at"],
                }
            )

        trends.sort(
            key=lambda item: (
                item["trend_strength"],
                item["source_count"],
                item["article_count"],
            ),
            reverse=True,
        )

        return {
            "window_hours": window_hours,
            "source": source,
            "category": category,
            "topics": trends[:limit],
            "chart": {
                "labels": [trend["topic"] for trend in trends[:limit]],
                "datasets": [
                    {
                        "label": "Trend strength",
                        "data": [
                            trend["trend_strength"] for trend in trends[:limit]
                        ],
                    }
                ],
            },
        }
