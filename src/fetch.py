"""Single shared HTTP fetch used by both chatbot detection and website-quality
checks, so each business's site is only requested once per run."""

import requests

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ChatbotLeadScout/1.0; "
        "+https://example.com/bot-info)"
    )
}


def fetch_site(website_url: str, timeout: int = 12) -> dict:
    """Return {'html': str, 'status': 'ok'|'dead'|'none', 'final_url': str}."""
    if not website_url:
        return {"html": "", "status": "none", "final_url": ""}

    url = website_url if website_url.startswith("http") else f"https://{website_url}"

    try:
        resp = requests.get(
            url, headers=REQUEST_HEADERS, timeout=timeout, allow_redirects=True
        )
    except requests.RequestException:
        return {"html": "", "status": "dead", "final_url": url}

    if resp.status_code >= 400:
        return {"html": "", "status": "dead", "final_url": url}

    return {"html": resp.text, "status": "ok", "final_url": resp.url}
