"""FastAPI web interface for the news summarizer."""
import asyncio
from datetime import datetime, timezone
import sqlite3
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from config import Config
from analytics import AnalyticsStore
from pipeline import run_pipeline


app = FastAPI(title="News Summarizer", version="1.0.0")


class SummarizeRequest(BaseModel):
    """Request payload for article summarization."""

    category: Literal["technology", "business", "health", "general"] = "technology"
    num_articles: int = Field(default=3, ge=1, le=10)
    async_processing: bool = False


def get_cache_stats():
    """Return simple cache statistics."""
    try:
        with sqlite3.connect(Config.CACHE_DB_PATH) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM processed_articles"
            ).fetchone()[0]
    except sqlite3.Error:
        count = 0

    return {"cached_articles": count}


@app.get("/", response_class=HTMLResponse)
def index():
    """Render the web interface."""
    return HTMLResponse(INDEX_HTML)


@app.get("/api/cache-stats")
def cache_stats():
    """Return cache statistics."""
    return get_cache_stats()


@app.post("/api/analytics/extract-topics")
async def extract_topics(window_hours: int = 24, category: str | None = None):
    """Extract and store topics for recent processed articles."""
    try:
        result = await asyncio.to_thread(
            AnalyticsStore().extract_and_store_topics,
            since_hours=window_hours,
            category=category,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return result


@app.get("/api/analytics/trending-topics")
def trending_topics(
    window_hours: int = 24,
    limit: int = 10,
    source: str | None = None,
    category: str | None = None,
):
    """Return charts-ready trending topic analytics."""
    if window_hours not in {24, 168, 720}:
        raise HTTPException(
            status_code=400,
            detail="window_hours must be one of 24, 168, or 720",
        )

    limit = max(1, min(50, limit))
    try:
        return AnalyticsStore().calculate_trending_topics(
            window_hours=window_hours,
            limit=limit,
            source=source,
            category=category,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/digest/open/{digest_id}.gif")
def track_digest_open(digest_id: str):
    """Placeholder open-tracking pixel endpoint."""
    try:
        with sqlite3.connect(Config.CACHE_DB_PATH) as connection:
            connection.execute(
                """
                UPDATE digest_sends
                SET opened_at = ?
                WHERE open_tracking_id = ?
                """,
                (datetime.now(timezone.utc).isoformat(), digest_id),
            )
    except sqlite3.Error:
        pass

    pixel = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
        b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
        b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
        b"D\x01\x00;"
    )
    return Response(content=pixel, media_type="image/gif")


@app.post("/api/summarize")
async def summarize(payload: SummarizeRequest):
    """Fetch, summarize, and analyze news articles."""
    try:
        run_result = await asyncio.to_thread(
            run_pipeline,
            category=payload.category,
            max_articles=payload.num_articles,
            async_processing=payload.async_processing,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if run_result.status == "failed":
        raise HTTPException(status_code=500, detail=run_result.error)

    if run_result.status == "skipped":
        raise HTTPException(status_code=409, detail=run_result.error)

    return {
        "category": run_result.category,
        "requested_articles": run_result.requested_articles,
        "fetched_articles": run_result.fetched_articles,
        "processed_articles": run_result.processed_articles,
        "async_processing": run_result.async_processing,
        "results": run_result.results,
        "cost_summary": run_result.cost_summary,
        "cache": get_cache_stats(),
    }


INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>News Summarizer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --panel-soft: #f0f4f8;
      --text: #17202a;
      --muted: #5b6472;
      --line: #d9e0e8;
      --accent: #0f766e;
      --accent-dark: #115e59;
      --warning: #b45309;
      --danger: #b91c1c;
      --shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
    }

    button,
    input,
    select {
      font: inherit;
    }

    .app-shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
    }

    .sidebar {
      border-right: 1px solid var(--line);
      background: #ffffff;
      padding: 28px;
      position: sticky;
      top: 0;
      height: 100vh;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 32px;
    }

    .brand-mark {
      width: 38px;
      height: 38px;
      border-radius: 8px;
      background: var(--accent);
      color: #ffffff;
      display: grid;
      place-items: center;
      font-weight: 800;
    }

    .brand h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.1;
      letter-spacing: 0;
    }

    .brand p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }

    .control-group {
      margin-bottom: 18px;
    }

    label {
      display: block;
      margin-bottom: 7px;
      color: #334155;
      font-size: 13px;
      font-weight: 650;
    }

    select,
    input[type="number"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--text);
      padding: 11px 12px;
      min-height: 44px;
      outline: none;
    }

    select:focus,
    input[type="number"]:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12);
    }

    .toggle-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-soft);
    }

    .toggle-row span {
      font-size: 14px;
      font-weight: 650;
    }

    .switch {
      position: relative;
      width: 48px;
      height: 28px;
      flex: 0 0 auto;
    }

    .switch input {
      opacity: 0;
      width: 0;
      height: 0;
    }

    .slider {
      position: absolute;
      cursor: pointer;
      inset: 0;
      background: #cbd5e1;
      border-radius: 999px;
      transition: 160ms ease;
    }

    .slider::before {
      content: "";
      position: absolute;
      width: 22px;
      height: 22px;
      left: 3px;
      top: 3px;
      background: #ffffff;
      border-radius: 50%;
      transition: 160ms ease;
      box-shadow: 0 2px 8px rgba(15, 23, 42, 0.2);
    }

    .switch input:checked + .slider {
      background: var(--accent);
    }

    .switch input:checked + .slider::before {
      transform: translateX(20px);
    }

    .primary-button {
      width: 100%;
      border: 0;
      border-radius: 8px;
      min-height: 46px;
      color: #ffffff;
      background: var(--accent);
      font-weight: 750;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }

    .primary-button:hover {
      background: var(--accent-dark);
    }

    .primary-button:disabled {
      cursor: wait;
      background: #8aa7a3;
    }

    .main {
      min-width: 0;
      padding: 28px;
    }

    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 20px;
      margin-bottom: 22px;
    }

    .topbar h2 {
      margin: 0;
      font-size: 28px;
      letter-spacing: 0;
    }

    .topbar p {
      margin: 6px 0 0;
      color: var(--muted);
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(130px, 1fr));
      gap: 12px;
      margin-bottom: 22px;
    }

    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: var(--shadow);
    }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }

    .metric strong {
      display: block;
      margin-top: 8px;
      font-size: 22px;
    }

    .status {
      margin-bottom: 16px;
      min-height: 22px;
      color: var(--muted);
      font-weight: 650;
    }

    .status.error {
      color: var(--danger);
    }

    .results {
      display: grid;
      gap: 14px;
    }

    .article-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      box-shadow: var(--shadow);
    }

    .article-head {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      margin-bottom: 12px;
    }

    .article-card h3 {
      margin: 0;
      font-size: 18px;
      line-height: 1.35;
    }

    .article-meta {
      color: var(--muted);
      font-size: 13px;
      margin-top: 6px;
    }

    .badge {
      flex: 0 0 auto;
      align-self: flex-start;
      border-radius: 999px;
      background: #e0f2f1;
      color: #0f766e;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 800;
    }

    .section-label {
      margin: 16px 0 6px;
      color: #334155;
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }

    .article-card p {
      margin: 0;
      color: #243244;
      line-height: 1.55;
      white-space: pre-wrap;
    }

    .article-card a {
      color: var(--accent-dark);
      font-weight: 700;
      word-break: break-word;
    }

    .empty-state {
      border: 1px dashed #bac6d3;
      border-radius: 8px;
      padding: 40px 24px;
      text-align: center;
      color: var(--muted);
      background: #ffffff;
    }

    .spinner {
      width: 16px;
      height: 16px;
      border-radius: 50%;
      border: 2px solid rgba(255, 255, 255, 0.55);
      border-top-color: #ffffff;
      display: none;
      animation: spin 800ms linear infinite;
    }

    .primary-button[aria-busy="true"] .spinner {
      display: inline-block;
    }

    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }

    @media (max-width: 860px) {
      .app-shell {
        grid-template-columns: 1fr;
      }

      .sidebar {
        position: static;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }

      .metrics {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .topbar,
      .article-head {
        flex-direction: column;
      }
    }

    @media (max-width: 520px) {
      .sidebar,
      .main {
        padding: 20px;
      }

      .metrics {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">NS</div>
        <div>
          <h1>News Summarizer</h1>
          <p>Multi-provider edition</p>
        </div>
      </div>

      <form id="summary-form">
        <div class="control-group">
          <label for="category">Category</label>
          <select id="category" name="category">
            <option value="technology">Technology</option>
            <option value="business">Business</option>
            <option value="health">Health</option>
            <option value="general">General</option>
          </select>
        </div>

        <div class="control-group">
          <label for="num_articles">Articles</label>
          <input id="num_articles" name="num_articles" type="number" min="1" max="10" value="3">
        </div>

        <div class="control-group">
          <div class="toggle-row">
            <span>Concurrent processing</span>
            <label class="switch" aria-label="Concurrent processing">
              <input id="async_processing" name="async_processing" type="checkbox">
              <span class="slider"></span>
            </label>
          </div>
        </div>

        <button class="primary-button" id="submit-button" type="submit">
          <span class="spinner" aria-hidden="true"></span>
          <span id="button-text">Process Articles</span>
        </button>
      </form>
    </aside>

    <main class="main">
      <div class="topbar">
        <div>
          <h2>Article Intelligence</h2>
          <p>Summaries, sentiment analysis, cost tracking, and SQLite caching in one workflow.</p>
        </div>
      </div>

      <section class="metrics" aria-label="Summary metrics">
        <div class="metric">
          <span>Processed</span>
          <strong id="metric-processed">0</strong>
        </div>
        <div class="metric">
          <span>Requests</span>
          <strong id="metric-requests">0</strong>
        </div>
        <div class="metric">
          <span>Cost</span>
          <strong id="metric-cost">$0.0000</strong>
        </div>
        <div class="metric">
          <span>Cache</span>
          <strong id="metric-cache">0</strong>
        </div>
      </section>

      <div class="status" id="status">Ready.</div>
      <section class="results" id="results">
        <div class="empty-state">
          Choose a category and process articles to populate the report.
        </div>
      </section>
    </main>
  </div>

  <script>
    const form = document.querySelector("#summary-form");
    const button = document.querySelector("#submit-button");
    const buttonText = document.querySelector("#button-text");
    const statusEl = document.querySelector("#status");
    const resultsEl = document.querySelector("#results");

    const metricProcessed = document.querySelector("#metric-processed");
    const metricRequests = document.querySelector("#metric-requests");
    const metricCost = document.querySelector("#metric-cost");
    const metricCache = document.querySelector("#metric-cache");

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function setLoading(isLoading) {
      button.disabled = isLoading;
      button.setAttribute("aria-busy", String(isLoading));
      buttonText.textContent = isLoading ? "Processing..." : "Process Articles";
    }

    function updateMetrics(data) {
      metricProcessed.textContent = data.processed_articles ?? 0;
      metricRequests.textContent = data.cost_summary?.total_requests ?? 0;
      metricCost.textContent = `$${Number(data.cost_summary?.total_cost ?? 0).toFixed(4)}`;
      metricCache.textContent = data.cache?.cached_articles ?? 0;
    }

    function renderResults(results) {
      if (!results.length) {
        resultsEl.innerHTML = '<div class="empty-state">No articles were processed.</div>';
        return;
      }

      resultsEl.innerHTML = results.map((article, index) => `
        <article class="article-card">
          <div class="article-head">
            <div>
              <h3>${index + 1}. ${escapeHtml(article.title)}</h3>
              <div class="article-meta">
                ${escapeHtml(article.source)} · ${escapeHtml(article.published_at || "No date")}
              </div>
            </div>
            <div class="badge">Analyzed</div>
          </div>
          <div class="section-label">Summary</div>
          <p>${escapeHtml(article.summary)}</p>
          <div class="section-label">Sentiment</div>
          <p>${escapeHtml(article.sentiment)}</p>
          <div class="section-label">Source</div>
          <a href="${escapeHtml(article.url)}" target="_blank" rel="noreferrer">
            ${escapeHtml(article.url)}
          </a>
        </article>
      `).join("");
    }

    async function refreshCacheStats() {
      const response = await fetch("/api/cache-stats");
      if (!response.ok) return;
      const data = await response.json();
      metricCache.textContent = data.cached_articles ?? 0;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      statusEl.className = "status";
      statusEl.textContent = "Fetching articles and running LLM analysis...";
      setLoading(true);

      const payload = {
        category: document.querySelector("#category").value,
        num_articles: Number(document.querySelector("#num_articles").value),
        async_processing: document.querySelector("#async_processing").checked,
      };

      try {
        const response = await fetch("/api/summarize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Request failed");
        }

        updateMetrics(data);
        renderResults(data.results || []);
        statusEl.textContent =
          `Fetched ${data.fetched_articles} article(s), processed ${data.processed_articles}.`;
      } catch (error) {
        statusEl.className = "status error";
        statusEl.textContent = error.message;
      } finally {
        setLoading(false);
      }
    });

    refreshCacheStats();
  </script>
</body>
</html>
"""
