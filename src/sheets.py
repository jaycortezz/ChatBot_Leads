"""Writes leads to a Google Sheet with three tabs, deduping by place_id so
re-running the tool doesn't create duplicate rows for the same business.

Auth: uses OAuth user credentials by default (gspread.oauth()) - this signs
in as *you*, so no service account or sharing step is needed, and it isn't
affected by organization policies that block service account key creation.
If a service account file is available (some orgs do allow them), pass
service_account_file and it'll be used instead.
"""

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
        skipping duplicates by place_id."""
        ws = self._get_or_create_tab(TAB_AGENTS, AgentLead.HEADER)
        seen = self._seen_place_ids(TAB_AGENTS, AgentLead.HEADER)
        rows = []
        for lead in leads:
            if lead.place_id in seen:
                continue
            rows.append([lead.place_id] + lead.as_row())
            seen.add(lead.place_id)
        if rows:
            ws.append_rows(rows, value_input_option="RAW")
        return {TAB_AGENTS: len(rows)}
