# Daily Email Digest

## Architecture Overview

The email digest is separated into small layers:

- `digest_data.py`: SQLite queries for recent summaries, subscribers, send history, and open tracking fields.
- `digest_builder.py`: subject generation, article ranking/truncation, HTML email, and plain-text fallback.
- `email_sender.py`: delivery providers. Current options are SMTP and SendGrid API.
- `digest_job.py`: scheduled job orchestration, retries, duplicate-send prevention, and locking.
- `scheduler.py`: optional APScheduler integration for daily digest sends.

The digest reads from the existing `processed_articles` SQLite table. That means
the existing article hash/cache behavior is respected: duplicate articles are
not reprocessed by the LLM, and the digest sees unique processed rows.

## Environment Variables

Keep secrets in `.env`, not in Git.

SMTP example:

```bash
EMAIL_PROVIDER=smtp
DIGEST_FROM_EMAIL=news@example.com
DIGEST_TO_EMAIL=reader@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=news@example.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=true
```

SendGrid API example:

```bash
EMAIL_PROVIDER=sendgrid
DIGEST_FROM_EMAIL=news@example.com
DIGEST_TO_EMAIL=reader@example.com
SENDGRID_API_KEY=your-sendgrid-api-key
```

Optional digest settings:

```bash
DIGEST_MAX_ARTICLES=5
DIGEST_BASE_URL=https://your-domain.example
DIGEST_SEND_HOUR_UTC=8
DIGEST_LOCK_FILE=digest.lock
```

## Query Recent Summaries from SQLite

```python
from digest_data import DigestStore

store = DigestStore()
articles = store.get_recent_articles(hours=24, limit=10)
```

The query reads unique cached summaries:

```sql
SELECT article_hash, title, source, url, published_at, summary, sentiment, updated_at
FROM processed_articles
WHERE updated_at >= ?
ORDER BY updated_at DESC
LIMIT ?
```

## Build Email Content

```python
from digest_builder import build_digest_subject, build_html_digest, build_text_digest, rank_articles

articles = rank_articles(articles, limit=5)
subject = build_digest_subject()
html_body = build_html_digest(articles, subject)
text_body = build_text_digest(articles, subject)
```

Subject format:

```text
Daily AI News - 2026-04-30
```

The HTML template is deliberately simple: readable typography, article cards,
summary, sentiment, and source link. A plain-text fallback is generated for
email clients that block HTML.

## Send Email

SMTP:

```python
from email_sender import SMTPEmailSender

sender = SMTPEmailSender()
sender.send("reader@example.com", subject, html_body, text_body)
```

SendGrid:

```python
from email_sender import SendGridEmailSender

sender = SendGridEmailSender()
sender.send("reader@example.com", subject, html_body, text_body)
```

Configured provider:

```python
from email_sender import get_email_sender

sender = get_email_sender()
```

## Scheduled Digest Job

Run once:

```bash
python digest_job.py --provider smtp --max-articles 5
```

Dry run without sending:

```bash
python digest_job.py --dry-run
```

Cron, daily at 8:00 UTC:

```cron
0 8 * * * cd /opt/news-summarizer && /opt/news-summarizer/.venv/bin/python digest_job.py --provider smtp >> /var/log/news-summarizer-digest.log 2>&1
```

APScheduler:

```bash
python scheduler.py --include-digest --interval-minutes 60
```

The pipeline still runs on its interval. The digest is scheduled separately with
a daily cron trigger at `DIGEST_SEND_HOUR_UTC`.

## Avoid Duplicate Sends

Each recipient gets a deterministic `digest_id`:

```python
digest_id = sha256(f"{recipient}|{date}|{article_hashes}")
```

Before sending, `digest_job.py` checks:

```python
store.digest_already_sent(digest_id)
```

After delivery, it records:

```python
store.record_digest_attempt(..., status="sent")
```

This prevents duplicate sends for the same recipient, date, and article set.
The job also uses `digest.lock` so overlapping scheduled runs do not send twice.

## Retries and Failure Monitoring

`send_daily_digest()` retries transient delivery failures with simple exponential
backoff. Final failures are recorded in `digest_sends` with `status="failed"` and
logged through the same logging setup as the pipeline.

Basic monitoring:

```bash
tail -f pipeline.log
```

For systemd:

```bash
journalctl -u news-summarizer-digest.service -f
```

For alerts, start simple:

- alert on non-zero cron/systemd exits
- ship `pipeline.log` to CloudWatch, Datadog, or Grafana Loki
- add a Slack/email alert where `result["status"] == "partial_failure"`

## Subscription Support

Single-user mode:

- set `DIGEST_TO_EMAIL`
- no subscriber table management needed

Multi-user mode:

```python
from digest_data import DigestStore

store = DigestStore()
store.add_subscriber("reader@example.com")
subscribers = store.get_active_subscribers()
```

The `subscribers` table supports active/inactive users. A future web endpoint can
add subscribe/unsubscribe flows without changing the digest sender.

## Basic Analytics

The `digest_sends` table stores:

- `sent_at`
- `status`
- `provider`
- `error`
- `open_tracking_id`
- `opened_at`

FastAPI includes a placeholder tracking pixel endpoint:

```text
GET /api/digest/open/{digest_id}.gif
```

This updates `opened_at` when email clients load images. Treat open tracking as
approximate because many clients block or proxy images.

## Supabase/Postgres Extension

SQLite is enough for one VM and local development. Move to Supabase/Postgres
when you need:

- multiple app instances
- shared locking across machines
- subscriber management at larger scale
- analytics dashboards
- stronger migration tooling

Migration shape:

- `processed_articles` -> Postgres table with `article_hash` unique index
- `subscribers` -> Postgres table with auth/user metadata
- `digest_sends` -> Postgres table with unique `digest_id`
- file locks -> Postgres advisory locks or Redis locks

The code is already layered so `DigestStore` can be replaced by a Postgres-backed
implementation without changing `digest_builder.py` or `email_sender.py`.
