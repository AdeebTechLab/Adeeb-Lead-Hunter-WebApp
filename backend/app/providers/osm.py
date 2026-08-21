from __future__ import annotations

import re
import threading
import time
from typing import Dict, List, Sequence, Tuple

import httpx

from app.core.config import settings
from app.providers.common import ProviderError, ProviderSearchResult
from app.providers.geoapify import geocode_city, normalise_keyword

CATEGORY_FILTERS: Dict[str, Sequence[Tuple[str, Sequence[str]]]] = {
    "restaurant": (("amenity", ("restaurant", "fast_food", "cafe")),),
    "cafe": (("amenity", ("cafe",)),),
    "bakery": (("shop", ("bakery",)),),
    "dentist": (("amenity", ("dentist",)), ("healthcare", ("dentist",))),
    "dental clinic": (("amenity", ("dentist",)), ("healthcare", ("dentist",))),
    "clinic": (("amenity", ("clinic", "doctors")), ("healthcare", ("clinic", "doctor"))),
    "hospital": (("amenity", ("hospital",)), ("healthcare", ("hospital",))),
    "pharmacy": (("amenity", ("pharmacy",)), ("shop", ("chemist",))),
    "medical laboratory": (("healthcare", ("laboratory",)),),
    "laboratory": (("healthcare", ("laboratory",)),),
    "physiotherapy": (("healthcare", ("physiotherapist",)),),
    "veterinarian": (("amenity", ("veterinary",)),),
    "school": (("amenity", ("school", "college", "training")),),
    "academy": (("amenity", ("school", "college", "training")), ("office", ("educational_institution",))),
    "college": (("amenity", ("college",)),),
    "university": (("amenity", ("university",)),),
    "tuition center": (("amenity", ("training",)), ("office", ("educational_institution",))),
    "coaching center": (("amenity", ("training",)), ("office", ("educational_institution",))),
    "daycare": (("amenity", ("kindergarten", "childcare")),),
    "gym": (("leisure", ("fitness_centre", "sports_centre")), ("sport", ("fitness", "gym"))),
    "fitness center": (("leisure", ("fitness_centre", "sports_centre")),),
    "hotel": (("tourism", ("hotel", "guest_house", "motel")),),
    "guest house": (("tourism", ("guest_house", "hotel")),),
    "beauty salon": (("shop", ("beauty", "hairdresser")),),
    "salon": (("shop", ("beauty", "hairdresser")),),
    "spa": (("leisure", ("spa",)), ("shop", ("beauty",))),
    "travel agency": (("shop", ("travel_agency",)), ("office", ("travel_agent",))),
    "law firm": (("office", ("lawyer",)),),
    "lawyer": (("office", ("lawyer",)),),
    "real estate": (("office", ("estate_agent",)),),
    "property dealer": (("office", ("estate_agent",)),),
    "car dealership": (("shop", ("car",)),),
    "auto workshop": (("shop", ("car_repair",)),),
    "car repair": (("shop", ("car_repair",)),),
    "software house": (("office", ("it", "company")),),
    "marketing agency": (("office", ("advertising_agency", "company")),),
    "digital marketing agency": (("office", ("advertising_agency", "company")),),
    "accountant": (("office", ("accountant",)),),
    "architect": (("office", ("architect",)),),
    "insurance": (("office", ("insurance",)),),
    "bank": (("amenity", ("bank",)),),
    "supermarket": (("shop", ("supermarket",)),),
    "grocery store": (("shop", ("convenience", "supermarket")),),
    "clothing store": (("shop", ("clothes",)),),
    "boutique": (("shop", ("clothes",)),),
    "electronics store": (("shop", ("electronics", "computer", "mobile_phone")),),
    "furniture store": (("shop", ("furniture",)),),
    "courier": (("office", ("logistics",)), ("amenity", ("post_office",))),
    "logistics": (("office", ("logistics",)),),
    "coworking space": (("office", ("coworking",)),),
}

# Avoid a Nominatim call for common Pakistan cities. Bboxes are intentionally
# broad city windows, not exact administrative boundaries.
CITY_CENTERS: Dict[str, Tuple[float, float, float]] = {
    "lahore": (31.5204, 74.3587, 0.24),
    "karachi": (24.8607, 67.0011, 0.34),
    "islamabad": (33.6844, 73.0479, 0.23),
    "rawalpindi": (33.5651, 73.0169, 0.22),
    "faisalabad": (31.4504, 73.1350, 0.23),
    "multan": (30.1575, 71.5249, 0.23),
    "peshawar": (34.0151, 71.5249, 0.22),
    "quetta": (30.1798, 66.9750, 0.22),
    "gujranwala": (32.1877, 74.1945, 0.20),
    "sialkot": (32.4945, 74.5229, 0.18),
    "bahawalpur": (29.3956, 71.6836, 0.20),
    "sargodha": (32.0836, 72.6711, 0.19),
    "hyderabad": (25.3960, 68.3578, 0.21),
    "sukkur": (27.7244, 68.8228, 0.18),
    "abbottabad": (34.1688, 73.2215, 0.16),
    "gujrat": (32.5731, 74.1005, 0.17),
    "jhelum": (32.9425, 73.7257, 0.16),
    "kasur": (31.1168, 74.4497, 0.16),
    "sahiwal": (30.6682, 73.1114, 0.17),
    "okara": (30.8138, 73.4534, 0.16),
    "rahim yar khan": (28.4212, 70.2989, 0.18),
    "dera ghazi khan": (30.0561, 70.6348, 0.18),
    "mirpur": (33.1478, 73.7519, 0.16),
    "muzaffarabad": (34.3700, 73.4711, 0.16),
    "gilgit": (35.9208, 74.3080, 0.16),
}

_geocode_lock = threading.Lock()
_last_geocode_at = 0.0
_geocode_cache: Dict[str, tuple[float, float, tuple[float, float, float, float]]] = {}


def _headers() -> dict:
    headers = {"User-Agent": settings.public_data_user_agent, "Accept": "application/json"}
    if settings.public_data_referer:
        headers["Referer"] = settings.public_data_referer
    return headers


def _bbox_from_center(lat: float, lon: float, delta: float) -> tuple[float, float, float, float]:
    return lat - delta, lon - delta, lat + delta, lon + delta


def _location(city: str, province: str) -> tuple[float, float, tuple[float, float, float, float]]:
    global _last_geocode_at
    cache_key = f"{city.casefold()}|{province.casefold()}"
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]

    city_key = re.sub(r"\s+", " ", city.strip().casefold())
    if city_key in CITY_CENTERS:
        lat, lon, delta = CITY_CENTERS[city_key]
        result = (lat, lon, _bbox_from_center(lat, lon, delta))
        _geocode_cache[cache_key] = result
        return result

    if settings.geoapify_api_key:
        timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)
        try:
            with httpx.Client(timeout=timeout, headers=_headers(), follow_redirects=True) as client:
                place = geocode_city(client, city, province)
            lat, lon = float(place["lat"]), float(place["lon"])
            box = place.get("bbox") or []
            if isinstance(box, dict):
                south = float(box.get("lat1", lat - 0.2))
                north = float(box.get("lat2", lat + 0.2))
                west = float(box.get("lon1", lon - 0.2))
                east = float(box.get("lon2", lon + 0.2))
                bbox = (south, west, north, east)
            else:
                bbox = _bbox_from_center(lat, lon, 0.22)
            result = (lat, lon, bbox)
            _geocode_cache[cache_key] = result
            return result
        except Exception:
            pass

    # Last-resort Nominatim path, rate-limited and policy-compliant.
    with _geocode_lock:
        wait = 1.05 - (time.monotonic() - _last_geocode_at)
        if wait > 0:
            time.sleep(wait)
        params = {
            "q": f"{city}, {province}, Pakistan",
            "countrycodes": "pk",
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(20.0), headers=_headers(), follow_redirects=True) as client:
                response = client.get(f"{settings.nominatim_url.rstrip('/')}/search", params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise ProviderError("OpenStreetMap could not locate that city. Automatic mode can use Geoapify when its API key is configured.") from exc
        finally:
            _last_geocode_at = time.monotonic()

    if not data:
        raise ProviderError("The city could not be found. Check the city and province spelling.")
    item = data[0]
    lat, lon = float(item["lat"]), float(item["lon"])
    box = item.get("boundingbox") or []
    if len(box) == 4:
        south, north, west, east = map(float, box)
        bbox = (south, west, north, east)
    else:
        bbox = _bbox_from_center(lat, lon, 0.22)
    result = (lat, lon, bbox)
    _geocode_cache[cache_key] = result
    return result


def _build_query(keyword: str, bbox: tuple[float, float, float, float], fetch_count: int) -> str:
    south, west, north, east = bbox
    area = f"({south:.6f},{west:.6f},{north:.6f},{east:.6f})"
    key = normalise_keyword(keyword)
    filters = CATEGORY_FILTERS.get(key)
    selectors: List[str] = []
    if filters:
        for tag_key, values in filters:
            for value in values:
                selectors.append(f'nwr["{tag_key}"="{value}"]["name"]{area};')
    else:
        cleaned = re.sub(r"[^a-zA-Z0-9 &.'-]", "", keyword).strip()[:70]
        if not cleaned:
            raise ProviderError("Enter a valid business keyword.")
        escaped = re.escape(cleaned).replace('"', '\\"')
        selectors.append(f'nwr["name"~"{escaped}",i]{area};')
    safe_count = min(max(int(fetch_count), 20), 300)
    return "[out:json][timeout:28];(" + "".join(selectors) + f");out tags center {safe_count};"


def _fetch_overpass(query: str) -> tuple[List[dict], str, List[str]]:
    warnings: List[str] = []
    retryable = {408, 429, 500, 502, 503, 504}
    timeout = httpx.Timeout(connect=10.0, read=settings.provider_timeout_seconds, write=20.0, pool=10.0)
    configured = [url.strip() for url in settings.overpass_urls if url.strip()]
    for endpoint_index, endpoint in enumerate(configured):
        for attempt in range(1, settings.provider_retry_attempts + 1):
            try:
                with httpx.Client(timeout=timeout, headers=_headers(), follow_redirects=True) as client:
                    response = client.post(endpoint, data={"data": query})
                if response.status_code in retryable:
                    raise httpx.HTTPStatusError("retryable status", request=response.request, response=response)
                response.raise_for_status()
                payload = response.json()
                if endpoint_index > 0:
                    warnings.append("The primary OpenStreetMap query service was busy, so a live failover service was used.")
                return payload.get("elements") or [], endpoint, warnings
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.NetworkError, ValueError):
                if attempt < settings.provider_retry_attempts:
                    time.sleep(min(0.8 * attempt, 2.0))
                    continue
                break
    raise ProviderError("OpenStreetMap live search is temporarily busy. Automatic mode can continue through Google Places or Geoapify when configured.")


def _normalise_item(item: dict, keyword: str, city: str, province: str) -> dict | None:
    tags = item.get("tags") or {}
    name = tags.get("name")
    if not name:
        return None
    center = item.get("center") or {}
    lat = item.get("lat", center.get("lat"))
    lon = item.get("lon", center.get("lon"))
    phone = tags.get("contact:phone") or tags.get("phone") or tags.get("contact:mobile")
    website = tags.get("contact:website") or tags.get("website") or tags.get("url")
    email = tags.get("contact:email") or tags.get("email")
    facebook = tags.get("contact:facebook") or tags.get("facebook")
    instagram = tags.get("contact:instagram") or tags.get("instagram")
    linkedin = tags.get("contact:linkedin") or tags.get("linkedin")
    address_parts = [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:suburb"), tags.get("addr:city")]
    address = ", ".join(part for part in address_parts if part) or None
    osm_type = item.get("type", "node")
    osm_id = item.get("id")
    return {
        "business_name": name,
        "category": keyword.strip().title(),
        "city": city.title(),
        "province": province.title(),
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
        "source": "OpenStreetMap",
        "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        "reviews_count": 0,
        "rating": None,
        "tags": [keyword.strip().title(), city.title(), "Real-time API", "OpenStreetMap"],
        "contact_sources": ["OpenStreetMap"] if phone or email or website else [],
        "contact_confidence": "Medium" if phone or email else "Low",
        "contact_status": "Contactable" if phone or email else "Website available" if website else "Research needed",
    }


def osm_search(keyword: str, city: str, province: str, limit: int, offset: int = 0) -> ProviderSearchResult:
    _, _, bbox = _location(city, province)
    # Overpass has no simple offset parameter. Fetch a stable larger window,
    # normalise/dedupe it, then slice locally. This keeps OSM as a lightweight
    # fallback while allowing repeated searches to move past qualified leads.
    fetch_count = min(max((max(offset, 0) + max(limit, 1)) * 2, 40), 300)
    query = _build_query(keyword, bbox, fetch_count)
    elements, endpoint, warnings = _fetch_overpass(query)
    elements = sorted(elements, key=lambda row: (str(row.get("type") or ""), int(row.get("id") or 0)))
    all_items: List[dict] = []
    seen = set()
    for element in elements:
        item = _normalise_item(element, keyword, city, province)
        if not item:
            continue
        key = (item["business_name"].casefold(), (item.get("address") or "").casefold(), item.get("phone") or "")
        if key in seen:
            continue
        seen.add(key)
        all_items.append(item)
    start = max(int(offset), 0)
    items = all_items[start:start + max(int(limit), 1)]
    return ProviderSearchResult(
        items=items,
        provider="osm",
        attribution="© OpenStreetMap contributors",
        warnings=warnings,
        endpoint="OpenStreetMap Overpass API",
    )
