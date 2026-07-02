"""Google Places API (Text Search, new v1 endpoint) lookup."""

import time
import requests

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "nextPageToken",
    ]
)


class PlacesClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY is not set")
        self.api_key = api_key

    def search(self, query: str, city: str, limit: int) -> list[dict]:
        """Run a single text search query scoped to a city, paginating until
        `limit` results are collected or Places stops returning pages."""
        results: list[dict] = []
        page_token = None
        text_query = f"{query} in {city}"

        while len(results) < limit:
            body = {"textQuery": text_query, "pageSize": min(20, limit - len(results))}
            if page_token:
                body["pageToken"] = page_token

            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": FIELD_MASK,
            }
            resp = requests.post(SEARCH_URL, json=body, headers=headers, timeout=20)
            if resp.status_code != 200:
                raise RuntimeError(f"Places API error {resp.status_code}: {resp.text}")

            data = resp.json()
            for place in data.get("places", []):
                results.append(self._normalize(place))

            page_token = data.get("nextPageToken")
            if not page_token:
                break
            # Google requires a short delay before a pageToken becomes valid.
            time.sleep(2)

        return results[:limit]

    @staticmethod
    def _normalize(place: dict) -> dict:
        return {
            "place_id": place.get("id", ""),
            "name": place.get("displayName", {}).get("text", ""),
            "address": place.get("formattedAddress", ""),
            "phone": place.get("nationalPhoneNumber")
            or place.get("internationalPhoneNumber", ""),
            "website": place.get("websiteUri", ""),
        }
