from dataclasses import dataclass


@dataclass
class Lead:
    """A single real estate agent (individual, not a brokerage/property
    management firm) with a direct contact email - built for pitching
    creative/marketing services (design, photo, video) directly to the
    person, not a company inbox."""

    place_id: str
    name: str
    address: str = ""
    phone: str = ""
    website: str = ""
    email: str = ""
    email_source: str = ""
    city: str = ""
    platform_hint: str = ""
    active_listings_hint: str = ""
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
            self.active_listings_hint,
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
        "Active Listings Signal",
        "Notes",
    ]
