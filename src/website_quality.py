"""Heuristics for flagging a business's website as 'outdated' - a web-design
lead even though a site technically exists. This is a signal score, not a
certainty: we flag a site as outdated once enough independent red flags are
present, to avoid subjective single-signal judgment calls.
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup

PARKED_PAGE_PHRASES = [
    "domain is for sale",
    "buy this domain",
    "this domain is parked",
    "future home of something quite cool",
    "godaddy.com/domains",
    "web hosting coming soon",
    "site not yet configured",
]

STALE_TECH_MARKERS = [
    "powered by frontpage",
    "adobe flash",
    "<marquee",
    "<blink",
]

STALE_YEAR_THRESHOLD_YEARS = 4

PLATFORM_MARKERS = [
    ("wixstatic.com", "Wix"),
    ("wix.com", "Wix"),
    ("static1.squarespace", "Squarespace"),
    ("squarespace.com", "Squarespace"),
    ("godaddysites.com", "GoDaddy Website Builder"),
    ("weebly.com", "Weebly"),
    ("carrd.co", "Carrd"),
]


def detect_platform_hint(html: str) -> str:
    """Best-effort detection of a DIY site-builder platform - a soft signal
    (not proof) that a business hasn't invested in custom branding/photography,
    useful for prioritizing design outreach. Empty string means unknown/custom
    (e.g. WordPress or a bespoke build), not "no signal found = good site"."""
    if not html:
        return ""
    lowered = html.lower()
    for marker, label in PLATFORM_MARKERS:
        if marker in lowered:
            return label
    return ""


def assess_website(url: str, html: str, fetch_status: str) -> dict:
    """Return {'status': 'ok'|'outdated'|'dead'|'none', 'reasons': [str]}."""
    if fetch_status == "none":
        return {"status": "none", "reasons": ["no website on record"]}
    if fetch_status == "dead":
        return {"status": "dead", "reasons": ["website did not respond / errored"]}

    reasons = []

    if url and url.startswith("http://"):
        reasons.append("no HTTPS")

    lowered = html.lower()

    if not re.search(r'<meta[^>]+name=["\']viewport["\']', lowered):
        reasons.append("not mobile-responsive (no viewport meta tag)")

    for phrase in PARKED_PAGE_PHRASES:
        if phrase in lowered:
            reasons.append("looks like a parked/placeholder page")
            break

    for marker in STALE_TECH_MARKERS:
        if marker in lowered:
            reasons.append(f"uses outdated markup ({marker.strip('<')})")
            break

    year_match = re.search(r"(?:©|copyright)\D{0,6}(20[0-2]\d)", lowered)
    if year_match:
        year = int(year_match.group(1))
        if datetime.now().year - year >= STALE_YEAR_THRESHOLD_YEARS:
            reasons.append(f"footer copyright year is stale ({year})")

    soup = BeautifulSoup(html, "html.parser")
    visible_text = soup.get_text(strip=True)
    if len(visible_text) < 200:
        reasons.append("very little content (likely a placeholder page)")

    status = "outdated" if len(reasons) >= 2 else "ok"
    return {"status": status, "reasons": reasons}
