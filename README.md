# ChatBot Leads

Finds small businesses that are good targets for a chatbot pitch, and
separately flags ones that need a new website (a funnel for web design work).

For each business found in a given city/industry, the tool:

1. Looks it up via **Google Places** (name, address, phone, website).
2. If it has no website, or the website is dead/parked/clearly outdated →
   **Web Design Leads**.
3. If it has a live, reasonably current website with **no chatbot widget
   detected** → **Buyer Leads** (your primary chatbot-sales target).
4. If it has a live website **with a chatbot already installed** → **Has
   Chatbot (Reference)** (logged, but excluded from your primary list).
5. Emails are scraped from the business's own site first (free); if that
   fails, it falls back to Hunter.io's free-tier domain search.
6. Everything is written to a Google Sheet (three tabs) and also saved as a
   local CSV backup in `output/` on every run.

Industries are config-driven (`config/industries.json`) — only **Real
Estate Agents / Brokerages / Property Management** is enabled to start, but
Legal Services, Retail/E-commerce, Restaurants/Hospitality,
Healthcare/Dental, and Professional Services are already stubbed in with
search terms from the adoption table you shared. Flip `"enabled": true` and
pass `--industry <key>` to turn one on — that's the "dropdown."

### Alternate mode: `real_estate_agents` (direct-email agent list)

A second, differently-shaped pipeline for a different pitch: selling
design/photo/video services directly to individual agents, rather than
chatbots to businesses. Run it with:

```bash
python -m src.main --industry real_estate_agents --city "Portland, OR" --limit 100
```

Differences from the default mode:
- Skips the buyer/web-design/chatbot categorization entirely - there's no
  "no chatbot" signal for this pitch.
- Filters out listings that read as a property-management/brokerage *firm*
  (name contains "property management," "management LLC," etc.) rather than
  an individual agent, since the pitch is to one person, not a company.
- Prefers a **named individual's own email** (e.g. `megan@...`) over a
  generic role inbox (`info@`, `team@`, `office@`, ...) when a site or
  Hunter.io has both - scored by matching the agent's own name against the
  email's local-part. Falls back to whatever's available if no personal
  match is found, and marks the `Email Source` column accordingly.
- Adds a **Site Platform Hint** column (Wix/Squarespace/GoDaddy/Weebly/
  Carrd, or blank) as a soft, automatable proxy for "hasn't invested in
  custom branding" - not a real detector of AI-generated graphics, which
  isn't something a script can reliably tell (that part's worth eyeballing
  the actual listing photos yourself before you pitch).
- Writes to its own **Real Estate Agents** tab instead of the three
  buyer/web-design/chatbot tabs.

## 1. Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

You need three things, all free to start. None of this can be done for
you automatically — each requires you to create your own account.

### a) Google Places API key

1. Go to https://console.cloud.google.com/ and create a project (or reuse one).
2. Enable **"Places API (New)"** under APIs & Services → Library.
3. APIs & Services → Credentials → Create Credentials → API key.
4. Enable billing on the project — Places API requires it, but Google gives
   a recurring monthly free credit that comfortably covers a few hundred
   searches. Text Search costs $0.032/request (Essentials SKU) as of this
   writing; a 50-lead run is roughly 4-8 requests. Set a budget alert.
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
     as a test user. Publishing status can stay "Testing."
   - Application type: **Desktop app**. Name it anything.
3. Download the resulting JSON and save it as `credentials.json` in
   gspread's config folder, which is **OS-specific**:
   - macOS/Linux: `~/.config/gspread/credentials.json`
     (create it first: `mkdir -p ~/.config/gspread`)
   - Windows: `%APPDATA%\gspread\credentials.json`, i.e.
     `C:\Users\<you>\AppData\Roaming\gspread\credentials.json`
     (create it first in PowerShell: `mkdir -Force "$env:APPDATA\gspread"`)
4. Leave `GOOGLE_SHEET_ID` blank in `.env` - the tool creates a new Sheet
   automatically on first run and prints its URL/ID for you to save if you
   want to reuse the same sheet on later runs.

The first time you run the tool, it'll open a browser asking you to sign in
and grant access - approve it, and it caches the token next to
`credentials.json` (as `authorized_user.json`) for future runs (no repeat
sign-in).

**If your org does allow service account keys** and you'd rather use one:
create it the traditional way (Credentials → Service Account → Keys → Add
Key → JSON), save it as `service_account.json` in the project root, share
the Sheet with its `client_email` as an Editor, and set
`GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json` in `.env` - the tool
will use it automatically instead of OAuth if the file exists.

## 2. Run it

```bash
python -m src.main --industry real_estate --city "Portland, OR" --limit 50
```

Useful flags:

- `--limit` — how many businesses to process (default 50). Directly drives
  Places API cost.
- `--max-hunter-calls` — cap on Hunter.io fallback lookups (default 20).
- `--no-sheet` — skip the Google Sheet write, CSV backup only (useful for a
  first test run before you've set up Sheets access).

Every run also writes a timestamped CSV to `output/` regardless of the
Sheets integration, so you never lose a batch.

## 3. Reading the output

Each Sheet tab / CSV row includes: business name, address, phone, email,
website, industry, city, whether a chatbot was detected (+ vendor if
known), website status (`ok` / `outdated` / `dead` / `none`), where the
email came from, and notes (e.g. why a site was flagged outdated).

- **Buyer Leads** — no chatbot detected on a live, current site. Pitch them
  the chatbot directly.
- **Web Design Leads** — no website, a dead one, or one flagged outdated
  (no HTTPS, not mobile-responsive, stale copyright year, parked-page text,
  or almost no content). Good web design leads; some may also become
  chatbot buyers once they have a real site.
- **Has Chatbot (Reference)** — already has a chatbot. Logged so you don't
  waste time on them, and to see which vendors are already in the market.

## 4. Notes on detection accuracy

Chatbot detection is signature-based (it looks for known vendor script
tags like Intercom, Drift, Tidio, HubSpot, Zendesk, Tawk.to, etc. in the
page HTML). It will miss chatbots that load exclusively through a tag
manager after page load, and it can't detect custom-built or very new
chatbot products it doesn't have a signature for yet — treat "no chatbot
detected" as "likely no chatbot," not a certainty, and glance at the site
yourself before a cold pitch. Add new signatures to
`src/chatbot_detect.py::CHATBOT_SIGNATURES` as you encounter vendors it
misses.

Hunter.io fallback is only used for **Buyer Leads** (live site, no chatbot,
no email found by scraping) — the highest-value list — to conserve your
free-tier quota. Web Design leads with a live-but-outdated site still get a
site-scrape attempt, but not a Hunter lookup; leads with no website at all
have no domain to look up, so rely on the phone number from Places.

"Outdated website" is a heuristic score (2+ red flags out of: no HTTPS, no
mobile viewport tag, stale copyright year, parked-page language, near-empty
page content). It's meant to surface likely candidates, not to be a
definitive audit — spot-check before you pitch.

## 5. Compliance

This tool only pulls information businesses already publish (Google
Business listings, their own websites). Before you use the output for
outreach:

- **Email**: CAN-SPAM requires a working unsubscribe mechanism, accurate
  sender info, and no deceptive subject lines for commercial email.
- **Phone/SMS**: cold calling or texting is subject to TCPA rules,
  including do-not-call list checks in some contexts — check current
  requirements for your state/use case before a calling campaign.

## Project layout

```
config/industries.json   # industry -> Places search queries ("dropdown")
src/places.py             # Google Places Text Search wrapper
src/fetch.py               # shared HTTP fetch (one request per site per run)
src/chatbot_detect.py       # chatbot vendor signature matching
src/website_quality.py     # outdated/dead/parked site heuristics
src/enrichment.py          # email scraping + Hunter.io fallback
src/sheets.py              # Google Sheets writer (dedupes by place_id)
src/models.py              # Lead dataclass / row schema
src/main.py                 # CLI orchestration
output/                    # CSV backups written on every run (gitignored)
```
