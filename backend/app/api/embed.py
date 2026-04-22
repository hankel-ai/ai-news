"""Minimal SSR endpoint for iframe embedding into hankel.ai."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Story

router = APIRouter(tags=["embed"])

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI News</title>
<style>
:root {{
  --bg: {bg};
  --bg2: {bg2};
  --text: {text_color};
  --text2: {text2};
  --accent: {accent};
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  padding: 12px;
}}
.story {{
  padding: 10px 12px;
  border-bottom: 1px solid var(--bg2);
}}
.story:last-child {{ border-bottom: none; }}
.story a {{
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
}}
.story a:hover {{ text-decoration: underline; }}
.meta {{
  font-size: 12px;
  color: var(--text2);
  margin-top: 2px;
}}
.empty {{
  text-align: center;
  padding: 40px 20px;
  color: var(--text2);
}}
</style>
</head>
<body>
{stories_html}
<script>
function notifyParent() {{
  window.parent.postMessage({{
    type: 'ai-news-resize',
    height: document.documentElement.scrollHeight
  }}, '*');
}}
notifyParent();
new ResizeObserver(notifyParent).observe(document.body);
</script>
</body>
</html>"""

DARK_PALETTE = {
    "bg": "#0f172a",
    "bg2": "#1e293b",
    "text_color": "#e2e8f0",
    "text2": "#94a3b8",
    "accent": "#60a5fa",
}

LIGHT_PALETTE = {
    "bg": "#ffffff",
    "bg2": "#f1f5f9",
    "text_color": "#1e293b",
    "text2": "#64748b",
    "accent": "#2563eb",
}


@router.get("/embed", response_class=HTMLResponse)
async def embed_view(
    limit: int = Query(20, ge=1, le=50),
    theme: str = Query("dark"),
    session: AsyncSession = Depends(get_session),
):
    palette = DARK_PALETTE if theme == "dark" else LIGHT_PALETTE

    stmt = (
        select(Story)
        .order_by(Story.first_seen_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        stories_html = '<div class="empty">No stories yet. Check back soon.</div>'
    else:
        parts = []
        for r in rows:
            source = _escape(r.source_name)
            title = _escape(r.title)
            ts = r.first_seen_at
            time_display = ts[:16].replace("T", " ") if ts else ""
            parts.append(
                f'<div class="story">'
                f'<a href="{_escape(r.url)}" target="_blank" rel="noopener">{title}</a>'
                f'<div class="meta">{source} &middot; {time_display}</div>'
                f'</div>'
            )
        stories_html = "\n".join(parts)

    html = TEMPLATE.format(stories_html=stories_html, **palette)
    return HTMLResponse(html)


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
