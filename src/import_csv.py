"""Recovery tool: upload an already-generated CSV backup to the Google
Sheet without re-running Places search/enrichment. Useful when the Sheets
write step fails after a run already produced output/*.csv (e.g. an
expired OAuth token) - avoids re-paying for and re-running the whole search
just to get data that was already successfully collected.

Usage:
    python -m src.import_csv output/real_estate_agents_Portland_OR_20260811_145320.csv
    python -m src.import_csv output/some_leads_run.csv <sheet_id>   # override GOOGLE_SHEET_ID
"""

import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.models import AgentLead, Lead


def _load_agent_leads(rows: list[dict]) -> list[AgentLead]:
    return [
        AgentLead(
            place_id=r["Place ID"],
            name=r["Agent / Business Name"],
            email=r["Direct Email"],
            email_source=r["Email Source"],
            phone=r["Phone"],
            website=r["Website"],
            address=r["Address"],
            city=r["City"],
            platform_hint=r["Site Platform Hint"],
            notes=r["Notes"],
        )
        for r in rows
    ]


def _load_leads(rows: list[dict]) -> list[Lead]:
    return [
        Lead(
            place_id=r["Place ID"],
            name=r["Business Name"],
            industry=r["Industry"],
            address=r["Address"],
            phone=r["Phone"],
            website=r["Website"],
            email=r["Email"],
            email_source=r["Email Source"],
            city=r["City"],
            has_website=bool(r["Website"]),
            website_status=r["Website Status"],
            chatbot_detected=r["Chatbot Detected"] == "Yes",
            chatbot_vendor=r["Chatbot Vendor"],
            category=r["Category"],
            notes=r["Notes"],
        )
        for r in rows
    ]


def main():
    load_dotenv()
    if len(sys.argv) < 2:
        sys.exit("Usage: python -m src.import_csv <path-to-csv> [sheet_id]")

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        sys.exit(f"File not found: {csv_path}")

    sheet_id = sys.argv[2] if len(sys.argv) > 2 else os.getenv("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        sys.exit("No sheet ID given and GOOGLE_SHEET_ID is not set in .env")

    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        sys.exit("CSV has no data rows.")

    is_agent_csv = "Direct Email" in rows[0]

    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    if not Path(service_account_file).exists():
        service_account_file = None

    from src.sheets import SheetWriter  # imported lazily, matches src/main.py

    writer = SheetWriter(sheet_id=sheet_id, service_account_file=service_account_file)

    if is_agent_csv:
        written = writer.write_agent_leads(_load_agent_leads(rows))
    else:
        written = writer.write_leads(_load_leads(rows))

    print("Written to Google Sheet:")
    for tab, count in written.items():
        print(f"  {tab}: {count} new rows")


if __name__ == "__main__":
    main()
