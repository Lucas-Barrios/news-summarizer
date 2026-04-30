# News Summarizer

Multi-provider news summarizer that fetches articles, summarizes them with
OpenAI, analyzes sentiment with Anthropic, caches processed articles in SQLite,
serves a FastAPI web UI, supports scheduled runs, sends daily email digests, and
calculates trending topics.

## What This Project Does

This project is an end-to-end news intelligence pipeline. It pulls current news
articles from NewsAPI, turns each article into a concise LLM-generated summary,
adds sentiment analysis, stores the processed result locally, and exposes the
output through a CLI, a FastAPI web app, scheduled jobs, email digests, and
analytics endpoints.

The main workflow is:

```text
NewsAPI -> article normalization -> SQLite cache lookup -> OpenAI summary
        -> Anthropic sentiment -> SQLite storage -> reports/API/digest/analytics
```

The cache is part of the core design. Repeated articles are detected with a
deterministic hash of normalized article text, so reruns and scheduled jobs avoid
paying for duplicate LLM work.

## Features

- Fetches top headlines from NewsAPI.
- Summarizes articles with OpenAI.
- Analyzes sentiment with Anthropic.
- Falls back between providers when configured logic fails.
- Tracks token usage and estimated API cost.
- Respects API rate limits.
- Caches processed articles by deterministic content hash in SQLite.
- Provides a FastAPI web interface.
- Supports scheduled pipeline runs with cron/systemd or APScheduler.
- Sends daily email digests through SMTP or SendGrid.
- Extracts topics/entities and exposes trending topic analytics.

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create `.env` in the project root:

```bash
OPENAI_API_KEY=your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
NEWS_API_KEY=your-newsapi-key-here

ENVIRONMENT=development
MAX_RETRIES=3
REQUEST_TIMEOUT=30
DAILY_BUDGET=5.00

CACHE_DB_PATH=article_cache.sqlite3
PIPELINE_LOCK_FILE=pipeline.lock
PIPELINE_LOG_FILE=pipeline.log

EMAIL_PROVIDER=smtp
DIGEST_FROM_EMAIL=news@example.com
DIGEST_TO_EMAIL=reader@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=news@example.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=true
```

`.env` is ignored by Git and must not be committed.

4. Validate configuration:

```bash
python config.py
```

Expected:

```text
✓ Configuration validated for development environment
```

## How To Run

### CLI

```bash
python main.py
```

The app prompts for category, article count, and async processing.

### Direct Summarizer Test

```bash
python summarizer.py
```

### FastAPI Web App

```bash
uvicorn web_app:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Useful API endpoints:

```http
POST /api/summarize
GET /api/cache-stats
POST /api/analytics/extract-topics?window_hours=24&category=technology
GET /api/analytics/trending-topics?window_hours=24&limit=10
```

### Scheduled Pipeline

Run once:

```bash
python scheduler.py --run-once --category technology --max-articles 5
```

Run continuously with APScheduler:

```bash
python scheduler.py --interval-minutes 60 --category technology --max-articles 5
```

See [SCHEDULING.md](SCHEDULING.md) for cron and systemd timer examples.

### Daily Email Digest

Dry run:

```bash
python digest_job.py --dry-run
```

Send:

```bash
python digest_job.py --provider smtp --max-articles 5
```

See [EMAIL_DIGEST.md](EMAIL_DIGEST.md) for SMTP, SendGrid, subscriptions, and
monitoring details.

### Trending Topic Analytics

Extract topics for recent cached articles:

```bash
curl -X POST "http://127.0.0.1:8000/api/analytics/extract-topics?window_hours=24&category=technology"
```

Get trends:

```bash
curl "http://127.0.0.1:8000/api/analytics/trending-topics?window_hours=24&limit=10"
```

See [ANALYTICS.md](ANALYTICS.md) for schema, scoring, filters, and Postgres notes.

## Example Output

CLI report excerpt:

```text
NEWS SUMMARY REPORT

1. Apple Has Given Up on the Vision Pro After M5 Refresh Flop - MacRumors
   Source: Google News | Published: 2026-04-29T18:31:59Z

   SUMMARY:
   Apple has reportedly reassessed its Vision Pro strategy after weak market response...

   SENTIMENT:
   Overall sentiment: Negative
   Confidence: 85%
   Key emotional tone: disappointment and concern

COST SUMMARY
Total requests: 4
Total cost: $0.0039
Total tokens: 701
Input: 359
Output: 342
Average cost per request: $0.000987
```

Trending topics response excerpt:

```json
{
  "window_hours": 24,
  "topics": [
    {
      "topic": "openai",
      "topic_type": "entity",
      "trend_strength": 4.82,
      "article_count": 3,
      "source_count": 2
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

## Cost Analysis

The project estimates LLM spend with per-million-token pricing in
`llm_providers.py`.

Current model defaults:

- OpenAI: `gpt-4o-mini`
- Anthropic: `claude-sonnet-4-20250514`

Cost controls:

- `DAILY_BUDGET` stops processing when estimated spend exceeds the configured
  budget.
- SQLite caching avoids repeated LLM calls for identical normalized article text.
- Scheduled runs reuse the same cache, so repeated articles are not reprocessed.
- Digest and analytics read from cached summaries and do not call LLMs.

Example from a small two-article run:

```text
Total requests: 4
Total cost: $0.0039
Total tokens: 701
Average cost per request: $0.000987
```

Cost grows mainly with:

- number of articles processed
- article text length included in prompts
- OpenAI/Anthropic model choice
- whether articles are already cached
- scheduled run frequency

For local development, process one to three articles at a time. For production,
set a conservative `DAILY_BUDGET`, monitor `pipeline.log`, and keep cheaper
models for high-volume summarization unless quality requirements justify more
expensive models.

API pricing changes over time. Update the `PRICING` dictionary when provider
pricing changes.

## Testing

Run tests:

```bash
pytest test_summarizer.py -v
```

Run syntax checks:

```bash
python -m py_compile *.py
```

Run style checks:

```bash
python -m pycodestyle *.py
```

The project uses `setup.cfg` with `max-line-length = 100`.

## File Map

```text
news-summarizer/
├── .env                  # Local secrets and runtime config; ignored by Git
├── .gitignore            # Ignore secrets, caches, logs, SQLite DBs, lock files
├── README.md             # Project setup and usage guide
├── ANALYTICS.md          # Trending topic analytics design and API notes
├── EMAIL_DIGEST.md       # Daily digest design and delivery setup
├── SCHEDULING.md         # Cron, systemd, APScheduler, and Celery trade-offs
├── requirements.txt      # Python dependencies
├── setup.cfg             # pycodestyle configuration
├── config.py             # Environment loading and app configuration
├── news_api.py           # NewsAPI client and rate limiting
├── llm_providers.py      # OpenAI/Anthropic clients, fallback, costs, rate limits
├── summarizer.py         # Summarization core, async wrapper, SQLite article cache
├── pipeline.py           # Shared pipeline runner with locking and logging
├── scheduler.py          # APScheduler jobs for pipeline and email digest
├── main.py               # Interactive CLI entry point
├── web_app.py            # FastAPI app, web UI, analytics endpoints
├── analytics.py          # Topic extraction, storage, trend scoring
├── digest_data.py        # SQLite data layer for digests and subscribers
├── digest_builder.py     # HTML/text digest formatting and subject generation
├── email_sender.py       # SMTP and SendGrid email delivery providers
├── digest_job.py         # Daily digest job with retries and duplicate prevention
└── test_summarizer.py    # Unit tests
```

Generated local files:

```text
article_cache.sqlite3     # SQLite cache; ignored by Git
pipeline.log              # Runtime log; ignored by Git
pipeline.lock             # Duplicate-run lock; ignored by Git
digest.lock               # Digest duplicate-run lock; ignored by Git
```

## Production Notes

- Use a VM process manager such as `systemd` for `uvicorn` and scheduled jobs.
- Keep all keys in environment variables or a secret manager.
- Ship logs to CloudWatch, Datadog, Grafana Loki, or similar.
- Move SQLite to Supabase/Postgres when running multiple app instances.
- Move file locks to Postgres advisory locks or Redis for distributed deployments.

## Future Deployment And Migration Considerations

The current architecture is intentionally simple and works well for local
development or a single cloud VM:

- SQLite stores cached articles, topics, subscribers, and digest send history.
- File locks prevent overlapping pipeline or digest jobs on one machine.
- APScheduler, cron, or systemd timers can trigger scheduled work.
- FastAPI serves the web UI and JSON API.

For a production deployment, migrate incrementally:

1. Single VM:
   - Run `uvicorn` behind Nginx or Caddy.
   - Use `systemd` services/timers for the web app and scheduled jobs.
   - Store `.env` values in a VM secret store or locked-down environment file.
   - Back up `article_cache.sqlite3` regularly.

2. Managed database:
   - Move `processed_articles`, `article_topics`, `subscribers`, and
     `digest_sends` from SQLite to Supabase/Postgres.
   - Keep `article_hash` as a unique key for cache/idempotency.
   - Add indexes for `updated_at`, `topic`, `source`, and `category`.

3. Distributed jobs:
   - Replace file locks with Postgres advisory locks or Redis locks.
   - Move long-running work to Celery/RQ when multiple workers or retries are
     needed.
   - Keep FastAPI focused on HTTP requests and enqueue background tasks instead
     of running them directly.

4. Observability:
   - Centralize logs.
   - Alert on failed scheduled runs and daily budget threshold breaches.
   - Track LLM spend, cache hit rate, digest sends, and API failures.

The existing module boundaries are designed for this migration: replace the data
layer first, then the scheduler/queue, without rewriting summarization,
digest-building, or analytics logic.
