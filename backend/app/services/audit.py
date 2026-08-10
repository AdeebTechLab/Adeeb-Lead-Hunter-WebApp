from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


class UnsafeURL(ValueError):
    pass


def _public_url(url: str) -> str:
    candidate = url.strip()
    if not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURL("Invalid website URL")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise UnsafeURL("Private network URLs are not allowed")
    except socket.gaierror as exc:
        raise UnsafeURL("Website host could not be resolved") from exc
    return candidate


def audit_website(url: str) -> dict:
    safe_url = _public_url(url)
    started = time.perf_counter()
    headers = {"User-Agent": "AILeadHunterAudit/1.0"}
    with httpx.Client(follow_redirects=True, timeout=10.0, headers=headers) as client:
        response = client.get(safe_url)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        final_url = str(response.url)
        soup = BeautifulSoup(response.text[:2_000_000], "html.parser")

        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        description_tag = soup.find("meta", attrs={"name": lambda value: value and value.lower() == "description"})
        description = description_tag.get("content", "").strip() if description_tag else ""
        viewport = soup.find("meta", attrs={"name": lambda value: value and value.lower() == "viewport"})
        h1 = soup.find("h1")
        canonical = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
        images = soup.find_all("img")
        alt_ratio = 1 if not images else sum(bool(img.get("alt")) for img in images) / len(images)
        forms = soup.find_all("form")
        links = [item.get("href") for item in soup.find_all("a", href=True)]
        text = soup.get_text(" ", strip=True).lower()

        seo_points = 0
        seo_points += 25 if 10 <= len(title) <= 65 else 10 if title else 0
        seo_points += 25 if 50 <= len(description) <= 170 else 10 if description else 0
        seo_points += 15 if h1 else 0
        seo_points += 10 if canonical else 0
        seo_points += 15 if alt_ratio >= 0.7 else 7 if alt_ratio >= 0.3 else 0
        seo_points += 10 if viewport else 0

        whatsapp = any("wa.me" in (link or "") or "api.whatsapp.com" in (link or "") for link in links)
        booking = any(term in text for term in ["book now", "appointment", "reserve", "reservation", "schedule now"])
        contact_form = bool(forms) and any(
            term in (form.get_text(" ", strip=True) + str(form)).lower()
            for form in forms
            for term in ["contact", "message", "email", "phone"]
        )

        broken_links = 0
        checked = 0
        host = urlparse(final_url).netloc
        seen = set()
        for link in links:
            if checked >= 8:
                break
            absolute = urljoin(final_url, link)
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"} or parsed.netloc != host or absolute in seen:
                continue
            seen.add(absolute)
            checked += 1
            try:
                result = client.head(absolute, timeout=4.0)
                if result.status_code >= 400:
                    broken_links += 1
            except httpx.HTTPError:
                broken_links += 1

    return {
        "website_available": True,
        "final_url": final_url,
        "http_status": response.status_code,
        "ssl_enabled": final_url.startswith("https://"),
        "mobile_friendly": bool(viewport),
        "response_time_ms": elapsed_ms,
        "speed_label": "Fast" if elapsed_ms < 900 else "Average" if elapsed_ms < 2200 else "Slow",
        "seo_score": min(100, seo_points),
        "contact_form": contact_form,
        "whatsapp_button": whatsapp,
        "booking_system": booking,
        "broken_links": broken_links,
        "links_checked": checked,
        "website_age": None,
        "website_age_note": "Not available without a reliable registration-data provider",
        "checked_at": int(time.time()),
    }
