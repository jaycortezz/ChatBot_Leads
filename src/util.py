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
