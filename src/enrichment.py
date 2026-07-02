"""Email discovery: try scraping the business's own site first (free, no
quota), fall back to Hunter.io's domain-search endpoint only when scraping
comes up empty. Hunter calls are capped per run to protect the free tier -
check your actual quota at https://hunter.io/api-keys since plan limits
change over time.
"""

import re
import requests
from urllib.parse import urljoin, urlparse

from src.fetch import fetch_site

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

IGNORED_EMAIL_DOMAINS = {
    "sentry.io",
    "wixpress.com",
    "example.com",
    "godaddy.com",
    "schema.org",
    "w3.org",
}

CONTACT_PATHS = ["/contact", "/contact-us", "/contact.html", "/about", "/about-us"]

HUNTER_URL = "https://api.hunter.io/v2/domain-search"


def _extract_email(html: str) -> str:
    if not html:
        return ""
    for match in EMAIL_RE.findall(html):
        domain = match.split("@")[-1].lower()
        if domain in IGNORED_EMAIL_DOMAINS:
            continue
        if any(match.lower().endswith(ext) for ext in (".png", ".jpg", ".gif", ".svg")):
            continue
        return match
    return ""


def find_email_from_site(homepage_url: str, homepage_html: str) -> str:
    """Check the already-fetched homepage first, then a few common contact
    page paths on the same domain."""
    email = _extract_email(homepage_html)
    if email:
        return email

    if not homepage_url:
        return ""

    parsed = urlparse(
        homepage_url if homepage_url.startswith("http") else f"https://{homepage_url}"
    )
    base = f"{parsed.scheme}://{parsed.netloc}"

    for path in CONTACT_PATHS:
        result = fetch_site(urljoin(base, path))
        if result["status"] != "ok":
            continue
        email = _extract_email(result["html"])
        if email:
            return email

    return ""


class HunterClient:
    def __init__(self, api_key: str, max_calls: int = 20):
        self.api_key = api_key
        self.max_calls = max_calls
        self.calls_made = 0

    def find_email(self, domain: str) -> str:
        if not self.api_key or not domain:
            return ""
        if self.calls_made >= self.max_calls:
            return ""

        self.calls_made += 1
        try:
            resp = requests.get(
                HUNTER_URL,
                params={"domain": domain, "api_key": self.api_key, "limit": 1},
                timeout=15,
            )
        except requests.RequestException:
            return ""

        if resp.status_code != 200:
            return ""

        emails = resp.json().get("data", {}).get("emails", [])
        if not emails:
            return ""

        generic = [e for e in emails if e.get("type") == "generic"]
        best = generic[0] if generic else emails[0]
        return best.get("value", "")
