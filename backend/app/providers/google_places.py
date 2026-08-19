from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx

from app.core.config import settings
from app.providers.common import ProviderError, ProviderSearchResult

SEARCH_FIELDS = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.rating",
        "places.userRatingCount",
        "places.primaryTypeDisplayName",
        "places.types",
        "places.businessStatus",
    ]
)


def _maps_search_url(name: str, address: str | None, place_id: str | None = None) -> str:
    query = quote_plus(", ".join(part for part in [name, address] if part))
    url = f"https://www.google.com/maps/search/?api=1&query={query}&utm_source=ai_lead_hunter&utm_campaign=lead_contact"
    if place_id:
        url += f"&query_place_id={quote_plus(place_id)}"
    return url


def _request_places(text_query: str, limit: int) -> List[Dict[str, Any]]:
    if not settings.google_places_api_key:
        raise ProviderError("Google Places is not configured.")

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": SEARCH_FIELDS,
        "User-Agent": settings.public_data_user_agent,
    }
    payload = {
        "textQuery": text_query,
        "pageSize": min(max(1, limit), 20),
        "languageCode": "en",
        "regionCode": "PK",
        "includePureServiceAreaBusinesses": True,
    }
    timeout = httpx.Timeout(connect=10.0, read=settings.provider_timeout_seconds, write=15.0, pool=10.0)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(f"{settings.google_places_base_url.rstrip('/')}/places:searchText", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        raise ProviderError("Google Places timed out. Automatic mode will try another live source.") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {401, 403}:
            raise ProviderError("Google Places access was rejected. Check the API key, Places API (New), billing and key restrictions.") from exc
        if status == 429:
            raise ProviderError("Google Places quota was reached. Try again later or use Geoapify.") from exc
        raise ProviderError("Google Places is temporarily unavailable.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError("Google Places could not return valid business data.") from exc
    return data.get("places") or []


def _text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _normalise_place(place: Dict[str, Any], keyword: str, city: str, province: str) -> Optional[dict]:
    name = _text(place.get("displayName"))
    if not name:
        return None
    address = _text(place.get("formattedAddress"))
    location = place.get("location") or {}
    phone = _text(place.get("internationalPhoneNumber")) or _text(place.get("nationalPhoneNumber"))
    website = _text(place.get("websiteUri"))
    place_id = _text(place.get("id"))
    maps_url = _text(place.get("googleMapsUri")) or _maps_search_url(name, address, place_id)
    category = _text(place.get("primaryTypeDisplayName")) or keyword.strip().title()
    rating = place.get("rating")
    reviews = int(place.get("userRatingCount") or 0)

    return {
        "business_name": name,
        "category": category,
        "city": city.title(),
        "province": province.title(),
        "phone": phone,
        "email": None,
        "website": website,
        "google_business_url": maps_url,
        "google_place_id": place_id,
        "facebook": None,
        "instagram": None,
        "linkedin": None,
        "address": address,
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "source": "Google Places API",
        "source_url": maps_url,
        "reviews_count": reviews,
        "rating": rating,
        "tags": [keyword.strip().title(), city.title(), "Real-time API", "Google Places"],
        "contact_sources": ["Google Places"] if phone or website else [],
        "contact_confidence": "High" if phone else "Medium" if website else "Low",
        "contact_status": "Contactable" if phone else "Website available" if website else "Research needed",
        "contact_search_url": maps_url,
    }


def google_places_search(keyword: str, city: str, province: str, limit: int, offset: int = 0) -> ProviderSearchResult:
    # Text Search pagination uses page tokens rather than numeric offsets. The
    # project currently keeps Google optional; later numeric pages are therefore
    # left empty so Automatic mode can continue through Geoapify/OSM.
    if offset > 0:
        return ProviderSearchResult(
            items=[],
            provider="google",
            attribution="Business details from Google Places API",
            endpoint="Google Places Text Search (New)",
        )
    query = f"{keyword.strip()} in {city.strip()}, {province.strip()}, Pakistan"
    places = _request_places(query, limit)
    items: List[dict] = []
    seen = set()
    for place in places:
        item = _normalise_place(place, keyword, city, province)
        if not item:
            continue
        key = (item["business_name"].casefold(), (item.get("address") or "").casefold())
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
        if len(items) >= limit:
            break
    return ProviderSearchResult(
        items=items,
        provider="google",
        attribution="Business details from Google Places API",
        endpoint="Google Places Text Search (New)",
    )


def google_exact_lookup(name: str, city: str, province: str, address: str | None = None) -> Optional[dict]:
    query = ", ".join(part for part in [name, address, city, province, "Pakistan"] if part)
    candidates = _request_places(query, 3)
    best: tuple[float, Optional[dict]] = (0.0, None)
    target = name.casefold().strip()
    city_key = city.casefold().strip()
    for place in candidates:
        item = _normalise_place(place, "Business", city, province)
        if not item:
            continue
        name_score = SequenceMatcher(None, target, item["business_name"].casefold()).ratio()
        address_text = (item.get("address") or "").casefold()
        city_bonus = 0.15 if city_key and city_key in address_text else 0.0
        score = name_score + city_bonus
        if score > best[0]:
            best = (score, item)
    # Strict enough to avoid assigning another business's phone number.
    return best[1] if best[0] >= 0.72 else None
