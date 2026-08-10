from dataclasses import dataclass, field


@dataclass
class Lead:
    place_id: str
    name: str
    industry: str
    address: str = ""
    phone: str = ""
    website: str = ""
    email: str = ""
    email_source: str = ""
    city: str = ""

    has_website: bool = False
    website_status: str = "unknown"  # "ok" | "outdated" | "dead" | "none"
    chatbot_detected: bool = False
    chatbot_vendor: str = ""

    category: str = ""  # "buyer" | "web_design" | "has_chatbot"
    notes: str = ""

    def as_row(self) -> list:
        return [
            self.name,
            self.address,
            self.phone,
            self.email,
            self.website,
            self.industry,
            self.city,
            "Yes" if self.chatbot_detected else "No",
            self.chatbot_vendor,
            self.website_status,
            self.email_source,
            self.notes,
        ]

    HEADER = [
        "Business Name",
        "Address",
        "Phone",
        "Email",
        "Website",
        "Industry",
        "City",
        "Chatbot Detected",
        "Chatbot Vendor",
        "Website Status",
        "Email Source",
        "Notes",
    ]


@dataclass
class AgentLead:
    """A single real estate agent (individual, not a brokerage/PM firm) with
    a direct contact email - built for design/photo/video outreach rather
    than the chatbot buyer/web-design categorization Lead uses."""

    place_id: str
    name: str
    address: str = ""
    phone: str = ""
    website: str = ""
    email: str = ""
    email_source: str = ""
    city: str = ""
    platform_hint: str = ""
    notes: str = ""

    def as_row(self) -> list:
        return [
            self.name,
            self.email,
            self.email_source,
            self.phone,
            self.website,
            self.address,
            self.city,
            self.platform_hint,
            self.notes,
        ]

    HEADER = [
        "Agent / Business Name",
        "Direct Email",
        "Email Source",
        "Phone",
        "Website",
        "Address",
        "City",
        "Site Platform Hint",
        "Notes",
    ]
