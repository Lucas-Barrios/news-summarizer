"""Build daily digest email content."""
import html
import re
from datetime import date


def build_digest_subject(run_date=None):
    """Build the daily digest subject line."""
    run_date = run_date or date.today()
    return f"Daily AI News - {run_date:%Y-%m-%d}"


def rank_articles(articles, limit=5):
    """Rank and truncate articles for digest delivery."""
    return sorted(
        articles,
        key=lambda article: article.get("published_at") or article.get("updated_at") or "",
        reverse=True,
    )[:limit]


def plain_text_preview(text, max_length=220):
    """Collapse and truncate text for email display."""
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 1].rstrip()}..."


def build_html_digest(articles, subject, tracking_pixel_url=None):
    """Build a clean HTML digest email."""
    article_blocks = []

    for index, article in enumerate(articles, 1):
        title = html.escape(article.get("title") or "Untitled")
        source = html.escape(article.get("source") or "Unknown")
        published_at = html.escape(article.get("published_at") or "No date")
        summary = html.escape(plain_text_preview(article.get("summary"), 520))
        sentiment = html.escape(plain_text_preview(article.get("sentiment"), 260))
        url = html.escape(article.get("url") or "#")

        article_blocks.append(
            f"""
            <tr>
              <td style="padding: 22px 0; border-top: 1px solid #d9e0e8;">
                <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">
                  {index}. {source} · {published_at}
                </div>
                <h2 style="margin: 0 0 10px; font-size: 19px; line-height: 1.35; color: #17202a;">
                  {title}
                </h2>
                <p style="margin: 0 0 12px; color: #334155; line-height: 1.55;">
                  {summary}
                </p>
                <div style="margin: 0 0 14px; padding: 12px; background: #f0f4f8;
                  border-radius: 8px; color: #334155; line-height: 1.5;">
                  <strong>Sentiment:</strong> {sentiment}
                </div>
                <a href="{url}" style="color: #0f766e; font-weight: 700;">Read source</a>
              </td>
            </tr>
            """
        )

    tracking_pixel = ""
    if tracking_pixel_url:
        tracking_pixel = (
            f'<img src="{html.escape(tracking_pixel_url)}" alt="" width="1" '
            'height="1" style="display:none;">'
        )

    return f"""
    <!doctype html>
    <html>
      <body style="margin: 0; background: #f6f7f9; font-family: Arial, sans-serif;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
          style="background: #f6f7f9; padding: 28px 12px;">
          <tr>
            <td align="center">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                style="max-width: 720px; background: #ffffff; border: 1px solid #d9e0e8;
                border-radius: 8px; padding: 30px;">
                <tr>
                  <td>
                    <div style="font-size: 13px; color: #0f766e; font-weight: 700;
                      margin-bottom: 8px;">
                      News Summarizer
                    </div>
                    <h1 style="margin: 0 0 8px; font-size: 26px; color: #17202a;">
                      {html.escape(subject)}
                    </h1>
                    <p style="margin: 0 0 18px; color: #64748b;">
                      Top summarized articles from the last 24 hours.
                    </p>
                  </td>
                </tr>
                {''.join(article_blocks)}
              </table>
            </td>
          </tr>
        </table>
        {tracking_pixel}
      </body>
    </html>
    """


def build_text_digest(articles, subject):
    """Build a plain-text fallback digest."""
    lines = [subject, "", "Top summarized articles from the last 24 hours.", ""]

    for index, article in enumerate(articles, 1):
        lines.extend(
            [
                f"{index}. {article.get('title') or 'Untitled'}",
                f"Source: {article.get('source') or 'Unknown'}",
                f"URL: {article.get('url') or ''}",
                "",
                plain_text_preview(article.get("summary"), 520),
                "",
                f"Sentiment: {plain_text_preview(article.get('sentiment'), 260)}",
                "",
                "-" * 72,
                "",
            ]
        )

    return "\n".join(lines)
