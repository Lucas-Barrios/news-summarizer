# Trending Topic Analytics

## Architecture Overview

Analytics is layered separately from summarization:

- `summarizer.py`: creates cached `processed_articles` rows keyed by article hash.
- `analytics.py`: extracts topics/entities, stores article-topic rows, and calculates trends.
- `pipeline.py`: calls analytics after processing articles so topics stay current.
- `web_app.py`: exposes charts-ready FastAPI endpoints.

This keeps analytics independent of the LLM workflow. The MVP uses local keyword
and named-entity heuristics, while the storage and API shape can support a later
LLM or NLP model extractor.

## Database Schema

The existing cache table remains the source of truth:

```sql
CREATE TABLE processed_articles (
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
);
```

Analytics adds:

```sql
CREATE TABLE article_topics (
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
);
```

Indexes:

```sql
CREATE INDEX idx_article_topics_window
ON article_topics(article_updated_at, topic);

CREATE INDEX idx_article_topics_filters
ON article_topics(source, category);
```

`article_hash` avoids duplicate counting for identical articles. `article_fingerprint`
helps avoid near-duplicate counting by grouping articles with the same normalized
title/source signature.

## Topic Extraction

Simple keyword extraction:

```python
from analytics import extract_topics

topics = extract_topics({
    "title": "OpenAI Launches New Product",
    "summary": "OpenAI released an AI product for developers.",
    "normalized_text": "Title: OpenAI Launches New Product..."
})
```

The MVP extractor combines:

- named entities from capitalization patterns, e.g. `OpenAI`, `Apple`, `Vision Pro`
- keywords and two-word phrases using frequency counts
- topic normalization to lowercase, punctuation-free forms
- light stopword filtering

## Simple Keywords vs LLM Topic Extraction

Simple extraction:

- fast
- free
- deterministic
- good enough for dashboards and MVP trend charts
- weaker at ambiguity, topic grouping, and semantic concepts

LLM extraction:

- better at semantic grouping, e.g. `AI infrastructure`, `mixed reality`
- can return typed entities and canonical names
- costs money and adds latency
- needs stricter JSON validation and retry handling

A later LLM extractor can write to the same `article_topics` table by returning:

```json
[
  {"topic": "openai", "type": "organization", "weight": 1.4},
  {"topic": "ai infrastructure", "type": "theme", "weight": 1.2}
]
```

## Trend Scoring Logic

Trend score:

```text
trend_strength = weighted_frequency * recency_factor * source_diversity_factor
```

Where:

- `weighted_frequency`: sum of topic weights across matching topic rows
- `recency_factor`: between `0.5` and `1.0`, based on average article age inside the window
- `source_diversity_factor`: `1 + log(unique_sources)`

Why this works for an MVP:

- frequency rewards topics appearing repeatedly
- recency rewards topics seen recently
- source diversity rewards topics covered by more than one outlet
- near-duplicate article fingerprints reduce repeated counting

## FastAPI Endpoints

Extract topics for recently processed articles:

```http
POST /api/analytics/extract-topics?window_hours=24&category=technology
```

Trending topics:

```http
GET /api/analytics/trending-topics?window_hours=24&limit=10
GET /api/analytics/trending-topics?window_hours=168&source=Google%20News
GET /api/analytics/trending-topics?window_hours=720&category=technology
```

Charts-ready response:

```json
{
  "window_hours": 24,
  "source": null,
  "category": "technology",
  "topics": [
    {
      "topic": "openai",
      "topic_type": "entity",
      "trend_strength": 4.82,
      "article_count": 3,
      "source_count": 2,
      "weighted_frequency": 4.2,
      "recency_factor": 0.9,
      "source_diversity_factor": 1.6931,
      "latest_seen_at": "2026-05-01T08:00:00+00:00"
    }
  ],
  "chart": {
    "labels": ["openai"],
    "datasets": [
      {"label": "Trend strength", "data": [4.82]}
    ]
  }
}
```

## Source and Category Filters

Topic rows store both `source` and `category`, so dashboards can filter:

- by source, e.g. `source=Google News`
- by category, e.g. `category=technology`
- by window, e.g. 24 hours, 7 days, 30 days

Category is attached when the shared pipeline runs because the original
NewsAPI category is known there.

## Testing Approach

Tests cover:

- topic normalization
- named-entity extraction
- keyword extraction
- topic storage
- near-duplicate trend counting via article fingerprints
- charts-ready JSON structure

The tests use temporary SQLite databases, so they do not touch the local cache.

## Supabase/Postgres Extension

SQLite is fine for a single VM and MVP dashboards. Move to Supabase/Postgres when:

- multiple app instances write analytics
- you need dashboard queries over larger history
- you need better full-text search or materialized views
- subscriber/user analytics should join with auth tables

Migration shape:

- `processed_articles.article_hash` remains a unique key
- `article_topics` gets indexes on `(article_updated_at, topic)`, `(source, category)`
- near-duplicate logic can become a generated fingerprint column
- trend queries can move into SQL views or materialized views
- locks move from local files to Postgres advisory locks or Redis
