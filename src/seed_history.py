"""One-time migration: seed output/dedup_history.json from an existing
sheet's current content.

Needed because of the switch to "a brand-new sheet every run" - without
this, the very first run after that switch would have no memory of
whatever's already sitting in an older sheet you'd been reusing, and could
re-add (or re-email) the same businesses/emails again in the new sheet.
Run this once against your existing sheet before your next run.

Usage:
    python -m src.seed_history <sheet_id>
    python -m src.seed_history            # uses GOOGLE_SHEET_ID from .env
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.dedup_history import load_history, save_history

KNOWN_TABS = ["Buyer Leads", "Web Design Leads", "Has Chatbot (Reference)", "Real Estate Agents"]


def main():
    load_dotenv()
    sheet_id = sys.argv[1] if len(sys.argv) > 1 else os.getenv("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        sys.exit("Usage: python -m src.seed_history <sheet_id>  (or set GOOGLE_SHEET_ID in .env)")

    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    if not Path(service_account_file).exists():
        service_account_file = None

    import gspread

    from src.sheets import SheetWriter  # imported lazily, matches src/main.py

    writer = SheetWriter(sheet_id=sheet_id, service_account_file=service_account_file)
    print(f"Reading from: {writer.spreadsheet.url}")
    print(f"Tabs found in this sheet: {[ws.title for ws in writer.spreadsheet.worksheets()]}")

    seeded_any = False
    for tab_name in KNOWN_TABS:
        try:
            ws = writer.spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            print(f"  {tab_name}: no such tab in this sheet - skipping")
            continue

        ids, emails, domains = writer._read_existing(ws, [])
        if not (ids or emails or domains):
            print(f"  {tab_name}: tab exists but has no data - nothing to seed")
            continue

        hist_ids, hist_emails, hist_domains = load_history(tab_name)
        save_history(tab_name, hist_ids | ids, hist_emails | emails, hist_domains | domains)
        print(f"  {tab_name}: seeded {len(ids)} place IDs, {len(emails)} emails, {len(domains)} domains")
        seeded_any = True

    if not seeded_any:
        print("No known tabs with data found in that sheet - nothing to seed.")
    else:
        print("Done. Future runs (new sheets) will now correctly skip anyone already captured here.")


if __name__ == "__main__":
    main()
