# News Summarizer

Multi-provider news summarizer that fetches articles, summarizes them with
OpenAI, analyzes sentiment with Anthropic, caches processed articles in SQLite,
serves a FastAPI web UI, supports scheduled runs, sends daily email digests, and
calculates trending topics.

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

## Cost Notes

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
