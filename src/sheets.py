"""Writes leads to a Google Sheet with three tabs, deduping by place_id,
email, and website domain so re-running the tool doesn't create duplicate
rows - or worse, a duplicate outreach email - for the same business.

Every run creates its own brand-new spreadsheet (see src/main.py), so the
sheet itself starts empty each time; cross-run duplicate protection instead
comes from src/dedup_history.py, a local file that remembers what's already
been captured across every past run, independent of which specific sheet it
ended up in.

Auth: uses OAuth user credentials by default (gspread.oauth()) - this signs
in as *you*, so no service account or sharing step is needed, and it isn't
affected by organization policies that block service account key creation.
If a service account file is available (some orgs do allow them), pass
service_account_file and it'll be used instead.
"""

import gspread
from google.oauth2.service_account import Credentials

from src.dedup_history import load_history, save_history
from src.models import AgentLead, Lead
from src.util import normalize_domain

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    # drive.file (not full Drive access) is required to *create* a new
    # spreadsheet via client.create(); it only grants access to files this
    # app itself creates, not your whole Drive.
    "https://www.googleapis.com/auth/drive.file",
]

TAB_BUYER = "Buyer Leads"
TAB_WEB_DESIGN = "Web Design Leads"
TAB_HAS_CHATBOT = "Has Chatbot (Reference)"
TAB_AGENTS = "Real Estate Agents"

TAB_FOR_CATEGORY = {
    "buyer": TAB_BUYER,
    "web_design": TAB_WEB_DESIGN,
    "has_chatbot": TAB_HAS_CHATBOT,
}


class SheetWriter:
    def __init__(
        self,
        sheet_id: str | None = None,
        service_account_file: str | None = None,
        create_title: str | None = None,
    ):
        """If sheet_id is falsy, a new spreadsheet titled create_title is
        created and used instead - the new sheet's ID/URL are exposed via
        self.spreadsheet for the caller to report back to the user."""
        if service_account_file:
            creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
            client = gspread.authorize(creds)
        else:
            # Opens a browser for one-time consent, then caches the token
            # locally (~/.config/gspread/authorized_user.json) for reuse.
            client = gspread.oauth(scopes=SCOPES)

        if sheet_id:
            self.spreadsheet = client.open_by_key(sheet_id)
        else:
            self.spreadsheet = client.create(create_title or "ChatBot Leads")

    def _get_or_create_tab(self, tab_name: str, header: list[str]):
        try:
            ws = self.spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=20)
            ws.append_row(["Place ID"] + header)
        return ws

    @staticmethod
    def _read_existing(ws, header: list[str]) -> tuple[set, set, set]:
        """Whatever's already in this specific sheet/tab - usually empty,
        since every run gets a fresh sheet, but still checked in case the
        caller explicitly reused an existing one."""
        all_values = ws.get_all_values()
        place_ids, emails, domains = set(), set(), set()
        if len(all_values) <= 1:
            return place_ids, emails, domains

        sheet_header = all_values[0]
        email_idx = next((sheet_header.index(n) for n in ("Direct Email", "Email") if n in sheet_header), None)
        website_idx = sheet_header.index("Website") if "Website" in sheet_header else None

        for row in all_values[1:]:
            if row and row[0]:
                place_ids.add(row[0])
            if email_idx is not None and len(row) > email_idx and row[email_idx]:
                emails.add(row[email_idx].strip().lower())
            if website_idx is not None and len(row) > website_idx and row[website_idx]:
                domain = normalize_domain(row[website_idx])
                if domain:
                    domains.add(domain)
        return place_ids, emails, domains

    def _write_deduped(self, tab_name: str, leads: list, header: list[str]) -> int:
        ws = self._get_or_create_tab(tab_name, header)
        sheet_ids, sheet_emails, sheet_domains = self._read_existing(ws, header)
        hist_ids, hist_emails, hist_domains = load_history(tab_name)

        seen_ids = sheet_ids | hist_ids
        seen_emails = sheet_emails | hist_emails
        seen_domains = sheet_domains | hist_domains
        new_ids, new_emails, new_domains = set(), set(), set()

        rows = []
        for lead in leads:
            email_key = (lead.email or "").strip().lower()
            domain_key = normalize_domain(lead.website)

            if lead.place_id in seen_ids:
                continue
            if email_key and email_key in seen_emails:
                continue
            if domain_key and domain_key in seen_domains:
                continue

            rows.append([lead.place_id] + lead.as_row())
            seen_ids.add(lead.place_id)
            new_ids.add(lead.place_id)
            if email_key:
                seen_emails.add(email_key)
                new_emails.add(email_key)
            if domain_key:
                seen_domains.add(domain_key)
                new_domains.add(domain_key)

        if rows:
            ws.append_rows(rows, value_input_option="RAW")
        if new_ids or new_emails or new_domains:
            save_history(tab_name, hist_ids | new_ids, hist_emails | new_emails, hist_domains | new_domains)

        return len(rows)

    def write_leads(self, leads: list[Lead]) -> dict:
        """Append leads to their category tab, skipping duplicates. Returns a
        count of rows written per tab."""
        written = {TAB_BUYER: 0, TAB_WEB_DESIGN: 0, TAB_HAS_CHATBOT: 0}

        by_tab: dict[str, list[Lead]] = {}
        for lead in leads:
            tab_name = TAB_FOR_CATEGORY.get(lead.category)
            if not tab_name:
                continue
            by_tab.setdefault(tab_name, []).append(lead)

        for tab_name, tab_leads in by_tab.items():
            written[tab_name] = self._write_deduped(tab_name, tab_leads, Lead.HEADER)

        return written

    def write_agent_leads(self, leads: list[AgentLead]) -> dict:
        """Append agent leads to the single 'Real Estate Agents' tab,
        skipping duplicates by place_id *and* by email/website domain -
        the same person/business can show up under more than one Place ID,
        and for a direct-outreach list a repeated email is what actually
        matters (it's a double-send risk), not just a repeated Place ID."""
        return {TAB_AGENTS: self._write_deduped(TAB_AGENTS, leads, AgentLead.HEADER)}
