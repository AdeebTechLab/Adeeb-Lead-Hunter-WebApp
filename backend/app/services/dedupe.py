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


def make_identity_keys(lead: dict) -> list[str]:
    """Return stable strong/branch identity aliases for duplicate detection across providers."""
    keys: list[str] = []

    phone = normalize_phone(lead.get("phone"))
    place_id = normalize_text(lead.get("google_place_id"))
    domain = normalize_domain(lead.get("website"))
    if phone:
        keys.append(f"phone:{phone}")
    if place_id:
        keys.append(f"place:{place_id}")
    if domain:
        keys.append(f"domain:{domain}")

    name = normalize_text(lead.get("business_name"))
    city = normalize_text(lead.get("city"))
    address = normalize_text(lead.get("address"))
    if name and city:
        if address:
            keys.append(f"name-address:{name}:{city}:{address}")

        lat, lon = lead.get("latitude"), lead.get("longitude")
        if lat is not None and lon is not None:
            try:
                keys.append(f"name-location:{name}:{city}:{float(lat):.4f}:{float(lon):.4f}")
            except (TypeError, ValueError):
                pass

        # Only use the weak name+city identity when no branch-level identity exists.
        if not address and not any(key.startswith("name-location:") for key in keys):
            keys.append(f"name-city:{name}:{city}")

    # Preserve priority order while removing accidental duplicates.
    return list(dict.fromkeys(keys))


def make_dedupe_key(lead: dict) -> str:
    """Primary unique key; aliases are stored separately to survive provider/contact differences."""
    keys = make_identity_keys(lead)
    if keys:
        return keys[0]
    # Models require a business name and city, but keep this deterministic for legacy records.
    return f"legacy:{normalize_text(lead.get('business_name'))}:{normalize_text(lead.get('city'))}"
