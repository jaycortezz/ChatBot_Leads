"""Hard-reset migration: seed output/dedup_history.json from *every*
agent-shaped CSV backup in output/, not just one Google Sheet.

This is the comprehensive version of src/seed_history.py - it covers runs
that never made it into any Sheet at all (e.g. crashed on an expired
OAuth token), and doesn't require hunting down the URLs of old,
disconnected sheets from earlier testing. Every run always writes a CSV
backup before attempting the Sheets write, so the CSVs are the complete
historical record regardless of what happened to any particular sheet.

Use this once for a clean reset: mark everyone already found (and likely
already emailed) as permanently captured, so no future run - into any
sheet, old or new - can ever resurface them.

Usage:
    python -m src.seed_history_from_csvs
"""

import csv
from pathlib import Path

from src.dedup_history import AGENTS_SCOPE, load_history, save_history
from src.util import normalize_domain

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def main():
    csv_paths = sorted(OUTPUT_DIR.glob("*.csv"))
    if not csv_paths:
        print(f"No CSV files found in {OUTPUT_DIR}.")
        return

    ids, emails, domains = set(), set(), set()
    skipped = []

    for path in csv_paths:
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))

        if not rows or "Direct Email" not in rows[0]:
            skipped.append(path.name)
            continue

        file_ids, file_emails, file_domains = 0, 0, 0
        for row in rows:
            place_id = row.get("Place ID", "")
            if place_id:
                ids.add(place_id)
                file_ids += 1
            email = (row.get("Direct Email") or "").strip().lower()
            if email:
                emails.add(email)
                file_emails += 1
            domain = normalize_domain(row.get("Website", ""))
            if domain:
                domains.add(domain)
                file_domains += 1

        print(f"  {path.name}: {len(rows)} rows ({file_ids} IDs, {file_emails} emails, {file_domains} domains)")

    if skipped:
        print(f"\nSkipped {len(skipped)} file(s) not shaped like an agent-leads CSV: {skipped}")

    if not (ids or emails or domains):
        print("\nNothing usable found across any CSV - nothing to seed.")
        return

    hist_ids, hist_emails, hist_domains = load_history(AGENTS_SCOPE)
    save_history(AGENTS_SCOPE, hist_ids | ids, hist_emails | emails, hist_domains | domains)

    print(
        f"\nSeeded {len(ids)} place IDs, {len(emails)} emails, {len(domains)} domains "
        f"across {len(csv_paths) - len(skipped)} file(s)."
    )
    print("Every future run will now permanently skip anyone already found in any past CSV.")


if __name__ == "__main__":
    main()
