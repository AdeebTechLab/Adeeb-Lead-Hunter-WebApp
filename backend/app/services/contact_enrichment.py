from __future__ import annotations

import ipaddress
import json
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.providers.google_places import google_exact_lookup

PHONE_RE = re.compile(r"(?:(?:\+|00)92[\s().-]*|0)(?:3\d{2}|[2-9]\d{1,3})[\s().-]*\d{3,4}[\s().-]*\d{3,4}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
CONTACT_PATH_WORDS = ("contact", "contact-us", "about", "about-us", "reach-us")


def google_maps_search_url(item: Dict[str, Any]) -> str:
    query = ", ".join(
        part for part in [item.get("business_name"), item.get("address"), item.get("city"), item.get("province"), "Pakistan"] if part
    )
    return (
        "https://www.google.com/maps/search/?api=1&query="
        f"{quote_plus(query)}&utm_source=ai_lead_hunter&utm_campaign=lead_contact"
    )


def _normalise_site(url: str) -> str:
    candidate = url.strip()
    if not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Invalid website URL")
    try:
        for address in socket.getaddrinfo(parsed.hostname, None):
            ip = ipaddress.ip_address(address[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("Private network address")
    except socket.gaierror as exc:
        raise ValueError("Website host could not be resolved") from exc
    return candidate


def _clean_phone(value: str) -> Optional[str]:
    text = value.strip().replace("tel:", "", 1).split("?")[0]
    digits = re.sub(r"\D", "", text)
    if digits.startswith("0092"):
        digits = digits[2:]
    if digits.startswith("92") and 11 <= len(digits) <= 13:
        return f"+{digits}"
    if digits.startswith("0") and 10 <= len(digits) <= 12:
        return digits
    if 10 <= len(digits) <= 13:
        return text.strip()
    return None


def _clean_email(value: str) -> Optional[str]:
    candidate = value.strip().replace("mailto:", "", 1).split("?")[0].lower()
    return candidate if EMAIL_RE.fullmatch(candidate) else None


def _first(items: Iterable[Optional[str]]) -> Optional[str]:
    for item in items:
        if item:
            return item
    return None


def _same_site(base: str, candidate: str) -> bool:
    return (urlparse(base).hostname or "").removeprefix("www.") == (urlparse(candidate).hostname or "").removeprefix("www.")


def _allowed_by_robots(base_url: str, target_url: str) -> bool:
    """Respect robots.txt without allowing an unbounded stdlib network call."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = httpx.get(
            robots_url,
            headers={"User-Agent": settings.public_data_user_agent},
            timeout=2.5,
            follow_redirects=True,
        )
        if response.status_code >= 400:
            return True
        parser.parse(response.text.splitlines())
        return parser.can_fetch(settings.public_data_user_agent, target_url)
    except httpx.HTTPError:
        # If robots.txt is unavailable, keep the crawl minimal and public-only.
        return True


def _json_ld_contacts(soup: BeautifulSoup) -> Dict[str, Any]:
    phones: List[str] = []
    emails: List[str] = []
    same_as: List[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            telephone = value.get("telephone")
            email = value.get("email")
            links = value.get("sameAs")
            if isinstance(telephone, str):
                phones.append(telephone)
            elif isinstance(telephone, list):
                phones.extend(str(item) for item in telephone)
            if isinstance(email, str):
                emails.append(email)
            if isinstance(links, str):
                same_as.append(links)
            elif isinstance(links, list):
                same_as.extend(str(item) for item in links)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            walk(json.loads(script.string or script.get_text() or "{}"))
        except (ValueError, TypeError):
            continue
    return {"phones": phones, "emails": emails, "same_as": same_as}


def _extract_page(response: httpx.Response, base_url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(response.text[:1_500_000], "html.parser")
    links = [urljoin(str(response.url), node.get("href")) for node in soup.find_all("a", href=True)]
    tel_links = [_clean_phone(link) for link in links if link.lower().startswith("tel:")]
    mail_links = [_clean_email(link) for link in links if link.lower().startswith("mailto:")]
    text = soup.get_text(" ", strip=True)
    text_phones = [_clean_phone(match.group(0)) for match in PHONE_RE.finditer(text)]
    text_emails = [_clean_email(match.group(0)) for match in EMAIL_RE.finditer(text)]
    structured = _json_ld_contacts(soup)

    social_links = list(structured["same_as"]) + links
    facebook = next((link for link in social_links if "facebook.com/" in link.lower() and "sharer" not in link.lower()), None)
    instagram = next((link for link in social_links if "instagram.com/" in link.lower()), None)
    linkedin = next((link for link in social_links if "linkedin.com/" in link.lower() and "/share" not in link.lower()), None)

    contact_pages: List[str] = []
    for link in links:
        lowered = link.lower()
        if _same_site(base_url, link) and any(word in lowered for word in CONTACT_PATH_WORDS):
            contact_pages.append(link.split("#")[0])

    return {
        "phone": _first([*tel_links, *(_clean_phone(value) for value in structured["phones"]), *text_phones]),
        "email": _first([*mail_links, *(_clean_email(value) for value in structured["emails"]), *text_emails]),
        "facebook": facebook,
        "instagram": instagram,
        "linkedin": linkedin,
        "contact_pages": list(dict.fromkeys(contact_pages))[:2],
    }


def discover_website_contacts(item: Dict[str, Any]) -> Dict[str, Any]:
    enriched = deepcopy(item)
    website = enriched.get("website")
    if not website:
        return enriched
    if enriched.get("phone") and enriched.get("email") and enriched.get("facebook") and enriched.get("instagram"):
        return enriched

    try:
        safe_url = _normalise_site(str(website))
    except ValueError:
        return enriched

    headers = {"User-Agent": settings.public_data_user_agent, "Accept": "text/html,application/xhtml+xml"}
    timeout = httpx.Timeout(connect=5.0, read=settings.website_contact_timeout_seconds, write=5.0, pool=5.0)
    found: Dict[str, Optional[str]] = {"phone": None, "email": None, "facebook": None, "instagram": None, "linkedin": None}
    pages_checked: List[str] = []
    try:
        with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
            response = client.get(safe_url)
            response.raise_for_status()
            pages_checked.append(str(response.url))
            page_data = _extract_page(response, str(response.url))
            for field in found:
                found[field] = page_data.get(field)
            for contact_url in page_data.get("contact_pages", []):
                if all(found.values()) or len(pages_checked) >= 3:
                    break
                if not _allowed_by_robots(str(response.url), contact_url):
                    continue
                try:
                    contact_response = client.get(contact_url)
                    if contact_response.status_code >= 400 or "text/html" not in contact_response.headers.get("content-type", ""):
                        continue
                    pages_checked.append(str(contact_response.url))
                    extra = _extract_page(contact_response, str(response.url))
                    for field in found:
                        found[field] = found[field] or extra.get(field)
                except httpx.HTTPError:
                    continue
    except (httpx.HTTPError, ValueError):
        return enriched

    changed = False
    for field, value in found.items():
        if value and not enriched.get(field):
            enriched[field] = value
            changed = True
    if changed:
        sources = list(dict.fromkeys([*(enriched.get("contact_sources") or []), "Official website"]))
        enriched["contact_sources"] = sources
        enriched["contact_confidence"] = "High"
        enriched["contact_status"] = "Contactable" if enriched.get("phone") or enriched.get("email") else "Website available"
        enriched["contact_discovery"] = {
            "website_pages_checked": pages_checked,
            "method": "Public business website",
        }
    return enriched


def _merge_google(item: Dict[str, Any], google: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(item)
    for field in [
        "phone",
        "website",
        "google_business_url",
        "google_place_id",
        "address",
        "latitude",
        "longitude",
        "rating",
    ]:
        if not merged.get(field) and google.get(field) is not None:
            merged[field] = google.get(field)
    merged["reviews_count"] = max(int(merged.get("reviews_count") or 0), int(google.get("reviews_count") or 0))
    merged["contact_sources"] = list(dict.fromkeys([*(merged.get("contact_sources") or []), "Google Places"]))
    merged["contact_confidence"] = "High" if merged.get("phone") else merged.get("contact_confidence") or "Medium"
    merged["contact_status"] = "Contactable" if merged.get("phone") or merged.get("email") else "Website available" if merged.get("website") else "Research needed"
    merged["contact_search_url"] = merged.get("google_business_url") or google_maps_search_url(merged)
    return merged


def finalise_contact_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    item = deepcopy(item)
    item["contact_search_url"] = item.get("contact_search_url") or item.get("google_business_url") or google_maps_search_url(item)
    sources = list(dict.fromkeys(item.get("contact_sources") or []))
    if (item.get("phone") or item.get("email") or item.get("website")) and not sources:
        sources.append(item.get("source") or "Public listing")
    item["contact_sources"] = sources
    if item.get("phone") or item.get("email"):
        item["contact_status"] = "Contactable"
        item["contact_confidence"] = item.get("contact_confidence") or "Medium"
    elif item.get("website"):
        item["contact_status"] = "Website available"
        item["contact_confidence"] = item.get("contact_confidence") or "Medium"
    else:
        item["contact_status"] = "Research needed"
        item["contact_confidence"] = item.get("contact_confidence") or "Low"
    return item


def enrich_search_items(items: List[dict], provider: str) -> tuple[List[dict], List[str]]:
    results = [finalise_contact_metadata(item) for item in items]
    warnings: List[str] = []

    if settings.enable_website_contact_enrichment:
        indexes = [index for index, item in enumerate(results) if item.get("website") and not (item.get("phone") and item.get("email"))]
        indexes = indexes[: max(0, settings.website_contact_enrichment_limit)]
        if indexes:
            with ThreadPoolExecutor(max_workers=min(4, len(indexes))) as executor:
                futures = {executor.submit(discover_website_contacts, results[index]): index for index in indexes}
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        results[index] = finalise_contact_metadata(future.result())
                    except Exception:
                        continue

    # Google is never scraped. When configured, use the official Places API only.
    if settings.google_places_api_key and provider != "google":
        lookups = 0
        for index, item in enumerate(results):
            if lookups >= max(0, settings.google_contact_enrichment_limit):
                break
            if item.get("phone"):
                continue
            lookups += 1
            try:
                google = google_exact_lookup(
                    item.get("business_name", ""),
                    item.get("city", ""),
                    item.get("province", ""),
                    item.get("address"),
                )
            except Exception:
                google = None
            if google:
                results[index] = _merge_google(item, google)
        if lookups:
            warnings.append("Missing contacts were checked against the official Google Places API where an accurate match was found.")
    elif any(not item.get("phone") for item in results):
        warnings.append("Some businesses do not publish a phone number in the connected sources. Use the Google Maps button to review the listing, or configure Google Places API for automated contact enrichment.")

    return [finalise_contact_metadata(item) for item in results], warnings


def enrich_single_lead(item: Dict[str, Any]) -> tuple[Dict[str, Any], List[str]]:
    enriched = finalise_contact_metadata(item)
    notes: List[str] = []
    if settings.enable_website_contact_enrichment and enriched.get("website"):
        before = (enriched.get("phone"), enriched.get("email"), enriched.get("facebook"), enriched.get("instagram"), enriched.get("linkedin"))
        enriched = finalise_contact_metadata(discover_website_contacts(enriched))
        after = (enriched.get("phone"), enriched.get("email"), enriched.get("facebook"), enriched.get("instagram"), enriched.get("linkedin"))
        if after != before:
            notes.append("New public contact details were found on the business website.")
    if settings.google_places_api_key and not enriched.get("phone"):
        try:
            google = google_exact_lookup(
                enriched.get("business_name", ""),
                enriched.get("city", ""),
                enriched.get("province", ""),
                enriched.get("address"),
            )
        except Exception:
            google = None
        if google:
            enriched = _merge_google(enriched, google)
            notes.append("The official Google Places API matched and enriched this business.")
    if not enriched.get("phone") and not enriched.get("email"):
        notes.append("No verified direct contact was published by the connected sources. Use the Google Maps review link and verify before outreach.")
    return finalise_contact_metadata(enriched), notes
