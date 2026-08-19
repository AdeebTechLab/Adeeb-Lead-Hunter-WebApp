from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, Tuple

import httpx

from app.core.config import settings

# Common Pakistan sales-market cities. The fuzzy matcher is intentionally
# conservative: it corrects small spelling mistakes, not unrelated names.
CITY_PROVINCES: Dict[str, str] = {
    "Abbottabad": "Khyber Pakhtunkhwa",
    "Bahawalnagar": "Punjab",
    "Bahawalpur": "Punjab",
    "Bannu": "Khyber Pakhtunkhwa",
    "Bhakkar": "Punjab",
    "Chakwal": "Punjab",
    "Charsadda": "Khyber Pakhtunkhwa",
    "Chiniot": "Punjab",
    "Dera Ghazi Khan": "Punjab",
    "Dera Ismail Khan": "Khyber Pakhtunkhwa",
    "Faisalabad": "Punjab",
    "Gilgit": "Gilgit-Baltistan",
    "Gujranwala": "Punjab",
    "Gujrat": "Punjab",
    "Gwadar": "Balochistan",
    "Haripur": "Khyber Pakhtunkhwa",
    "Hyderabad": "Sindh",
    "Islamabad": "Islamabad Capital Territory",
    "Jacobabad": "Sindh",
    "Jhang": "Punjab",
    "Jhelum": "Punjab",
    "Karachi": "Sindh",
    "Kasur": "Punjab",
    "Khairpur": "Sindh",
    "Khanewal": "Punjab",
    "Kharian": "Punjab",
    "Khuzdar": "Balochistan",
    "Kohat": "Khyber Pakhtunkhwa",
    "Lahore": "Punjab",
    "Larkana": "Sindh",
    "Mandi Bahauddin": "Punjab",
    "Mansehra": "Khyber Pakhtunkhwa",
    "Mardan": "Khyber Pakhtunkhwa",
    "Mianwali": "Punjab",
    "Mirpur": "Azad Jammu and Kashmir",
    "Mirpur Khas": "Sindh",
    "Multan": "Punjab",
    "Muzaffarabad": "Azad Jammu and Kashmir",
    "Nawabshah": "Sindh",
    "Nowshera": "Khyber Pakhtunkhwa",
    "Okara": "Punjab",
    "Peshawar": "Khyber Pakhtunkhwa",
    "Quetta": "Balochistan",
    "Rahim Yar Khan": "Punjab",
    "Rawalpindi": "Punjab",
    "Sahiwal": "Punjab",
    "Sargodha": "Punjab",
    "Sheikhupura": "Punjab",
    "Sialkot": "Punjab",
    "Sukkur": "Sindh",
    "Swabi": "Khyber Pakhtunkhwa",
    "Swat": "Khyber Pakhtunkhwa",
    "Taxila": "Punjab",
    "Turbat": "Balochistan",
    "Vehari": "Punjab",
    "Wah Cantt": "Punjab",
}


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def _local_best(city: str, province: str) -> Tuple[str, float]:
    wanted = _key(city)
    if not wanted:
        return city.strip(), 0.0
    best_city = city.strip()
    best_score = 0.0
    province_key = _key(province)
    for candidate, candidate_province in CITY_PROVINCES.items():
        score = SequenceMatcher(None, wanted, _key(candidate)).ratio()
        if province_key and province_key == _key(candidate_province):
            score += 0.035
        if score > best_score:
            best_city, best_score = candidate, min(score, 1.0)
    return best_city, best_score


def _geoapify_city(city: str, province: str) -> str | None:
    if not settings.geoapify_api_key:
        return None
    params = {
        "text": f"{city}, {province}, Pakistan",
        "type": "city",
        "filter": "countrycode:pk",
        "limit": 5,
        "format": "json",
        "lang": "en",
        "apiKey": settings.geoapify_api_key,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0), follow_redirects=True) as client:
            response = client.get(f"{settings.geoapify_base_url.rstrip('/')}/v1/geocode/autocomplete", params=params)
            response.raise_for_status()
            rows = response.json().get("results") or []
    except (httpx.HTTPError, ValueError, TypeError):
        return None

    original_key = _key(city)
    province_key = _key(province)
    best: tuple[float, str] | None = None
    for row in rows:
        name = str(row.get("city") or row.get("name") or "").strip()
        if not name:
            continue
        score = SequenceMatcher(None, original_key, _key(name)).ratio()
        state = str(row.get("state") or "")
        if province_key and province_key == _key(state):
            score += 0.05
        if best is None or score > best[0]:
            best = (score, name)
    return best[1] if best and best[0] >= 0.58 else None


def resolve_city(city: str, province: str) -> dict:
    """Resolve small city spelling errors without silently changing unrelated input."""
    entered = re.sub(r"\s+", " ", city.strip())
    if not entered:
        return {"city": city, "corrected": False, "source": "input"}

    local_city, local_score = _local_best(entered, province)
    if _key(local_city) == _key(entered):
        return {"city": local_city, "corrected": local_city != entered, "source": "local"}
    # A high local score handles common transpositions such as Lahroe -> Lahore
    # without spending an API request.
    if local_score >= 0.80:
        return {"city": local_city, "corrected": True, "source": "local"}

    remote = _geoapify_city(entered, province)
    if remote:
        return {"city": remote, "corrected": _key(remote) != _key(entered), "source": "geoapify"}

    # For borderline small typos, use the local suggestion only when still close.
    if local_score >= 0.72:
        return {"city": local_city, "corrected": True, "source": "local"}
    return {"city": entered.title(), "corrected": False, "source": "input"}
