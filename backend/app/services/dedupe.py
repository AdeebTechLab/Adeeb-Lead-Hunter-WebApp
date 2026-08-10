import re
from urllib.parse import urlparse


def normalize_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def normalize_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


def normalize_domain(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return parsed.netloc.lower().removeprefix("www.")


def make_dedupe_key(lead: dict) -> str:
    """Prefer stable contact identifiers, while keeping same-name branches distinct."""
    phone = normalize_phone(lead.get("phone"))
    domain = normalize_domain(lead.get("website"))
    place_id = normalize_text(lead.get("google_place_id"))
    if phone:
        return f"phone:{phone}"
    if place_id:
        return f"place:{place_id}"
    if domain:
        return f"domain:{domain}"

    name = normalize_text(lead.get("business_name"))
    city = normalize_text(lead.get("city"))
    address = normalize_text(lead.get("address"))
    if address:
        return f"name-address:{name}:{city}:{address}"
    lat, lon = lead.get("latitude"), lead.get("longitude")
    if lat is not None and lon is not None:
        return f"name-location:{name}:{city}:{float(lat):.4f}:{float(lon):.4f}"
    return f"name-city:{name}:{city}"
