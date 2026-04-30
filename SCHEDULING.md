# Scheduled Pipeline Execution

## Architecture Overview

The project now separates execution concerns:

- `web_app.py`: FastAPI web interface and HTTP API only.
- `pipeline.py`: shared pipeline function used by web, CLI, cron, and scheduler.
- `scheduler.py`: standalone APScheduler process for periodic execution.
- `summarizer.py`: summarization, sentiment analysis, and SQLite article cache.

The scheduler should not live inside the FastAPI request path. Run it as a
separate process so web traffic and background jobs can scale, restart, and fail
independently.

## Scheduled Job Function

The shared entry point is `run_pipeline()`:

```python
from pipeline import run_pipeline

result = run_pipeline(
    category="technology",
    max_articles=5,
    async_processing=False,
)

print(result.status)
print(result.processed_articles)
```

`run_pipeline()` handles:

- fetching articles from NewsAPI
- processing articles through `NewsSummarizer`
- using the existing SQLite cache before LLM calls
- file locking to avoid duplicate runs
- logging success, skipped runs, and failures

## Duplicate Run Protection

`pipeline.py` uses an atomic lock file:

```python
with pipeline_lock(lock_file="pipeline.lock"):
    ...
```

If a previous run is still active, the next run returns `status="skipped"`.
If the lock is older than the stale timeout, it is removed and replaced.

This is enough for one VM. For multiple VMs or containers, move locking to
shared infrastructure such as Redis, Postgres advisory locks, or Celery's task
deduplication/queue controls.

## Cache Compatibility

The scheduled run calls the same `NewsSummarizer.summarize_article()` method as
the web UI. That method normalizes article text, hashes it, and checks SQLite
before calling OpenAI or Anthropic. Repeated articles are returned from cache
without reprocessing.

## Approach 1: Cron

Cron is the simplest production setup for one VM.

Run once:

```bash
python scheduler.py --run-once --category technology --max-articles 5
```

Cron entry for hourly runs:

```cron
0 * * * * cd /opt/news-summarizer && /opt/news-summarizer/.venv/bin/python scheduler.py --run-once --category technology --max-articles 5 >> /var/log/news-summarizer-cron.log 2>&1
```

Pros:

- simple
- reliable on one VM
- no app process required

Cons:

- limited visibility
- no built-in retry workflow
- not ideal for multiple workers or distributed deployments

## Approach 2: systemd Timer on a Cloud VM

Use this on Ubuntu/Debian VMs when you want better logs and service control than
cron.

`/etc/systemd/system/news-summarizer.service`:

```ini
[Unit]
Description=Run news summarizer pipeline

[Service]
Type=oneshot
WorkingDirectory=/opt/news-summarizer
EnvironmentFile=/opt/news-summarizer/.env
ExecStart=/opt/news-summarizer/.venv/bin/python scheduler.py --run-once --category technology --max-articles 5
```

`/etc/systemd/system/news-summarizer.timer`:

```ini
[Unit]
Description=Run news summarizer pipeline hourly

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now news-summarizer.timer
systemctl list-timers news-summarizer.timer
```

View logs:

```bash
journalctl -u news-summarizer.service -f
```

## Approach 3: APScheduler

`scheduler.py` runs a dedicated APScheduler process:

```bash
python scheduler.py --interval-minutes 60 --category technology --max-articles 5
```

The job is configured with:

```python
scheduler.add_job(
    scheduled_job,
    trigger=IntervalTrigger(minutes=60),
    id="news_summarizer_pipeline",
    replace_existing=True,
    max_instances=1,
    coalesce=True,
)
```

`max_instances=1` prevents overlapping jobs inside the scheduler process.
`pipeline.lock` protects against overlap from other processes.

Pros:

- scheduling logic is Python code
- easy local development
- good for a single app/worker process

Cons:

- the scheduler process must stay running
- not enough by itself for distributed execution
- missed runs depend on process uptime unless configured with persistent job stores

## When to Use Celery

Move to Celery, RQ, or another distributed task queue when:

- multiple web servers need to enqueue work
- jobs are long-running or high volume
- you need retries, backoff, dead-letter queues, or worker autoscaling
- you need stronger observability over task state
- you deploy across multiple VMs or containers

In that setup, FastAPI should enqueue a task, Celery workers should call
`run_pipeline()`, and Redis/Postgres/RabbitMQ should provide queue and lock
coordination.

## Monitoring Failures

Basic monitoring already exists through `pipeline.log`:

```bash
tail -f pipeline.log
```

For cron, redirect output:

```cron
0 * * * * cd /opt/news-summarizer && /opt/news-summarizer/.venv/bin/python scheduler.py --run-once >> /var/log/news-summarizer-cron.log 2>&1
```

For systemd, use:

```bash
journalctl -u news-summarizer.service --since "1 hour ago"
```

Simple alert options:

- configure your VM monitoring to alert on non-zero systemd service exits
- ship `pipeline.log` to CloudWatch, Datadog, Grafana Loki, or another log tool
- add an email/Slack webhook inside `scheduled_job()` when `result.status == "failed"`

Example alert hook:

```python
if result.status == "failed":
    logger.error("Scheduled pipeline failed: %s", result.error)
    # send_slack_alert(result.error)
```

Keep alerts low-noise: alert on failed runs, not skipped duplicate runs.
