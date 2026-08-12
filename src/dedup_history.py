"""Cross-run duplicate memory.

Every run creates a brand-new Google Sheet (see src/main.py), so there's no
single persistent sheet left to check "have I already added/emailed this
business?" against - a fresh sheet starts empty every time. This local file
is that memory instead: it's checked and updated the same way live sheet
content used to be, keyed by tab/scope name (e.g. "Real Estate Agents"),
so a business, email, or website domain captured in any past run still
won't be re-added (or re-emailed) by a later one, even though it's now
landing in a different sheet each time.

Not committed to git (see .gitignore) - it's local run state, specific to
whatever leads you've actually already collected on this machine.
"""

import json
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent.parent / "output" / "dedup_history.json"

# Fixed regardless of which sheet/tab a run's results land in - this is
# what cross-run dedup keys off of, not any particular sheet or tab name.
AGENTS_SCOPE = "Real Estate Agents"


def _read_all() -> dict:
    if not HISTORY_PATH.exists():
        return {}
    return json.loads(HISTORY_PATH.read_text())


def load_history(scope: str) -> tuple[set, set, set]:
    """Returns (place_ids, emails, domains) seen for this scope across all
    past runs."""
    entry = _read_all().get(scope, {})
    return (
        set(entry.get("place_ids", [])),
        set(entry.get("emails", [])),
        set(entry.get("domains", [])),
    )


def save_history(scope: str, place_ids: set, emails: set, domains: set) -> None:
    data = _read_all()
    data[scope] = {
        "place_ids": sorted(place_ids),
        "emails": sorted(emails),
        "domains": sorted(domains),
    }
    HISTORY_PATH.parent.mkdir(exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(data, indent=2))
