from __future__ import annotations

import math
import re
import uuid
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, Optional

import httpx

from app.core.config import settings
from app.providers.common import TTLCache

_contact_cache = TTLCache()

_DISCOVER_ATTRIBUTES = "results(id,type,title,subtitles,position,address,distanceInMeters,contacts,more)"
_DETAILS_ATTRIBUTES = "id,type,title,subtitles,position,address,distanceInMeters,contacts"


def _normalise_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()
    noise = {
        "pvt", "private", "limited", "ltd", "llc", "inc", "company", "co",
        "official", "actual", "location", "branch", "outlet",
    }
    tokens = [token for token in text.split() if token not in noise]
    return " ".join(tokens)


def _name_similarity(left: str, right: str) -> float:
    a, b = _normalise_name(left), _normalise_name(right)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    a_tokens, b_tokens = set(a.split()), set(b.split())
    overlap = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
    containment = 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    # Branch labels such as "Actual Location" or "Main Branch" should not
    # block an otherwise exact POI match. Require at least two words so a
    # generic one-word name does not become an unsafe match.
    if len(shorter.split()) >= 2 and shorter in longer:
        containment = 0.93
    return max(ratio, overlap, containment)


def _normalise_address(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()
    noise = {"pakistan", "pk", "road", "rd", "street", "st", "block", "sector", "near"}
    return " ".join(token for token in text.split() if token not in noise)


def _address_similarity(left: str, right: str) -> float:
    a, b = _normalise_address(left), _normalise_address(right)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    a_tokens, b_tokens = set(a.split()), set(b.split())
    overlap = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
    return max(ratio, overlap)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _city_matches(address: Dict[str, Any], city: str) -> bool:
    target = re.sub(r"[^a-z0-9]", "", (city or "").casefold())
    if not target:
        return True
    values = [
        address.get("municipality"),
        address.get("municipalitySubdivision"),
        address.get("countrySecondarySubdivision"),
        address.get("countryTertiarySubdivision"),
        address.get("freeformAddress"),
    ]
    haystack = re.sub(r"[^a-z0-9]", "", " ".join(str(value or "") for value in values).casefold())
    return target in haystack


def _candidate_score(item: Dict[str, Any], result: Dict[str, Any]) -> tuple[float, Optional[float], float, float, bool]:
    poi = result.get("poi") or {}
    similarity = _name_similarity(str(item.get("business_name") or ""), str(poi.get("name") or ""))
    candidate_address = str((result.get("address") or {}).get("freeformAddress") or "")
    address_similarity = _address_similarity(str(item.get("address") or ""), candidate_address)
    position = result.get("position") or {}
    distance: Optional[float] = None
    if item.get("latitude") is not None and item.get("longitude") is not None and position.get("lat") is not None and position.get("lon") is not None:
        try:
            distance = _distance_m(
                float(item["latitude"]), float(item["longitude"]),
                float(position["lat"]), float(position["lon"]),
            )
        except (TypeError, ValueError):
            distance = None
    city_ok = _city_matches(result.get("address") or {}, str(item.get("city") or ""))
    if distance is not None:
        proximity = max(0.0, 1.0 - min(distance, 5000.0) / 5000.0)
        score = similarity * 0.64 + proximity * 0.20 + address_similarity * 0.11 + (0.05 if city_ok else 0.0)
    else:
        score = similarity * 0.82 + address_similarity * 0.10 + (0.08 if city_ok else 0.0)
    return score, distance, similarity, address_similarity, city_ok


def _accepted_match(score: float, distance: Optional[float], similarity: float, address_similarity: float, city_ok: bool) -> bool:
    if distance is not None:
        if distance > settings.tomtom_contact_match_radius_m:
            return False
        # Coordinates are strong evidence, but never accept a nearby unrelated
        # restaurant/clinic merely because it is physically close. Address
        # agreement can safely compensate for harmless name/branch differences.
        if distance <= 60:
            return city_ok and (similarity >= 0.48 or (similarity >= 0.38 and address_similarity >= 0.45)) and score >= 0.57
        if distance <= 150:
            return city_ok and (similarity >= 0.56 or (similarity >= 0.46 and address_similarity >= 0.55)) and score >= 0.63
        if distance <= 500:
            return city_ok and similarity >= 0.68 and score >= 0.70
        return city_ok and similarity >= 0.80 and score >= 0.78
    return city_ok and similarity >= 0.88 and score >= 0.86


def _normalise_website(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    value = str(url).strip()
    if not value:
        return None
    return value if value.startswith(("http://", "https://")) else f"https://{value}"


def _contact_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, str):
        if value.strip():
            values.append(value.strip())
    elif isinstance(value, dict):
        # Current Places v3 uses strings, but tolerate wrapper objects so the
        # parser stays forward-compatible with provider response variations.
        preferred_keys = ("value", "phone", "number", "url", "website", "href")
        picked = False
        for key in preferred_keys:
            if key in value:
                values.extend(_contact_values(value.get(key)))
                picked = True
        if not picked:
            for nested in value.values():
                values.extend(_contact_values(nested))
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            values.extend(_contact_values(nested))
    return values


def _first_contact(raw: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    phones: list[str] = []
    websites: list[str] = []
    contacts = raw.get("contacts") or []
    if isinstance(contacts, dict):
        contacts = [contacts]
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        phones.extend(_contact_values(contact.get("phones")))
        websites.extend(_contact_values(contact.get("websites")))
    phones = list(dict.fromkeys(value for value in phones if value))
    websites = list(dict.fromkeys(value for value in websites if value))
    return (phones[0] if phones else None, websites[0] if websites else None)


def _freeform_address(raw: Dict[str, Any]) -> str:
    subtitles = [str(value).strip() for value in (raw.get("subtitles") or []) if str(value).strip()]
    if subtitles:
        return ", ".join(subtitles)
    address = raw.get("address") or {}
    street = " ".join(part for part in [str(address.get("houseNumber") or "").strip(), str(address.get("street") or "").strip()] if part)
    parts = [
        street,
        str(address.get("municipalitySubdivision") or "").strip(),
        str(address.get("municipality") or "").strip(),
        str(address.get("postalCode") or "").strip(),
        str(address.get("country") or "").strip(),
    ]
    return ", ".join(dict.fromkeys(part for part in parts if part))


def _normalise_places_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Places Search API v3 data to the provider-neutral shape already used by enrichment."""
    coordinates = (raw.get("position") or {}).get("coordinates") or []
    lon = coordinates[0] if len(coordinates) >= 2 else None
    lat = coordinates[1] if len(coordinates) >= 2 else None
    phone, website = _first_contact(raw)
    address = deepcopy(raw.get("address") or {})
    address["freeformAddress"] = _freeform_address(raw)
    return {
        "type": "POI" if str(raw.get("type") or "").casefold() == "poi" else str(raw.get("type") or "").upper(),
        "id": raw.get("id"),
        "poi": {
            "name": raw.get("title"),
            "phone": phone,
            "url": website,
        },
        "position": {"lat": lat, "lon": lon},
        "address": address,
        "distance": raw.get("distanceInMeters"),
        "_places_raw": raw,
    }


def _best_accepted(item: Dict[str, Any], results: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    best: Optional[tuple[float, Optional[float], float, float, bool, Dict[str, Any]]] = None
    for result in results:
        if result.get("type") != "POI" or not (result.get("poi") or {}).get("name"):
            continue
        score, distance, similarity, address_similarity, city_ok = _candidate_score(item, result)
        if not _accepted_match(score, distance, similarity, address_similarity, city_ok):
            continue
        if best is None or score > best[0]:
            best = (score, distance, similarity, address_similarity, city_ok, result)
    if best is None:
        return None
    score, distance, similarity, address_similarity, city_ok, result = best
    candidate = deepcopy(result)
    candidate["_match"] = {
        "score": score,
        "distance": distance,
        "similarity": similarity,
        "address_similarity": address_similarity,
        "city_ok": city_ok,
    }
    return candidate


def _places_headers(attributes: str, session_id: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "TomTom-Api-Key": settings.tomtom_api_key,
        "TomTom-Api-Version": "3",
        "Attributes": attributes,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": settings.public_data_user_agent,
        "Tracking-Id": str(uuid.uuid4()),
    }
    if session_id:
        headers["Session-Id"] = session_id
    if settings.public_data_referer:
        headers["Referer"] = settings.public_data_referer
    return headers


def _discover_body(item: Dict[str, Any]) -> Dict[str, Any]:
    name = str(item.get("business_name") or "").strip()
    address = str(item.get("address") or "").strip()
    city = str(item.get("city") or "").strip()
    province = str(item.get("province") or "").strip()
    # Use the discovered identity plus its address/city. Coordinates still
    # constrain the candidate set, while the extra address text helps TomTom
    # distinguish same-name branches and improves contact matching coverage.
    query = ", ".join(part for part in [name, address or city, province] if part)
    body: Dict[str, Any] = {
        "query": query,
        "maxResults": 8,
        "filters": {
            "types": ["poi"],
            "countryCodesIso2": ["PK"],
        },
    }
    lat, lon = item.get("latitude"), item.get("longitude")
    if lat is not None and lon is not None:
        try:
            lat_f, lon_f = float(lat), float(lon)
            point = {"type": "point", "coordinates": [lon_f, lat_f]}
            body["origin"] = point
            body["preferences"] = {"geometry": point}
            body["filters"]["geometry"] = {
                "type": "circle",
                "center": point,
                "radiusInMeters": int(max(500, settings.tomtom_contact_match_radius_m)),
            }
        except (TypeError, ValueError):
            pass
    return body


def _discover(client: httpx.Client, item: Dict[str, Any], session_id: str) -> list[Dict[str, Any]]:
    endpoint = f"{settings.tomtom_base_url.rstrip('/')}/maps/orbis/places/discover"
    try:
        response = client.post(
            endpoint,
            json=_discover_body(item),
            headers=_places_headers(_DISCOVER_ATTRIBUTES, session_id),
        )
        response.raise_for_status()
        payload = response.json()
        return [_normalise_places_result(raw) for raw in (payload.get("results") or [])]
    except (httpx.HTTPError, ValueError, TypeError):
        return []


def _details(client: httpx.Client, place_id: str, item: Dict[str, Any], session_id: str) -> Optional[Dict[str, Any]]:
    if not place_id:
        return None
    endpoint = f"{settings.tomtom_base_url.rstrip('/')}/maps/orbis/places/details/pois/{place_id}"
    params: Dict[str, Any] = {}
    lat, lon = item.get("latitude"), item.get("longitude")
    if lat is not None and lon is not None:
        try:
            params["origin"] = f"{float(lon)},{float(lat)}"
        except (TypeError, ValueError):
            pass
    try:
        response = client.get(
            endpoint,
            params=params,
            headers=_places_headers(_DETAILS_ATTRIBUTES, session_id),
        )
        response.raise_for_status()
        payload = response.json()
        return _normalise_places_result(payload)
    except (httpx.HTTPError, ValueError, TypeError):
        return None


def _candidate_with_contacts(client: httpx.Client, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Match an existing Geoapify/OSM lead against TomTom Places Search API v3.

    Discovery remains with Geoapify/OpenStreetMap. TomTom is used only to enrich
    the already-discovered POI with verified public phone/website data.
    """
    name = str(item.get("business_name") or "").strip()
    if not name:
        return None

    session_id = str(uuid.uuid4())
    best = _best_accepted(item, _discover(client, item, session_id))
    if best is None:
        return None

    poi = best.get("poi") or {}
    # Discover often contains contacts already. Details is used only when the
    # direct phone is still missing; this preserves the free quota while still
    # improving coverage for records that are not yet callable.
    if not poi.get("phone") and best.get("id"):
        detailed = _details(client, str(best.get("id")), item, session_id)
        if detailed and detailed.get("type") == "POI":
            # The discover candidate already passed strict identity checks. Keep
            # that evidence when merging the richer Details response.
            detailed["_match"] = best.get("_match")
            best = detailed
    return best


def tomtom_exact_lookup(item: Dict[str, Any]) -> Optional[dict]:
    """Cross-check a Geoapify/OSM lead and return verified public contact data."""
    if not settings.tomtom_api_key:
        return None
    name = str(item.get("business_name") or "").strip()
    city = str(item.get("city") or "").strip()
    if not name:
        return None

    lat, lon = item.get("latitude"), item.get("longitude")
    rounded_position = ""
    if lat is not None and lon is not None:
        try:
            rounded_position = f"|{float(lat):.4f}|{float(lon):.4f}"
        except (TypeError, ValueError):
            rounded_position = ""
    cache_key = f"tomtom-places-v3|{_normalise_name(name)}|{city.casefold()}{rounded_position}"
    cached = _contact_cache.get(cache_key)
    if cached:
        return deepcopy(cached.get("result"))

    timeout = httpx.Timeout(connect=5.0, read=settings.tomtom_contact_timeout_seconds, write=5.0, pool=5.0)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            result = _candidate_with_contacts(client, item)
    except httpx.HTTPError:
        result = None

    if result is None:
        # Do not retain a negative match for a week: transient quota/network or
        # configuration issues should recover quickly after they are fixed.
        _contact_cache.set(cache_key, {"result": None}, min(settings.tomtom_contact_cache_ttl_seconds, 600))
        return None

    poi = result.get("poi") or {}
    address = result.get("address") or {}
    position = result.get("position") or {}
    match = result.get("_match") or {}
    phone = str(poi.get("phone") or "").strip() or None
    website = _normalise_website(poi.get("url"))
    if not phone and not website:
        _contact_cache.set(cache_key, {"result": None}, min(settings.tomtom_contact_cache_ttl_seconds, 600))
        return None

    similarity = float(match.get("similarity") or 0.0)
    distance = match.get("distance")
    confidence = "High" if similarity >= 0.90 and (distance is None or float(distance) <= 800) else "Medium"
    matched = {
        "tomtom_id": result.get("id"),
        "matched_name": poi.get("name"),
        "phone": phone,
        "website": website,
        "address": address.get("freeformAddress"),
        "latitude": position.get("lat"),
        "longitude": position.get("lon"),
        "match_confidence": confidence,
        "match_score": round(float(match.get("score") or 0.0), 3),
        "name_similarity": round(similarity, 3),
        "address_similarity": round(float(match.get("address_similarity") or 0.0), 3),
        "distance_m": round(float(distance)) if distance is not None else None,
        "city_match": bool(match.get("city_ok")),
        "source": "TomTom Places Search API",
    }
    _contact_cache.set(cache_key, {"result": deepcopy(matched)}, settings.tomtom_contact_cache_ttl_seconds)
    return matched
