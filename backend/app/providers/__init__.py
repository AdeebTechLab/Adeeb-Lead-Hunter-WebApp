from __future__ import annotations

import re
from copy import deepcopy
from typing import Callable

from app.core.config import settings
from app.providers.common import ProviderError, ProviderSearchResult, search_cache
from app.providers.geoapify import geoapify_search, supports_keyword
from app.providers.google_places import google_places_search
from app.providers.osm import osm_search
from app.services.contact_enrichment import enrich_search_items

SearchFunction = Callable[[str, str, str, int], ProviderSearchResult]


def provider_status() -> dict:
    return {
        "default": "auto",
        "providers": [
            {
                "id": "auto",
                "name": "Automatic",
                "configured": True,
                "description": "Uses configured providers in priority order with automatic fallback and contact enrichment.",
            },
            {
                "id": "google",
                "name": "Google Places",
                "configured": bool(settings.google_places_api_key),
                "description": "Official Google Places business details and contact data.",
            },
            {
                "id": "geoapify",
                "name": "Geoapify Places",
                "configured": bool(settings.geoapify_api_key),
                "description": "Geoapify Places business discovery and public place details.",
            },
            {
                "id": "osm",
                "name": "OpenStreetMap",
                "configured": True,
                "description": "OpenStreetMap public business-data fallback.",
            },
        ],
    }


def _identity(item: dict) -> str:
    name = re.sub(r"[^a-z0-9]", "", str(item.get("business_name") or "").casefold())
    city = re.sub(r"[^a-z0-9]", "", str(item.get("city") or "").casefold())
    address = re.sub(r"[^a-z0-9]", "", str(item.get("address") or "").casefold())
    place_id = re.sub(r"[^a-z0-9]", "", str(item.get("google_place_id") or "").casefold())
    if place_id:
        return f"place|{place_id}"
    if address:
        return f"name|{name}|{city}|{address}"
    lat, lon = item.get("latitude"), item.get("longitude")
    if lat is not None and lon is not None:
        return f"name|{name}|{city}|{float(lat):.4f}|{float(lon):.4f}"
    return f"name|{name}|{city}"


def _merge(existing: dict, incoming: dict) -> dict:
    merged = deepcopy(existing)
    for field in [
        "phone",
        "email",
        "website",
        "google_business_url",
        "google_place_id",
        "facebook",
        "instagram",
        "linkedin",
        "address",
        "latitude",
        "longitude",
        "rating",
        "source_url",
    ]:
        if not merged.get(field) and incoming.get(field) is not None:
            merged[field] = incoming.get(field)
    merged["reviews_count"] = max(int(merged.get("reviews_count") or 0), int(incoming.get("reviews_count") or 0))
    merged["tags"] = list(dict.fromkeys([*(merged.get("tags") or []), *(incoming.get("tags") or [])]))
    merged["contact_sources"] = list(
        dict.fromkeys([*(merged.get("contact_sources") or []), *(incoming.get("contact_sources") or [])])
    )
    source_names = list(dict.fromkeys([*(str(merged.get("source") or "").split(" + ")), str(incoming.get("source") or "")]))
    merged["source"] = " + ".join(name for name in source_names if name)
    if incoming.get("contact_confidence") == "High":
        merged["contact_confidence"] = "High"
    return merged


def _candidate_chain(selected: str, keyword: str) -> list[tuple[str, SearchFunction]]:
    if selected == "google":
        if not settings.google_places_api_key:
            raise ProviderError("Google Places is not configured. Add GOOGLE_PLACES_API_KEY or choose Automatic/Geoapify.")
        return [("google", google_places_search)]
    if selected == "geoapify":
        if not settings.geoapify_api_key:
            raise ProviderError("Geoapify is not configured. Add GEOAPIFY_API_KEY or choose OpenStreetMap.")
        return [("geoapify", geoapify_search)]
    if selected == "osm":
        return [("osm", osm_search)]
    if selected != "auto":
        raise ProviderError("Unsupported public-data provider.")

    candidates: list[tuple[str, SearchFunction]] = []
    if settings.google_places_api_key:
        candidates.append(("google", google_places_search))
    if settings.geoapify_api_key and supports_keyword(keyword):
        candidates.append(("geoapify", geoapify_search))
    candidates.append(("osm", osm_search))
    return candidates


def search_public_businesses(provider: str, keyword: str, city: str, province: str, limit: int) -> dict:
    selected = provider.strip().lower()
    cache_key = "|".join([selected, keyword.casefold().strip(), city.casefold().strip(), province.casefold().strip(), str(limit)])
    cached = search_cache.get(cache_key)
    if cached:
        return cached

    candidates = _candidate_chain(selected, keyword)
    errors: list[str] = []
    warnings: list[str] = []
    combined: dict[str, dict] = {}
    providers_used: list[str] = []
    attributions: list[str] = []
    endpoints: list[str] = []

    for name, search_function in candidates:
        try:
            needed = max(1, limit - len(combined))
            result = search_function(keyword, city, province, needed)
            if result.items:
                providers_used.append(name)
                if result.attribution:
                    attributions.append(result.attribution)
                if result.endpoint:
                    endpoints.append(result.endpoint)
                warnings.extend(result.warnings)
                for item in result.items:
                    key = _identity(item)
                    if not key.strip("|"):
                        continue
                    combined[key] = _merge(combined[key], item) if key in combined else item
                    if len(combined) >= limit:
                        break
            else:
                warnings.append(f"{name.title()} returned no matching businesses; another live source was checked.")
        except ProviderError as exc:
            errors.append(str(exc))
            # Explicit selection does not fail over, but raw upstream URLs/status traces
            # are never exposed to the UI. Configuration errors are raised earlier.
            if selected != "auto":
                raise ProviderError(
                    f"{name.title()} could not complete this live search. Retry shortly or choose Automatic so another configured source can be used."
                ) from exc
        if len(combined) >= limit:
            break

    items = list(combined.values())[:limit]
    if not items:
        safe_message = "Live business data is temporarily unavailable or no matching businesses were found. Check the city, niche and configured API key, then retry."
        if errors:
            warnings.append("Automatic retries completed without a usable result.")
        raise ProviderError(safe_message)

    primary_provider = providers_used[0] if len(providers_used) == 1 else "+".join(providers_used)
    items, contact_warnings = enrich_search_items(items, primary_provider)
    warnings.extend(contact_warnings)
    if errors and selected == "auto":
        warnings.append("One live source was unavailable, so Automatic mode used another configured source without stopping the search.")

    payload = {
        "items": items,
        "provider": primary_provider,
        "attribution": " · ".join(dict.fromkeys(attributions)),
        "cached": False,
        "warnings": list(dict.fromkeys(warnings)),
        "endpoint": " + ".join(dict.fromkeys(endpoints)),
    }
    search_cache.set(cache_key, payload, settings.provider_cache_ttl_seconds)
    return payload
