import re
from urllib.parse import urlparse


def normalize_domain(url: str) -> str:
    """Strip scheme/www/path down to a bare comparable domain, e.g.
    'https://www.proud-realty.com/agents/jeanne' -> 'proud-realty.com'."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = f"https://{url}"
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def sanitize_tab_name(name: str) -> str:
    """Google Sheets tab names can't contain [ ] * / \\ ? : , can't be
    blank, and are capped at 100 characters."""
    cleaned = re.sub(r'[\[\]*/\\?:]', "-", name).strip()
    return (cleaned or "Untitled")[:100]
