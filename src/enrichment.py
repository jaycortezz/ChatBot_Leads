"""Email discovery: try scraping the business's own site first (free, no
quota), fall back to Hunter.io's domain-search endpoint only when scraping
comes up empty. Hunter calls are capped per run to protect the free tier -
check your actual quota at https://hunter.io/api-keys since plan limits
change over time.
"""

import re
import requests
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

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

# Common placeholder text left in form fields (e.g. <input placeholder="user@domain.com">)
# that isn't a real address - seen showing up identically across unrelated sites.
IGNORED_EXACT_EMAILS = {
    "user@domain.com",
    "email@domain.com",
    "email@example.com",
    "name@example.com",
    "your@email.com",
    "youremail@example.com",
    "yourname@domain.com",
    "info@example.com",
    "test@test.com",
}

CONTACT_PATHS = ["/contact", "/contact-us", "/contact.html", "/about", "/about-us"]

HUNTER_URL = "https://api.hunter.io/v2/domain-search"


def _is_valid_email(candidate: str) -> bool:
    domain = candidate.split("@")[-1].lower()
    if domain in IGNORED_EMAIL_DOMAINS:
        return False
    if candidate.lower() in IGNORED_EXACT_EMAILS:
        return False
    if any(candidate.lower().endswith(ext) for ext in (".png", ".jpg", ".gif", ".svg")):
        return False
    return True


def _all_emails(html: str) -> list[str]:
    """Every plausible email on the page, mailto: links first (strongest
    signal of a real contact address), then rendered text (not tag
    attributes like placeholder="..." so form field hints aren't mistaken
    for real addresses), deduped while preserving that priority order."""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    seen: set[str] = set()

    for link in soup.select('a[href^="mailto:"]'):
        address = link["href"][len("mailto:"):].split("?")[0].strip()
        if address and EMAIL_RE.fullmatch(address) and _is_valid_email(address):
            if address.lower() not in seen:
                found.append(address)
                seen.add(address.lower())

    visible_text = soup.get_text(" ")
    for match in EMAIL_RE.findall(visible_text):
        if _is_valid_email(match) and match.lower() not in seen:
            found.append(match)
            seen.add(match.lower())

    return found


# Generic role-inbox prefixes to deprioritize when we specifically want a
# named individual's direct address (e.g. selling to one agent, not a team).
GENERIC_LOCAL_PARTS = {
    "info", "sales", "team", "office", "contact", "admin", "support",
    "hello", "service", "help", "listings", "agent", "agents", "leasing",
    "inquiries", "inquiry", "marketing", "general", "frontdesk", "reception",
    "hi", "mail",
}

# Words that show up in real-estate business names but never in a person's
# own name, stripped out before matching a name against an email local-part.
_NAME_STOPWORDS = {
    "real", "estate", "realty", "realtor", "realtors", "group", "team",
    "llc", "inc", "and", "the", "properties", "property", "co", "pdx",
    "homes", "home",
}


def _name_tokens(name: str) -> set[str]:
    # Cut off trailing " | Team Name" / " - Brokerage" style suffixes before
    # tokenizing, so we match against the person's own name, not their firm.
    cleaned = re.split(r"[|–-]", name)[0]
    words = re.findall(r"[a-zA-Z]+", cleaned.lower())
    return {w for w in words if w not in _NAME_STOPWORDS and len(w) > 1}


def _score_email(email: str, name_tokens: set[str]) -> int:
    local = email.split("@")[0].lower()
    if local in GENERIC_LOCAL_PARTS:
        return -3
    local_tokens = set(re.findall(r"[a-z]+", local))
    return 2 if local_tokens & name_tokens else 0


def pick_direct_email(name: str, emails: list[str]) -> str:
    """Given every email found on a site, prefer the one most likely to be
    the named individual's own address over a generic role inbox."""
    if not emails:
        return ""
    tokens = _name_tokens(name)
    best_i, best_score = 0, _score_email(emails[0], tokens)
    for i, email in enumerate(emails[1:], 1):
        score = _score_email(email, tokens)
        if score > best_score:
            best_i, best_score = i, score
    return emails[best_i]


def find_direct_email_from_site(name: str, homepage_url: str, homepage_html: str) -> tuple[str, str]:
    """Checks the homepage first, scoring every candidate email against the
    agent's own name to prefer a personal address over a generic role
    inbox - checking a few common contact page paths too if the homepage
    only turns up something generic. Returns (email, source_note)."""
    tokens = _name_tokens(name)
    emails = _all_emails(homepage_html)
    best = pick_direct_email(name, emails)
    if best and _score_email(best, tokens) > 0:
        return best, "site scrape (direct match)"

    if homepage_url:
        parsed = urlparse(
            homepage_url if homepage_url.startswith("http") else f"https://{homepage_url}"
        )
        base = f"{parsed.scheme}://{parsed.netloc}"
        for path in CONTACT_PATHS:
            result = fetch_site(urljoin(base, path))
            if result["status"] != "ok":
                continue
            emails += _all_emails(result["html"])

    best = pick_direct_email(name, emails)
    if not best:
        return "", ""
    source = "site scrape (direct match)" if _score_email(best, tokens) > 0 else "site scrape (generic inbox)"
    return best, source


class HunterClient:
    def __init__(self, api_key: str, max_calls: int = 20):
        self.api_key = api_key
        self.max_calls = max_calls
        self.calls_made = 0

    def find_email(self, domain: str, prefer: str = "personal") -> str:
        """prefer: Hunter tags each result 'generic' (role inbox) or
        'personal' (named individual) - pass prefer='personal' when you
        specifically want a direct address, not any working inbox."""
        if not self.api_key or not domain:
            return ""
        if self.calls_made >= self.max_calls:
            return ""

        self.calls_made += 1
        try:
            resp = requests.get(
                HUNTER_URL,
                params={"domain": domain, "api_key": self.api_key, "limit": 10},
                timeout=15,
            )
        except requests.RequestException:
            return ""

        if resp.status_code != 200:
            return ""

        emails = resp.json().get("data", {}).get("emails", [])
        if not emails:
            return ""

        preferred = [e for e in emails if e.get("type") == prefer]
        best = preferred[0] if preferred else emails[0]
        return best.get("value", "")
