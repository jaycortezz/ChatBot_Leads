"""One-time migration: seed output/dedup_history.json from an existing
sheet's current content.

Needed because of the switch to "a brand-new sheet every run" - without
this, the very first run after that switch would have no memory of
whatever's already sitting in an older sheet you'd been reusing, and could
re-add (or re-email) the same agents/emails again in the new sheet. Run
this once against your existing sheet before your next run.

Usage:
    python -m src.seed_history <sheet_id>
    python -m src.seed_history            # uses GOOGLE_SHEET_ID from .env
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.dedup_history import load_history, save_history


def main():
    load_dotenv()
    sheet_id = sys.argv[1] if len(sys.argv) > 1 else os.getenv("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        sys.exit("Usage: python -m src.seed_history <sheet_id>  (or set GOOGLE_SHEET_ID in .env)")

    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    if not Path(service_account_file).exists():
        service_account_file = None

    import gspread

    from src.sheets import TAB_NAME, SheetWriter  # imported lazily, matches src/main.py

    writer = SheetWriter(sheet_id=sheet_id, service_account_file=service_account_file)
    print(f"Reading from: {writer.spreadsheet.url}")
    print(f"Tabs found in this sheet: {[ws.title for ws in writer.spreadsheet.worksheets()]}")

    try:
        ws = writer.spreadsheet.worksheet(TAB_NAME)
    except gspread.WorksheetNotFound:
        print(f"No '{TAB_NAME}' tab in this sheet - nothing to seed.")
        return

    ids, emails, domains = writer._read_existing(ws)
    if not (ids or emails or domains):
        print(f"'{TAB_NAME}' tab exists but has no data - nothing to seed.")
        return

    hist_ids, hist_emails, hist_domains = load_history(TAB_NAME)
    save_history(TAB_NAME, hist_ids | ids, hist_emails | emails, hist_domains | domains)
    print(f"Seeded {len(ids)} place IDs, {len(emails)} emails, {len(domains)} domains.")
    print("Done. Future runs (new sheets) will now correctly skip anyone already captured here.")


if __name__ == "__main__":
    main()
