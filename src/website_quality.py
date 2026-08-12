"""Soft, best-effort signals read off an agent's own website - not hard
filters. There's no free/reliable way to pull live MLS listing counts per
agent (that data lives behind Zillow/Realtor.com/MLS systems that block
scraping or require a paid broker data feed), so these are proxies to help
prioritize outreach, not proof of anything.
"""

import re

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
    (not proof) that an agent hasn't invested in custom branding/photography,
    useful for prioritizing design outreach. Empty string means unknown/custom
    (e.g. WordPress or a bespoke build), not "no signal found = good site"."""
    if not html:
        return ""
    lowered = html.lower()
    for marker, label in PLATFORM_MARKERS:
        if marker in lowered:
            return label
    return ""


IDX_MARKERS = [
    ("idxbroker", "IDX Broker"),
    ("sparkplatform", "Spark API / Flexmls"),
    ("flexmls", "Spark API / Flexmls"),
    ("showcaseidx", "Showcase IDX"),
    ("realgeeks", "Real Geeks"),
    ("boomtownroi", "BoomTown"),
    ("kvcore", "kvCORE"),
    ("chime.me", "Chime"),
    ("cincpro", "CINC"),
    ("diverse solutions", "Diverse Solutions"),
    ("propertypanorama", "PropertyPanorama"),
]

MLS_NUMBER_RE = re.compile(r"\bMLS\s*(?:#|No\.?|Number|ID)?\s*[:#]?\s*\d{5,}\b", re.IGNORECASE)


def detect_active_listings_hint(html: str) -> str:
    """Best-effort signal that a site is actually showing live listings, not
    a guarantee - a widget can be installed with zero current listings, and
    some brokerage-hosted sites show listings with none of these markers.
    Useful for sorting/prioritizing, not for hard-filtering someone out."""
    if not html:
        return ""
    lowered = html.lower()
    for marker, label in IDX_MARKERS:
        if marker in lowered:
            return f"IDX widget ({label})"
    if MLS_NUMBER_RE.search(html):
        return "MLS# found on page"
    return ""
