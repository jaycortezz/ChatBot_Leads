"""One-off cleanup: remove duplicate rows already sitting in a tab, matched
by a repeated email or website domain - not just a repeated Place ID.
Google Places sometimes lists the same real business/agent under two
different Place IDs (e.g. a personal listing and their brokerage's listing
pointing at the same site), which the tool's normal place_id-only dedup
doesn't catch. When two rows share an email/domain, keeps whichever one has
an email filled in (or the first one, if both/neither do) and deletes the
other.

Usage:
    python -m src.dedupe_sheet "Real Estate Agents"
    python -m src.dedupe_sheet "Buyer Leads" <sheet_id>   # override GOOGLE_SHEET_ID
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.util import normalize_domain


def main():
    load_dotenv()
    if len(sys.argv) < 2:
        sys.exit('Usage: python -m src.dedupe_sheet "<Tab Name>" [sheet_id]')

    tab_name = sys.argv[1]
    sheet_id = sys.argv[2] if len(sys.argv) > 2 else os.getenv("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        sys.exit("No sheet ID given and GOOGLE_SHEET_ID is not set in .env")

    import gspread
    from google.oauth2.service_account import Credentials

    from src.sheets import SCOPES

    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    if Path(service_account_file).exists():
        creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
        client = gspread.authorize(creds)
    else:
        client = gspread.oauth(scopes=SCOPES)

    spreadsheet = client.open_by_key(sheet_id)
    ws = spreadsheet.worksheet(tab_name)
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        print("Nothing to dedupe - tab is empty.")
        return

    header = all_values[0]
    email_col = "Direct Email" if "Direct Email" in header else "Email"
    if email_col not in header or "Website" not in header:
        sys.exit(f"Tab '{tab_name}' doesn't have the expected Email/Website columns.")
    email_idx = header.index(email_col)
    website_idx = header.index("Website")

    seen_emails: dict[str, int] = {}   # key -> 1-based sheet row number
    seen_domains: dict[str, int] = {}
    rows_to_delete: set[int] = set()

    for offset, row in enumerate(all_values[1:], start=2):
        email = row[email_idx].strip().lower() if len(row) > email_idx else ""
        domain = normalize_domain(row[website_idx]) if len(row) > website_idx else ""

        dup_of = seen_emails.get(email) if email else None
        if dup_of is None and domain:
            dup_of = seen_domains.get(domain)

        if dup_of is not None:
            existing_row = all_values[dup_of - 1]
            existing_has_email = len(existing_row) > email_idx and bool(existing_row[email_idx].strip())
            current_has_email = bool(email)

            if current_has_email and not existing_has_email:
                # This row is more complete - keep it, delete the earlier one instead.
                rows_to_delete.add(dup_of)
                seen_emails[email] = offset
                if domain:
                    seen_domains[domain] = offset
            else:
                rows_to_delete.add(offset)
            continue

        if email:
            seen_emails[email] = offset
        if domain:
            seen_domains[domain] = offset

    if not rows_to_delete:
        print("No duplicates found.")
        return

    print(f"Deleting {len(rows_to_delete)} duplicate row(s) (by sheet row number): {sorted(rows_to_delete)}")
    for row_num in sorted(rows_to_delete, reverse=True):
        ws.delete_rows(row_num)

    print("Done.")


if __name__ == "__main__":
    main()
