# Real Estate Agent Leads

Finds **individual real estate agents** (not brokerages, not property
management firms) in a given city, along with each one's **direct personal
email** — built for pitching creative/marketing services (design, photo,
video) straight to the agent, not a company inbox.

For each agent found in a given city, the tool:

1. Looks them up via **Google Places** (name, address, phone, website),
   filtering out anything that reads as a property-management/brokerage
   *firm* rather than an individual.
2. Visits their own website and looks for a **direct/personal email**
   (e.g. `megan@...`) over a generic role inbox (`info@`, `team@`,
   `office@`) — scored by matching the agent's own name against the
   email's local-part. Falls back to Hunter.io's free-tier domain search if
   nothing's found by scraping, and to a generic inbox if no personal
   address exists anywhere.
3. Flags two soft, best-effort signals on their site (not hard filters —
   there's no free/reliable way to pull live MLS listing counts per agent,
   that data lives behind Zillow/Realtor.com/MLS systems that block
   scraping or require a paid broker data feed):
   - **Site Platform Hint** — Wix/Squarespace/GoDaddy/Weebly/Carrd, or
     blank. A DIY site builder is a soft proxy for "hasn't invested in
     custom branding/photography."
   - **Active Listings Signal** — an IDX/MLS widget or an actual MLS#
     found on the page. A soft proxy for "currently active," not proof.
4. Every run creates its **own brand-new Google Sheet** (tab: "Real Estate
   Agents") and also always saves a local CSV backup in `output/`.
   Cross-run duplicate protection (by Place ID, email, *and* website
   domain — the same person sometimes shows up under two different Google
   Places listings) means re-running never re-adds, or re-emails, someone
   already captured in an earlier run, even though results land in a new
   sheet each time.

## 1. Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

You need three things, all free to start. None of this can be done for you
automatically — each requires you to create your own account.

### a) Google Places API key

1. Go to https://console.cloud.google.com/ and create a project (or reuse one).
2. Enable **"Places API (New)"** under APIs & Services → Library.
3. APIs & Services → Credentials → Create Credentials → API key.
4. Enable billing on the project — Places API requires it, but Google gives
   a recurring monthly free credit that comfortably covers a few hundred
   searches. Text Search costs $0.032/request (Essentials SKU) as of this
   writing; a 100-agent run is typically only 5-6 requests. Set a budget alert.
5. Paste the key into `.env` as `GOOGLE_PLACES_API_KEY`.

### b) Hunter.io API key (free tier)

1. Sign up at https://hunter.io (free plan).
2. Go to https://hunter.io/api-keys and copy your key.
3. Paste it into `.env` as `HUNTER_API_KEY`.
4. Check your current free-tier monthly search limit on that page — it has
   changed over time, so don't assume a number. The `--max-hunter-calls`
   flag (default 20) caps usage per run so you don't blow through it in one go.

### c) Google Sheets output

Uses OAuth (you sign in as yourself) by default, since many Google Cloud
orgs now block service account key downloads for security. No sharing step
needed - it's already your Sheet.

1. In the same Google Cloud project, enable **"Google Sheets API"** (APIs &
   Services → Library → search it → Enable).
2. APIs & Services → Credentials → Create Credentials → **OAuth client ID**.
   - If prompted, configure the OAuth consent screen first: User type
     "External" is fine, fill in an app name, your email, and add yourself
     as a test user.
   - Application type: **Desktop app**. Name it anything.
   - **Publishing status: click "Publish App" to move it to Production**
     (it stays unverified, fine for personal use). Apps left in "Testing"
     get a 7-day sign-in expiry, which means re-authenticating weekly for
     no reason - Production doesn't have that limit.
3. Download the resulting JSON and save it as `credentials.json` in
   gspread's config folder, which is **OS-specific**:
   - macOS/Linux: `~/.config/gspread/credentials.json`
     (create it first: `mkdir -p ~/.config/gspread`)
   - Windows: `%APPDATA%\gspread\credentials.json`, i.e.
     `C:\Users\<you>\AppData\Roaming\gspread\credentials.json`
     (create it first in PowerShell: `mkdir -Force "$env:APPDATA\gspread"`)
4. Nothing else to configure here - **every run creates its own brand-new
   Google Sheet** and prints its URL when done. Pass `--sheet-id <id>` if you
   ever want to write into one specific existing sheet instead. Either way,
   an agent/email/website domain already captured in a *past* run is still
   automatically skipped (tracked locally in `output/dedup_history.json`,
   not committed to git), so you never get a duplicate row or a duplicate
   outreach email just because the results now land in a new sheet each
   time.

The first time you run the tool, it'll open a browser asking you to sign in
and grant access - approve it, and it caches the token next to
`credentials.json` (as `authorized_user.json`) for future runs (no repeat
sign-in, as long as the app's Published as above).

**If your org does allow service account keys** and you'd rather use one:
create it the traditional way (Credentials → Service Account → Keys → Add
Key → JSON), save it as `service_account.json` in the project root, share
the Sheet with its `client_email` as an Editor, and set
`GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json` in `.env` - the tool
will use it automatically instead of OAuth if the file exists.

## 2. Run it

```bash
python -m src.main --city "Portland, OR" --limit 100
```

Useful flags:

- `--limit` — how many agents to process (default 50). Directly drives
  Places API cost.
- `--sheet-id <id>` — write into a specific existing sheet instead of
  creating a new one this run.
- `--max-hunter-calls` — cap on Hunter.io fallback lookups (default 20).
- `--no-sheet` — skip the Google Sheet write, CSV backup only (useful for a
  first test run before you've set up Sheets access).

Every run also writes a timestamped CSV to `output/` regardless of the
Sheets integration, so you never lose a batch.

### Getting more than ~60 results for one city

Google Places Text Search caps out around 60 results per distinct search
phrase, and near-synonym phrases ("real estate agent" vs. "realtor") tend
to return heavily overlapping sets - so you'll hit a ceiling well below the
true number of agents in a city. Two ways to push past it, both edited in
`config/search_queries.json`:

- **Add genuinely different phrasing** (not synonyms) — e.g. "buyers
  agent," "listing agent," "residential real estate agent" — each distinct
  phrase gets its own fresh ~60-result ceiling from Google's ranking.
- **Split by neighborhood/suburb** instead of running the whole metro at
  once — e.g. separate runs for "Southeast Portland, OR," "Northwest
  Portland, OR," "Beaverton, OR," "Lake Oswego, OR" — each is a distinct
  enough query to surface a different set of top-ranked results.

## 3. Reading the output

Each Sheet row / CSV row includes: agent/business name, direct email, where
that email came from, phone, website, address, city, site platform hint,
active-listings signal, and notes (e.g. why no email was found).

- **Email Source** tells you how confident to be: `site scrape (direct
  match)` means the email's local-part matched the agent's own name (the
  good case); `site scrape (generic inbox)` or `hunter.io` means it's the
  best available but not confirmed personal - worth a quick glance before
  a highly personalized pitch.
- **Site Platform Hint** and **Active Listings Signal** are prioritization
  aids, not filters - nobody gets excluded from the list based on them.
  Neither one is a substitute for looking at the agent's actual listing
  photos/flyers yourself before pitching design/photo/video services.

## 4. Compliance

This tool only pulls information agents already publish (Google Business
listings, their own websites). Before you use the output for outreach:

- **Email**: CAN-SPAM requires a working unsubscribe mechanism, accurate
  sender info, and no deceptive subject lines for commercial email.
- **Phone/SMS**: cold calling or texting is subject to TCPA rules,
  including do-not-call list checks in some contexts — check current
  requirements for your state/use case before a calling campaign.

## Recovery / maintenance tools

- `python -m src.import_csv <path-to-csv> [sheet_id]` — upload an
  already-generated `output/*.csv` straight to a Sheet without re-running
  the search. Useful if the Sheets write step fails after a run already
  collected the data (e.g. an expired OAuth token) - avoids re-paying for
  and re-running the whole search.
- `python -m src.dedupe_sheet "Real Estate Agents" [sheet_id]` — one-off
  cleanup of duplicate rows already sitting in a sheet (matched by email
  or website domain, not just Place ID). Keeps whichever row has an email
  filled in when only one does.
- `python -m src.seed_history [sheet_id]` — seeds
  `output/dedup_history.json` from an existing sheet's current content.
  Only needed once if you're migrating an older sheet into the current
  cross-run dedup system.

## Project layout

```
config/search_queries.json  # Places search phrases (edit to add more/split by neighborhood)
src/places.py                # Google Places Text Search wrapper
src/fetch.py                  # shared HTTP fetch (one request per site per run)
src/website_quality.py       # site platform / active-listings signal heuristics
src/enrichment.py            # direct-email scraping + Hunter.io fallback
src/sheets.py                 # Google Sheets writer (dedupes by place_id/email/domain)
src/dedup_history.py          # local cross-run duplicate memory
src/util.py                    # shared helpers (domain normalization)
src/models.py                 # Lead dataclass / row schema
src/main.py                    # CLI orchestration
src/import_csv.py             # recovery: CSV -> Sheet without re-scraping
src/dedupe_sheet.py            # recovery: clean up duplicates already in a sheet
src/seed_history.py            # migration: seed dedup history from an existing sheet
output/                       # CSV backups + dedup_history.json (gitignored)
```
