"""CLI entrypoint: find businesses via Google Places, classify them as
chatbot-buyer leads or web-design leads, enrich contact info, and write
results to a Google Sheet (plus always a local CSV backup).

Usage:
    python -m src.main --industry real_estate --city "Portland, OR" --limit 50
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.enrichment import HunterClient, find_email_from_site
from src.chatbot_detect import detect_chatbot
from src.fetch import fetch_site
from src.models import Lead
from src.places import PlacesClient
from src.website_quality import assess_website

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "industries.json"
OUTPUT_DIR = ROOT / "output"


def load_industries() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def parse_args(industries: dict) -> argparse.Namespace:
    choices = [k for k, v in industries.items() if not k.startswith("_")]
    parser = argparse.ArgumentParser(description="Find chatbot-buyer and web-design leads.")
    parser.add_argument("--industry", choices=choices, default="real_estate")
    parser.add_argument("--city", required=True, help='e.g. "Portland, OR"')
    parser.add_argument("--limit", type=int, default=50, help="max businesses to process")
    parser.add_argument("--sheet-id", default=os.getenv("GOOGLE_SHEET_ID", ""))
    parser.add_argument(
        "--max-hunter-calls",
        type=int,
        default=20,
        help="cap Hunter.io lookups per run to protect free-tier quota",
    )
    parser.add_argument(
        "--no-sheet", action="store_true", help="skip writing to Google Sheets, CSV only"
    )
    return parser.parse_args()


def process_place(place: dict, industry_label: str, city: str, hunter: HunterClient) -> Lead:
    lead = Lead(
        place_id=place["place_id"],
        name=place["name"],
        industry=industry_label,
        address=place["address"],
        phone=place["phone"],
        website=place["website"],
        city=city,
    )

    if not lead.website:
        lead.has_website = False
        lead.website_status = "none"
        lead.category = "web_design"
        lead.notes = "No website on file with Google Places"
        return lead

    lead.has_website = True
    site = fetch_site(lead.website)

    if site["status"] != "ok":
        lead.website_status = "dead"
        lead.category = "web_design"
        lead.notes = "Website did not respond"
        return lead

    quality = assess_website(lead.website, site["html"], site["status"])
    lead.website_status = quality["status"]

    if quality["status"] == "outdated":
        lead.category = "web_design"
        lead.notes = "; ".join(quality["reasons"])
        lead.email = find_email_from_site(lead.website, site["html"])
        lead.email_source = "site scrape" if lead.email else ""
        return lead

    chatbot = detect_chatbot(site["html"])
    lead.chatbot_detected = chatbot["detected"]
    lead.chatbot_vendor = chatbot["vendor"]

    if chatbot["detected"]:
        lead.category = "has_chatbot"
        return lead

    lead.category = "buyer"
    lead.email = find_email_from_site(lead.website, site["html"])
    lead.email_source = "site scrape" if lead.email else ""
    if not lead.email:
        domain = lead.website.split("//")[-1].split("/")[0].replace("www.", "")
        hunter_email = hunter.find_email(domain)
        if hunter_email:
            lead.email = hunter_email
            lead.email_source = "hunter.io"

    return lead


def write_csv_backup(leads: list[Lead], industry: str, city: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_city = city.replace(",", "").replace(" ", "_")
    path = OUTPUT_DIR / f"{industry}_{safe_city}_{timestamp}.csv"

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Category", "Place ID"] + Lead.HEADER)
        for lead in leads:
            writer.writerow([lead.category, lead.place_id] + lead.as_row())

    return path


def main():
    load_dotenv()
    industries = load_industries()
    args = parse_args(industries)

    places_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    hunter_api_key = os.getenv("HUNTER_API_KEY", "")

    if not places_api_key:
        sys.exit("GOOGLE_PLACES_API_KEY is not set. Copy .env.example to .env and fill it in.")

    industry_cfg = industries[args.industry]
    industry_label = industry_cfg["label"]
    queries = industry_cfg["queries"]

    places_client = PlacesClient(places_api_key)
    hunter = HunterClient(hunter_api_key, max_calls=args.max_hunter_calls)

    print(f"Searching '{industry_label}' in {args.city} (limit {args.limit})...")

    seen_place_ids = set()
    raw_places = []
    for i, query in enumerate(queries):
        remaining_budget = args.limit - len(raw_places)
        if remaining_budget <= 0:
            break
        # Split remaining budget across remaining queries so an early query
        # returning fewer results than its share doesn't starve later ones.
        query_limit = max(1, -(-remaining_budget // (len(queries) - i)))
        results = places_client.search(query, args.city, query_limit)
        for place in results:
            if place["place_id"] in seen_place_ids:
                continue
            seen_place_ids.add(place["place_id"])
            raw_places.append(place)

    raw_places = raw_places[: args.limit]
    print(f"Found {len(raw_places)} unique businesses. Processing each...")

    leads = []
    for i, place in enumerate(raw_places, 1):
        print(f"  [{i}/{len(raw_places)}] {place['name']}")
        lead = process_place(place, industry_label, args.city, hunter)
        leads.append(lead)
        time.sleep(0.5)  # be polite to target sites

    buyer_count = sum(1 for l in leads if l.category == "buyer")
    web_design_count = sum(1 for l in leads if l.category == "web_design")
    has_chatbot_count = sum(1 for l in leads if l.category == "has_chatbot")

    print("\nSummary:")
    print(f"  Buyer leads (no chatbot):       {buyer_count}")
    print(f"  Web design leads (no/outdated): {web_design_count}")
    print(f"  Has chatbot (reference):        {has_chatbot_count}")
    print(f"  Hunter.io lookups used:         {hunter.calls_made}/{hunter.max_calls}")

    csv_path = write_csv_backup(leads, args.industry, args.city)
    print(f"\nCSV backup written to {csv_path}")

    if args.no_sheet:
        return

    sheet_id = args.sheet_id
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

    if not sheet_id:
        print("\nNo --sheet-id / GOOGLE_SHEET_ID set - skipping Google Sheets write.")
        return

    if not Path(service_account_file).exists():
        print(
            f"\nService account file '{service_account_file}' not found - "
            "skipping Google Sheets write. See README for setup."
        )
        return

    from src.sheets import SheetWriter  # imported lazily so --no-sheet doesn't need gspread

    writer = SheetWriter(service_account_file, sheet_id)
    written = writer.write_leads(leads)
    print("\nWritten to Google Sheet:")
    for tab, count in written.items():
        print(f"  {tab}: {count} new rows")


if __name__ == "__main__":
    main()
