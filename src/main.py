"""CLI entrypoint: find individual real estate agents via Google Places,
find each one's direct contact email, and write results to a Google Sheet
(plus always a local CSV backup). Built for pitching creative/marketing
services (design, photo, video) straight to the agent - not brokerages or
property-management firms, and not chatbots.

Usage:
    python -m src.main --city "Portland, OR" --limit 100
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

from src.enrichment import HunterClient, find_direct_email_from_site
from src.fetch import fetch_site
from src.models import Lead
from src.places import PlacesClient
from src.util import sanitize_tab_name
from src.website_quality import detect_active_listings_hint, detect_platform_hint

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "search_queries.json"
OUTPUT_DIR = ROOT / "output"

# Name substrings that mean "this is a brokerage/property-management firm,
# not an individual agent" - the pitch (design/photo/video services) targets
# a specific person, not a company.
FIRM_KEYWORDS = [
    "property management",
    "management llc",
    "management inc",
    "management company",
    "management services",
    "management group",
]


def _looks_like_firm_not_agent(name: str) -> bool:
    lowered = name.lower()
    return any(kw in lowered for kw in FIRM_KEYWORDS)


def load_queries() -> list[str]:
    with open(CONFIG_PATH) as f:
        return json.load(f)["queries"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find individual real estate agents with a direct contact email."
    )
    parser.add_argument("--city", required=True, help='e.g. "Portland, OR"')
    parser.add_argument("--limit", type=int, default=50, help="max agents to process")
    parser.add_argument(
        "--sheet-id",
        default="",
        help=(
            "write into this specific sheet instead of the remembered active one "
            "(and make it the new active sheet for future runs too)."
        ),
    )
    parser.add_argument(
        "--new-sheet",
        action="store_true",
        help="start a brand-new spreadsheet instead of adding a tab to the remembered active one",
    )
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


def process_place(place: dict, city: str, hunter: HunterClient) -> Lead:
    lead = Lead(
        place_id=place["place_id"],
        name=place["name"],
        address=place["address"],
        phone=place["phone"],
        website=place["website"],
        city=city,
    )

    if not lead.website:
        lead.notes = "No website on file with Google Places"
        return lead

    site = fetch_site(lead.website)
    if site["status"] != "ok":
        lead.notes = "Website did not respond"
        return lead

    lead.platform_hint = detect_platform_hint(site["html"])
    lead.active_listings_hint = detect_active_listings_hint(site["html"])

    email, source = find_direct_email_from_site(lead.name, lead.website, site["html"])
    if email:
        lead.email = email
        lead.email_source = source
        return lead

    domain = lead.website.split("//")[-1].split("/")[0].replace("www.", "")
    hunter_email = hunter.find_email(domain)
    if hunter_email:
        lead.email = hunter_email
        lead.email_source = "hunter.io"

    return lead


def write_csv_backup(leads: list[Lead], city: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_city = city.replace(",", "").replace(" ", "_")
    path = OUTPUT_DIR / f"real_estate_agents_{safe_city}_{timestamp}.csv"

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Place ID"] + Lead.HEADER)
        for lead in leads:
            writer.writerow([lead.place_id] + lead.as_row())

    return path


def main():
    load_dotenv()
    queries = load_queries()
    args = parse_args()

    places_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    hunter_api_key = os.getenv("HUNTER_API_KEY", "")

    if not places_api_key:
        sys.exit("GOOGLE_PLACES_API_KEY is not set. Copy .env.example to .env and fill it in.")

    places_client = PlacesClient(places_api_key)
    hunter = HunterClient(hunter_api_key, max_calls=args.max_hunter_calls)

    print(f"Searching for real estate agents in {args.city} (limit {args.limit})...")

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

    before = len(raw_places)
    raw_places = [p for p in raw_places if not _looks_like_firm_not_agent(p["name"])]
    skipped = before - len(raw_places)
    if skipped:
        print(
            f"Filtered out {skipped} property-management/brokerage-firm "
            "listings (not individual agents)."
        )

    print(f"Found {len(raw_places)} unique agents. Processing each...")

    leads = []
    for i, place in enumerate(raw_places, 1):
        print(f"  [{i}/{len(raw_places)}] {place['name']}")
        lead = process_place(place, args.city, hunter)
        leads.append(lead)
        time.sleep(0.5)  # be polite to target sites

    with_email = sum(1 for l in leads if l.email)
    direct_match_count = sum(1 for l in leads if l.email_source == "site scrape (direct match)")
    active_listing_count = sum(1 for l in leads if l.active_listings_hint)

    print("\nSummary:")
    print(f"  Agents found:                     {len(leads)}")
    print(f"  With an email:                    {with_email}")
    print(f"  Confirmed direct/personal match:  {direct_match_count}")
    print(f"  Active-listings signal found:     {active_listing_count}")
    print(f"  Hunter.io lookups used:           {hunter.calls_made}/{hunter.max_calls}")

    csv_path = write_csv_backup(leads, args.city)
    print(f"\nCSV backup written to {csv_path}")

    if args.no_sheet:
        return

    from src.active_sheet import load_active_sheet, save_active_sheet
    from src.sheets import SheetWriter  # imported lazily so --no-sheet doesn't need gspread

    active = load_active_sheet()

    if args.sheet_id:
        sheet_id = args.sheet_id
        reused_active = False
    elif args.new_sheet or not active:
        sheet_id = None
        reused_active = False
    else:
        sheet_id = active["sheet_id"]
        reused_active = True

    # Service account is optional - only used if the file actually exists
    # (some orgs block service account key creation; OAuth is the default).
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    if not Path(service_account_file).exists():
        service_account_file = None

    if service_account_file is None:
        print("\nNo service account file found - using OAuth (browser sign-in) instead.")

    if reused_active:
        print(f"Adding a new tab to your active sheet: {active['url']}")
    elif sheet_id:
        print(f"Writing into the sheet you specified: {sheet_id}")
    else:
        print("No active sheet yet - creating a brand-new Google Sheet...")

    writer = SheetWriter(
        sheet_id=sheet_id,
        service_account_file=service_account_file,
        create_title="Real Estate Agent Leads",
    )
    save_active_sheet(writer.spreadsheet.id, writer.spreadsheet.url)

    if not reused_active:
        print(f"Sheet: {writer.spreadsheet.url}")
        print(
            "(This is now your active sheet - every future run adds its own new tab "
            "here automatically. Pass --new-sheet to start a different one instead. "
            "Either way, an agent/email/domain already captured in a past run is still "
            "automatically skipped, so nothing gets duplicated or emailed twice.)"
        )

    run_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tab_name = sanitize_tab_name(f"{args.city} - {run_stamp}")

    written = writer.write_leads(leads, tab_name)
    print("\nWritten to Google Sheet:")
    for tab, count in written.items():
        print(f"  {tab}: {count} new rows")


if __name__ == "__main__":
    main()
