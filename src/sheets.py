"""Writes leads to a Google Sheet with three tabs, deduping by place_id so
re-running the tool doesn't create duplicate rows for the same business.

Auth: uses OAuth user credentials by default (gspread.oauth()) - this signs
in as *you*, so no service account or sharing step is needed, and it isn't
affected by organization policies that block service account key creation.
If a service account file is available (some orgs do allow them), pass
service_account_file and it'll be used instead.
"""

from urllib.parse import urlparse

import gspread
from google.oauth2.service_account import Credentials

from src.models import AgentLead, Lead

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


def _normalize_domain(url: str) -> str:
    """Google Places sometimes lists the same real business/agent under two
    different Place IDs (e.g. a personal listing and their brokerage's
    listing pointing at the same site) - place_id-only dedup misses that.
    Comparing normalized website domains catches it."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = f"https://{url}"
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


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

        self._existing_place_ids: dict[str, set] = {}
        self._existing_emails: dict[str, set] = {}
        self._existing_domains: dict[str, set] = {}

    def _get_or_create_tab(self, tab_name: str, header: list[str] | None = None):
        try:
            ws = self.spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=20)
            ws.append_row(["Place ID"] + (header or Lead.HEADER))
        return ws

    def _seen_place_ids(self, tab_name: str, header: list[str] | None = None) -> set:
        if tab_name not in self._existing_place_ids:
            ws = self._get_or_create_tab(tab_name, header)
            col_values = ws.col_values(1)[1:]  # skip header
            self._existing_place_ids[tab_name] = set(col_values)
        return self._existing_place_ids[tab_name]

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
            ws = self._get_or_create_tab(tab_name)
            seen = self._seen_place_ids(tab_name)
            rows = []
            for lead in tab_leads:
                if lead.place_id in seen:
                    continue
                rows.append([lead.place_id] + lead.as_row())
                seen.add(lead.place_id)
            if rows:
                ws.append_rows(rows, value_input_option="RAW")
                written[tab_name] = len(rows)

        return written

    def write_agent_leads(self, leads: list[AgentLead]) -> dict:
        """Append agent leads to the single 'Real Estate Agents' tab,
        skipping duplicates by place_id *and* by email/website domain -
        the same person/business can show up under more than one Place ID,
        and for a direct-outreach list a repeated email is what actually
        matters (it's a double-send risk), not just a repeated Place ID."""
        ws = self._get_or_create_tab(TAB_AGENTS, AgentLead.HEADER)
        seen_ids = self._seen_place_ids(TAB_AGENTS, AgentLead.HEADER)

        if TAB_AGENTS not in self._existing_emails:
            all_values = ws.get_all_values()
            emails, domains = set(), set()
            if len(all_values) > 1:
                header = all_values[0]
                email_idx = header.index("Direct Email") if "Direct Email" in header else None
                website_idx = header.index("Website") if "Website" in header else None
                for row in all_values[1:]:
                    if email_idx is not None and len(row) > email_idx and row[email_idx]:
                        emails.add(row[email_idx].strip().lower())
                    if website_idx is not None and len(row) > website_idx and row[website_idx]:
                        domain = _normalize_domain(row[website_idx])
                        if domain:
                            domains.add(domain)
            self._existing_emails[TAB_AGENTS] = emails
            self._existing_domains[TAB_AGENTS] = domains

        seen_emails = self._existing_emails[TAB_AGENTS]
        seen_domains = self._existing_domains[TAB_AGENTS]

        rows = []
        for lead in leads:
            email_key = lead.email.strip().lower() if lead.email else ""
            domain_key = _normalize_domain(lead.website)

            if lead.place_id in seen_ids:
                continue
            if email_key and email_key in seen_emails:
                continue
            if domain_key and domain_key in seen_domains:
                continue

            rows.append([lead.place_id] + lead.as_row())
            seen_ids.add(lead.place_id)
            if email_key:
                seen_emails.add(email_key)
            if domain_key:
                seen_domains.add(domain_key)

        if rows:
            ws.append_rows(rows, value_input_option="RAW")
        return {TAB_AGENTS: len(rows)}
