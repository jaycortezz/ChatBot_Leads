"""Remembers which Google Sheet is "the" active one across runs, so the
default behavior is one persistent sheet with a new tab per run - not a
new spreadsheet every time. Local only (output/active_sheet.json,
gitignored) - not committed, machine-specific.
"""

import json
from pathlib import Path

ACTIVE_SHEET_PATH = Path(__file__).resolve().parent.parent / "output" / "active_sheet.json"


def load_active_sheet() -> dict | None:
    if not ACTIVE_SHEET_PATH.exists():
        return None
    return json.loads(ACTIVE_SHEET_PATH.read_text())


def save_active_sheet(sheet_id: str, url: str) -> None:
    ACTIVE_SHEET_PATH.parent.mkdir(exist_ok=True)
    ACTIVE_SHEET_PATH.write_text(json.dumps({"sheet_id": sheet_id, "url": url}, indent=2))
