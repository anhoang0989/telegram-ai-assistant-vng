"""
Build HTML self-contained report từ sections markdown.
Mobile-first CSS inline (không CDN, không JS) — mở được offline.
LLM (best: Claude Sonnet 4.6) gen sections content trước, service này chỉ wrap.
"""
import logging
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo
import markdown as md_lib

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Mobile-first inline CSS — không phụ thuộc CDN/JS, render được offline
_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue",
               Roboto, "Noto Sans", Arial, sans-serif;
  font-size: 16px;
  line-height: 1.65;
  color: #1a1a1a;
  background: #fafafa;
  margin: 0;
  padding: 16px;
  max-width: 760px;
  margin-left: auto;
  margin-right: auto;
}
@media (prefers-color-scheme: dark) {
  body { color: #e6e6e6; background: #121212; }
  hr { border-color: #333; }
  table { border-color: #333; }
  th, td { border-color: #333; }
  th { background: #1f1f1f; }
  code { background: #1f1f1f; }
  pre { background: #1f1f1f; }
  blockquote { border-color: #444; color: #bbb; }
  a { color: #6cb6ff; }
}
header.report-header {
  border-bottom: 2px solid #007acc;
  padding-bottom: 12px;
  margin-bottom: 24px;
}
header.report-header h1 {
  font-size: 1.6em;
  margin: 0 0 6px 0;
  line-height: 1.3;
  color: #007acc;
  word-break: break-word;
}
header.report-header .meta {
  color: #666;
  font-size: 0.9em;
}
section.report-section {
  margin: 28px 0;
  padding: 0;
}
section.report-section h2 {
  font-size: 1.25em;
  margin: 0 0 12px 0;
  padding-bottom: 6px;
  border-bottom: 1px solid #ddd;
  color: #111;
}
@media (prefers-color-scheme: dark) {
  section.report-section h2 { color: #f0f0f0; border-color: #333; }
}
h3, h4 { margin: 16px 0 8px 0; }
p { margin: 8px 0; }
ul, ol { padding-left: 24px; margin: 8px 0; }
li { margin: 4px 0; }
strong { font-weight: 700; }
em { font-style: italic; }
blockquote {
  border-left: 4px solid #007acc;
  padding: 4px 12px;
  margin: 12px 0;
  color: #555;
  background: rgba(0, 122, 204, 0.06);
}
code {
  background: #eee;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: 0.92em;
  word-break: break-word;
}
pre {
  background: #f0f0f0;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 0.9em;
}
pre code { background: none; padding: 0; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  display: block;
  overflow-x: auto;
}
th, td {
  border: 1px solid #ccc;
  padding: 8px 10px;
  text-align: left;
}
th { background: #f5f5f5; font-weight: 600; }
hr {
  border: 0;
  border-top: 1px solid #ddd;
  margin: 24px 0;
}
a { color: #007acc; }
img { max-width: 100%; height: auto; }
footer.report-footer {
  margin-top: 40px;
  padding-top: 12px;
  border-top: 1px solid #ddd;
  font-size: 0.85em;
  color: #888;
  text-align: center;
}
.summary-box {
  background: rgba(0, 122, 204, 0.08);
  border-left: 4px solid #007acc;
  padding: 12px 16px;
  margin: 0 0 24px 0;
  border-radius: 0 6px 6px 0;
  font-size: 0.95em;
}
"""


def _render_markdown(text: str) -> str:
    """Render markdown → safe HTML. Bật extensions cho bảng + fenced code."""
    return md_lib.markdown(
        text,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
        output_format="html5",
    )


def build_report(
    title: str,
    sections: list[dict],
    summary: str | None = None,
    audience: str | None = None,
    model_used: str | None = None,
) -> str:
    """
    sections: [{"heading": str, "content_markdown": str}, ...]
    Trả về full HTML string self-contained.
    """
    now = datetime.now(TZ)
    safe_title = escape(title or "Báo cáo")
    safe_audience = escape(audience or "")
    safe_model = escape(model_used or "")

    sections_html: list[str] = []
    for sec in sections or []:
        heading = escape(sec.get("heading") or "")
        body_md = sec.get("content_markdown") or ""
        body_html = _render_markdown(body_md)
        sections_html.append(
            f'<section class="report-section">'
            f'<h2>{heading}</h2>\n{body_html}\n'
            f'</section>'
        )

    summary_block = ""
    if summary:
        summary_block = (
            f'<div class="summary-box"><strong>📋 Tóm tắt:</strong> '
            f'{escape(summary)}</div>'
        )

    audience_line = (
        f' • 👥 Audience: {safe_audience}' if safe_audience else ''
    )
    model_line = (
        f' • 🤖 Model: {safe_model}' if safe_model else ''
    )

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<style>{_CSS}</style>
</head>
<body>
<header class="report-header">
  <h1>{safe_title}</h1>
  <div class="meta">🕐 {now.strftime('%d/%m/%Y %H:%M')} (giờ VN){audience_line}{model_line}</div>
</header>
{summary_block}
{''.join(sections_html)}
<footer class="report-footer">
  Tạo bởi Telegram AI Assistant • {now.year}
</footer>
</body>
</html>"""


def safe_filename(title: str) -> str:
    """Convert title → filename ASCII-only hợp lệ.
    Strip dấu tiếng Việt để file name portable trên mọi hệ điều hành.
    """
    import unicodedata
    # Decompose VN diacritics → strip combining marks → ASCII
    t = (title or "report").strip()
    t = unicodedata.normalize("NFKD", t)
    t = t.encode("ascii", "ignore").decode("ascii")
    t = "".join(c if c.isalnum() or c in "-_" else "_" for c in t)
    while "__" in t:
        t = t.replace("__", "_")
    t = t.strip("_")[:50] or "report"
    ts = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    return f"{t}_{ts}.html"
