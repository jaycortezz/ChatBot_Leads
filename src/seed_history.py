"""One-time migration: seed output/dedup_history.json from every tab in an
existing sheet's current content.

Useful for pulling an older, disconnected sheet's data into the current
cross-run dedup system (e.g. a sheet from before the "one active sheet,
new tab per run" model) - without this, a future run would have no memory
of whatever's already sitting there, and could re-add (or re-email) the
same agents again.

For a comprehensive reset covering *every* run you've ever done (not just
one sheet), use src/seed_history_from_csvs.py instead - it doesn't require
knowing a sheet's ID/URL at all.

Usage:
    python -m src.seed_history <sheet_id>
    python -m src.seed_history            # uses GOOGLE_SHEET_ID from .env
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.dedup_history import AGENTS_SCOPE, load_history, save_history


def main():
    load_dotenv()
    sheet_id = sys.argv[1] if len(sys.argv) > 1 else os.getenv("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        sys.exit("Usage: python -m src.seed_history <sheet_id>  (or set GOOGLE_SHEET_ID in .env)")

    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    if not Path(service_account_file).exists():
        service_account_file = None

    from src.sheets import SheetWriter  # imported lazily, matches src/main.py

    writer = SheetWriter(sheet_id=sheet_id, service_account_file=service_account_file)
    worksheets = writer.spreadsheet.worksheets()
    print(f"Reading from: {writer.spreadsheet.url}")
    print(f"Tabs found in this sheet: {[ws.title for ws in worksheets]}")

    ids, emails, domains = set(), set(), set()
    for ws in worksheets:
        tab_ids, tab_emails, tab_domains = writer._read_existing(ws)
        if not (tab_ids or tab_emails or tab_domains):
            continue
        print(f"  {ws.title}: {len(tab_ids)} place IDs, {len(tab_emails)} emails, {len(tab_domains)} domains")
        ids |= tab_ids
        emails |= tab_emails
        domains |= tab_domains

    if not (ids or emails or domains):
        print("No usable data found in any tab - nothing to seed.")
        return

    hist_ids, hist_emails, hist_domains = load_history(AGENTS_SCOPE)
    save_history(AGENTS_SCOPE, hist_ids | ids, hist_emails | emails, hist_domains | domains)
    print(f"\nSeeded {len(ids)} place IDs, {len(emails)} emails, {len(domains)} domains total.")
    print("Done. Future runs will now correctly skip anyone already captured here.")


if __name__ == "__main__":
    main()
