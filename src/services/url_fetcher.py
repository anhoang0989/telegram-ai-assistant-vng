"""
Fetch URL → extract main text (article/article-like content).
Dùng httpx + BeautifulSoup. Strip script/style/nav/footer/ads.
"""
import logging
import re
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_HTML_BYTES = 5 * 1024 * 1024   # 5MB raw HTML cap
MAX_TEXT_CHARS = 30_000             # truncate output cho LLM
TIMEOUT_SEC = 15

# User-Agent để tránh bị block bởi 1 số CDN
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TelegramAIBot/1.0; +https://t.me/your_bot)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "vi,en;q=0.9",
}

URL_RE = re.compile(r"https?://[^\s<>\"'\)]+", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?)\"'"


def extract_urls(text: str, limit: int = 2) -> list[str]:
    """Extract URLs từ text (max `limit` URL đầu tiên).
    Strip trailing punct để tránh '.' hay ',' bám vào URL."""
    raw = URL_RE.findall(text or "")
    return [u.rstrip(_TRAILING_PUNCT) for u in raw][:limit]


async def fetch_url(url: str) -> tuple[str, str]:
    """Returns (text, title). Raise nếu fail.
    text là main content, đã strip nav/footer/script/style.
    """
    async with httpx.AsyncClient(
        headers=_HEADERS,
        timeout=TIMEOUT_SEC,
        follow_redirects=True,
        max_redirects=5,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            # Plain text or other → return as-is
            text = resp.text[:MAX_TEXT_CHARS]
            return text, url[:100]

        if len(resp.content) > MAX_HTML_BYTES:
            raise ValueError(f"HTML quá lớn ({len(resp.content)/1024/1024:.1f}MB)")

        html = resp.text

    return _parse_html(html, url)


def _parse_html(html: str, url: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()[:200]
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            title = og["content"].strip()[:200]
    if not title:
        title = url[:100]

    # Strip noise
    for tag in soup(["script", "style", "noscript", "iframe", "nav", "footer",
                     "header", "aside", "form", "button"]):
        tag.decompose()

    # Prefer main / article tag
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text(separator="\n", strip=True)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n\n…(truncated, original {len(text):,} chars)"
    return text, title
