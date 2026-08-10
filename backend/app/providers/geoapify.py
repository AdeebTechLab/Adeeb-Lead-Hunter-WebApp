from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.providers.common import ProviderError, ProviderSearchResult

# Geoapify categories are deliberately broad enough to support the agency's
# target niches and common Pakistan local-business searches. Unknown custom
# keywords use a broad local-business category set plus Geoapify's name filter.
CATEGORY_MAP: Dict[str, str] = {
    "restaurant": "catering.restaurant,catering.fast_food,catering.cafe",
    "cafe": "catering.cafe,catering.coffee_shop",
    "bakery": "commercial.food_and_drink.bakery,catering.cafe",
    "real estate": "service.estate_agent,office.estate_agent",
    "property dealer": "service.estate_agent,office.estate_agent",
    "hospital": "healthcare.hospital",
    "clinic": "healthcare.clinic_or_praxis,healthcare.doctor",
    "medical laboratory": "healthcare.laboratory",
    "laboratory": "healthcare.laboratory",
    "dental clinic": "healthcare.dentist",
    "dentist": "healthcare.dentist",
    "pharmacy": "healthcare.pharmacy,commercial.health_and_beauty.pharmacy",
    "physiotherapy": "healthcare.physiotherapist",
    "veterinarian": "healthcare.veterinary",
    "beauty salon": "service.beauty,service.beauty.hairdresser,service.beauty.spa",
    "salon": "service.beauty,service.beauty.hairdresser",
    "spa": "service.beauty.spa",
    "school": "education.school",
    "academy": "education.college,education.language_school,education.music_school,office.educational_institution",
    "college": "education.college",
    "university": "education.university",
    "tuition center": "education.training,office.educational_institution",
    "coaching center": "education.training,office.educational_institution",
    "daycare": "childcare,education.kindergarten",
    "gym": "sport.fitness,sport.fitness.gym,sport.fitness.fitness_centre",
    "fitness center": "sport.fitness,sport.fitness.gym,sport.fitness.fitness_centre",
    "hotel": "accommodation.hotel,accommodation.guest_house,accommodation.motel",
    "guest house": "accommodation.guest_house,accommodation.hotel",
    "travel agency": "service.travel_agency,office.travel_agent",
    "law firm": "office.lawyer",
    "lawyer": "office.lawyer",
    "car dealership": "commercial.vehicle,commercial.vehicle.car",
    "auto workshop": "service.vehicle.repair,commercial.vehicle.repair",
    "car repair": "service.vehicle.repair,commercial.vehicle.repair",
    "software house": "office.it,office.company",
    "digital marketing agency": "office.advertising_agency,office.company",
    "marketing agency": "office.advertising_agency,office.company",
    "accountant": "office.accountant",
    "architect": "office.architect",
    "construction company": "office.company,commercial.trade",
    "insurance": "office.insurance",
    "bank": "commercial.financial.bank",
    "supermarket": "commercial.supermarket",
    "grocery store": "commercial.food_and_drink.grocery",
    "clothing store": "commercial.clothing",
    "boutique": "commercial.clothing",
    "electronics store": "commercial.elektronics,commercial.electronics",
    "furniture store": "commercial.houseware_and_hardware.furniture",
    "wedding hall": "catering.restaurant,entertainment.culture.events_venue",
    "banquet hall": "catering.restaurant,entertainment.culture.events_venue",
    "event planner": "office.company,service",
    "photographer": "service.photography,office.company",
    "courier": "office.logistics,service.delivery",
    "logistics": "office.logistics,office.company",
    "coworking space": "office.coworking",
    "any local business": "commercial,service,office,catering,healthcare,education,accommodation,sport",
}

ALIASES = {
    "restaurants": "restaurant",
    "cafes": "cafe",
    "hospitals": "hospital",
    "clinics": "clinic",
    "dental clinics": "dental clinic",
    "dentists": "dentist",
    "salons": "beauty salon",
    "beauty salons": "beauty salon",
    "schools": "school",
    "academies": "academy",
    "gyms": "gym",
    "hotels": "hotel",
    "guest houses": "guest house",
    "travel agencies": "travel agency",
    "law firms": "law firm",
    "lawyers": "lawyer",
    "car dealerships": "car dealership",
    "car dealers": "car dealership",
    "property dealers": "property dealer",
    "real estate agents": "real estate",
    "pharmacies": "pharmacy",
    "software houses": "software house",
    "marketing agencies": "marketing agency",
}

BROAD_LOCAL_BUSINESS_CATEGORIES = "commercial,service,office,catering,healthcare,education,accommodation,sport"


def normalise_keyword(keyword: str) -> str:
    cleaned = re.sub(r"\s+", " ", keyword.strip().lower())
    return ALIASES.get(cleaned, cleaned)


def supports_keyword(keyword: str) -> bool:
    return bool(normalise_keyword(keyword))


def _first_text(*values: Any) -> Optional[str]:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return None


def _raw_value(raw: Dict[str, Any], *keys: str) -> Optional[str]:
    return _first_text(*(raw.get(key) for key in keys))


def _request_json(client: httpx.Client, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException as exc:
        raise ProviderError("Geoapify timed out. Automatic mode will retry another live source.") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {401, 403}:
            raise ProviderError("Geoapify access was rejected. Check GEOAPIFY_API_KEY and its restrictions.") from exc
        if status == 429:
            raise ProviderError("Geoapify quota or rate limit was reached. Try again later.") from exc
        raise ProviderError("Geoapify is temporarily unavailable.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError("Geoapify could not return valid place data.") from exc


def geocode_city(client: httpx.Client, city: str, province: str) -> Dict[str, Any]:
    data = _request_json(
        client,
        f"{settings.geoapify_base_url.rstrip('/')}/v1/geocode/search",
        {
            "text": f"{city}, {province}, Pakistan",
            "filter": "countrycode:pk",
            "type": "city",
            "limit": 1,
            "format": "json",
            "apiKey": settings.geoapify_api_key,
        },
    )
    results = data.get("results") or []
    if not results:
        raise ProviderError("The city could not be found in Pakistan. Check the city and province spelling.")
    return results[0]


def _source_url(lat: Optional[float], lon: Optional[float], raw: Dict[str, Any]) -> Optional[str]:
    osm_id = raw.get("osm_id")
    osm_type = str(raw.get("osm_type") or "").lower()
    type_map = {"n": "node", "w": "way", "r": "relation", "node": "node", "way": "way", "relation": "relation"}
    if osm_id and osm_type in type_map:
        return f"https://www.openstreetmap.org/{type_map[osm_type]}/{osm_id}"
    if lat is not None and lon is not None:
        return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"
    return None


def _normalise_feature(feature: Dict[str, Any], keyword: str, city: str, province: str) -> Optional[dict]:
    props = feature.get("properties") or {}
    datasource = props.get("datasource") or {}
    raw = datasource.get("raw") or {}
    contact = props.get("contact") or {}
    lat = props.get("lat")
    lon = props.get("lon")
    if lat is None or lon is None:
        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coordinates) >= 2:
            lon, lat = coordinates[0], coordinates[1]

    name = _first_text(props.get("name"), raw.get("name"), props.get("address_line1"))
    if not name:
        return None

    phone = _first_text(contact.get("phone"), contact.get("mobile"), _raw_value(raw, "contact:phone", "phone", "contact:mobile"))
    email = _first_text(contact.get("email"), _raw_value(raw, "contact:email", "email"))
    website = _first_text(contact.get("website"), _raw_value(raw, "contact:website", "website", "url"))
    facebook = _first_text(contact.get("facebook"), _raw_value(raw, "contact:facebook", "facebook"))
    instagram = _first_text(contact.get("instagram"), _raw_value(raw, "contact:instagram", "instagram"))
    linkedin = _first_text(contact.get("linkedin"), _raw_value(raw, "contact:linkedin", "linkedin"))
    address = _first_text(props.get("formatted"), props.get("address_line2"), raw.get("addr:full"))
    place_id = _first_text(props.get("place_id"))

    return {
        "business_name": name,
        "category": keyword.strip().title(),
        "city": _first_text(props.get("city"), city.title()) or city.title(),
        "province": _first_text(props.get("state"), province.title()) or province.title(),
        "phone": phone,
        "email": email,
        "website": website,
        "google_business_url": None,
        "google_place_id": None,
        "facebook": facebook,
        "instagram": instagram,
        "linkedin": linkedin,
        "address": address,
        "latitude": lat,
        "longitude": lon,
        "source": "Geoapify Places / OpenStreetMap",
        "source_url": _source_url(lat, lon, raw),
        "provider_place_id": place_id,
        "reviews_count": 0,
        "rating": None,
        "tags": [keyword.strip().title(), city.title(), "Real-time API", "Geoapify"],
        "contact_sources": ["Geoapify / OpenStreetMap"] if phone or email or website else [],
        "contact_confidence": "Medium" if phone or email else "Low",
        "contact_status": "Contactable" if phone or email else "Website available" if website else "Research needed",
    }


def geoapify_search(keyword: str, city: str, province: str, limit: int) -> ProviderSearchResult:
    if not settings.geoapify_api_key:
        raise ProviderError("Geoapify is not configured. Add GEOAPIFY_API_KEY in backend/.env.")
    key = normalise_keyword(keyword)
    categories = CATEGORY_MAP.get(key, BROAD_LOCAL_BUSINESS_CATEGORIES)

    timeout = httpx.Timeout(connect=10.0, read=settings.provider_timeout_seconds, write=15.0, pool=10.0)
    headers = {"User-Agent": settings.public_data_user_agent, "Accept": "application/json"}
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        place = geocode_city(client, city, province)
        place_id = place.get("place_id")
        lat, lon = place.get("lat"), place.get("lon")
        location_filter = f"place:{place_id}" if place_id else f"circle:{lon},{lat},25000"
        params: Dict[str, Any] = {
            "categories": categories,
            "filter": location_filter,
            "bias": f"proximity:{lon},{lat}",
            "limit": min(max(limit * 2, limit), 80),
            "lang": "en",
            "apiKey": settings.geoapify_api_key,
        }
        if key not in CATEGORY_MAP:
            params["name"] = keyword.strip()
        data = _request_json(client, f"{settings.geoapify_base_url.rstrip('/')}/v2/places", params)

    items: List[dict] = []
    seen = set()
    for feature in data.get("features") or []:
        item = _normalise_feature(feature, keyword, city, province)
        if not item:
            continue
        # For custom text searches, require a reasonable name match to improve precision.
        if key not in CATEGORY_MAP and key.casefold() not in item["business_name"].casefold():
            continue
        dedupe_key = (item["business_name"].casefold(), (item.get("address") or "").casefold(), item.get("phone") or "")
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(item)
        if len(items) >= limit:
            break

    return ProviderSearchResult(
        items=items,
        provider="geoapify",
        attribution="Powered by Geoapify and OpenStreetMap contributors",
        endpoint="Geoapify Places API",
    )
