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
        "text": ", ".join(part for part in [city, province, "Pakistan"] if str(part or "").strip()),
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


def resolve_city(city: str, province: str = "") -> dict:
    """Resolve common Pakistan city spelling mistakes and infer its province.

    Province is intentionally optional because the Lead Hunter UI no longer asks
    users to select it. Known-city matches are resolved locally; Geoapify is used
    only when the city is not confidently known.
    """
    entered = re.sub(r"\s+", " ", city.strip())
    province = re.sub(r"\s+", " ", (province or "").strip())
    if not entered:
        return {"city": city, "province": province, "corrected": False, "source": "input"}

    local_city, local_score = _local_best(entered, province)
    if _key(local_city) == _key(entered) or local_score >= 0.80:
        inferred = CITY_PROVINCES.get(local_city, province)
        return {
            "city": local_city,
            "province": inferred,
            "corrected": _key(local_city) != _key(entered) or local_city != entered,
            "source": "local",
        }

    remote = _geoapify_city(entered, province)
    if remote:
        inferred = CITY_PROVINCES.get(remote, province)
        return {
            "city": remote,
            "province": inferred,
            "corrected": _key(remote) != _key(entered),
            "source": "geoapify",
        }

    if local_score >= 0.72:
        inferred = CITY_PROVINCES.get(local_city, province)
        return {"city": local_city, "province": inferred, "corrected": True, "source": "local"}

    # Unknown cities are still allowed for manual entry. The provider geocoder will
    # validate them. Leaving province blank avoids forcing a wrong Punjab filter.
    return {"city": entered.title(), "province": province, "corrected": False, "source": "input"}
