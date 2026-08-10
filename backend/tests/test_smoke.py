import os
from unittest.mock import patch

os.environ["ENVIRONMENT"] = "test"
os.environ["DEFAULT_ADMIN_EMAIL"] = "admin@example.com"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "Admin@123"
os.environ["DEFAULT_ADMIN_CNIC"] = "00000-0000000-0"
os.environ["DEFAULT_ADMIN_CITY"] = "Islamabad"

from fastapi.testclient import TestClient

from app.main import app


LIVE_ITEM = {
    "business_name": "Live Lahore Restaurant",
    "category": "Restaurant",
    "city": "Lahore",
    "province": "Punjab",
    "phone": "+92 300 0000000",
    "email": None,
    "website": None,
    "google_business_url": None,
    "facebook": "https://facebook.com/example",
    "instagram": None,
    "linkedin": None,
    "address": "Gulberg, Lahore",
    "latitude": 31.5204,
    "longitude": 74.3587,
    "source": "OpenStreetMap",
    "source_url": "https://www.openstreetmap.org/node/1",
    "reviews_count": 0,
    "rating": None,
    "tags": ["Restaurant", "Lahore", "Public API"],
}


def _login(client: TestClient) -> dict:
    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "Admin@123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_auth_dashboard_and_leads():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        headers = _login(client)
        dashboard = client.get("/api/dashboard", headers=headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["stats"]["total_leads"] == 0
        leads = client.get("/api/leads", headers=headers)
        assert leads.status_code == 200
        assert leads.json()["total"] == 0


def test_public_signup_requires_cnic_and_city():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            data={
                "name": "Sales User",
                "email": "sales@example.com",
                "password": "Sales1234",
                "cnic": "35202-1234567-1",
                "city": "Lahore",
            },
        )
        assert response.status_code == 200
        user = response.json()["user"]
        assert user["role"] == "salesperson"
        assert user["cnic"] == "35202-1234567-1"
        assert user["city"] == "Lahore"


def test_admin_can_create_role_account_with_required_identity_fields():
    with TestClient(app) as client:
        headers = _login(client)
        response = client.post(
            "/api/users",
            headers=headers,
            data={
                "name": "Manager User",
                "email": "manager@example.com",
                "password": "Manager123",
                "cnic": "35202-7654321-0",
                "city": "Multan",
                "role": "manager",
            },
        )
        assert response.status_code == 200
        assert response.json()["role"] == "manager"
        assert response.json()["city"] == "Multan"


def test_realtime_search_and_bulk_import():
    provider_result = {
        "items": [LIVE_ITEM],
        "provider": "osm",
        "cached": False,
        "attribution": "© OpenStreetMap contributors",
        "warnings": [],
        "endpoint": "https://overpass.example/api/interpreter",
    }
    with TestClient(app) as client, patch("app.api.leads.search_public_businesses", return_value=provider_result):
        headers = _login(client)
        search = client.post(
            "/api/leads/search",
            headers=headers,
            json={"keyword": "Restaurant", "city": "Lahore", "province": "Punjab", "provider": "auto", "limit": 3},
        )
        assert search.status_code == 200
        payload = search.json()
        assert payload["provider"] == "osm"
        assert payload["cached"] is False
        assert payload["items"][0]["source"] == "OpenStreetMap"
        imported = client.post("/api/leads/bulk", headers=headers, json={"leads": payload["items"]})
        assert imported.status_code == 200
        assert imported.json()["imported"] >= 1


def test_provider_status_saved_lists_notifications_and_admin_users():
    with TestClient(app) as client:
        headers = _login(client)
        providers = client.get("/api/leads/providers", headers=headers)
        assert providers.status_code == 200
        ids = {item["id"] for item in providers.json()["providers"]}
        assert ids == {"auto", "google", "geoapify", "osm"}
        created = client.post("/api/leads", headers=headers, json=LIVE_ITEM)
        assert created.status_code == 200
        leads = client.get("/api/leads?page_size=1", headers=headers).json()["items"]
        saved = client.post("/api/lists", headers=headers, json={"name": "Hot Lahore", "description": "Local prospects"})
        assert saved.status_code == 200
        list_id = saved.json()["id"]
        add = client.post(f"/api/lists/{list_id}/leads", headers=headers, json={"lead_id": leads[0]["id"]})
        assert add.status_code == 200
        assert add.json()["lead_count"] == 1
        notifications = client.get("/api/notifications", headers=headers)
        assert notifications.status_code == 200
        users = client.get("/api/users", headers=headers)
        assert users.status_code == 200
        assert any(item["role"] == "admin" for item in users.json()["items"])


def test_auto_provider_falls_back_after_primary_error():
    from app.providers import search_public_businesses
    from app.providers.common import ProviderError, ProviderSearchResult

    osm_result = ProviderSearchResult(
        items=[LIVE_ITEM],
        provider="osm",
        attribution="© OpenStreetMap contributors",
        endpoint="secondary-overpass",
    )
    with patch("app.providers.settings.geoapify_api_key", "configured"), \
         patch("app.providers.geoapify_search", side_effect=ProviderError("temporary failure")), \
         patch("app.providers.osm_search", return_value=osm_result):
        result = search_public_businesses("auto", "Restaurant", "Fallback City", "Punjab", 1)
    assert result["provider"] == "osm"
    assert any("another configured source" in warning.lower() for warning in result["warnings"])


def test_provider_search_cache_avoids_duplicate_api_call():
    from app.providers import search_public_businesses
    from app.providers.common import ProviderSearchResult

    osm_result = ProviderSearchResult(
        items=[LIVE_ITEM],
        provider="osm",
        attribution="© OpenStreetMap contributors",
        endpoint="cached-overpass",
    )
    with patch("app.providers.osm_search", return_value=osm_result) as mocked:
        first = search_public_businesses("osm", "Restaurant", "Cache City", "Punjab", 1)
        second = search_public_businesses("osm", "Restaurant", "Cache City", "Punjab", 1)
    assert first["cached"] is False
    assert second["cached"] is True
    assert mocked.call_count == 1


def test_score_meanings_and_contact_metadata():
    from app.services.contact_enrichment import finalise_contact_metadata
    from app.services.scoring import score_profile

    assert score_profile(45)["label"] == "Cold / incomplete lead"
    assert score_profile(70)["label"] == "Strong warm lead"
    assert score_profile(92)["label"] == "Top-priority opportunity"

    item = finalise_contact_metadata({
        "business_name": "Public Business",
        "city": "Multan",
        "province": "Punjab",
        "source": "OpenStreetMap",
        "phone": None,
        "email": None,
        "website": None,
    })
    assert item["contact_status"] == "Research needed"
    assert item["contact_confidence"] == "Low"
    assert "google.com/maps/search" in item["contact_search_url"]


def test_provider_failure_returns_safe_message():
    from app.providers import search_public_businesses
    from app.providers.common import ProviderError

    with patch("app.providers.osm_search", side_effect=ProviderError("403 from https://upstream.example/private")):
        try:
            search_public_businesses("osm", "Hotels", "Safe Error City", "Punjab", 2)
        except ProviderError as exc:
            message = str(exc)
        else:
            raise AssertionError("Expected a provider error")
    assert "upstream.example" not in message
    assert "could not complete this live search" in message


def test_social_audit_is_explicitly_unverified_without_platform_api():
    from app.api.leads import _social_audit

    audit = _social_audit({"facebook": "https://facebook.com/public", "instagram": None, "linkedin": None})
    assert audit["activity_level"] == "Not verified"
    assert "official" in audit["activity_explanation"].lower()
    assert audit["recommended_action"]
