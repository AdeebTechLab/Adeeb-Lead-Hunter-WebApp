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


def _login(client: TestClient, email="admin@example.com", password="Admin@123") -> dict:
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _signup(client: TestClient, suffix="sales", cnic="35202-1234567-1", city="Lahore"):
    response = client.post(
        "/api/auth/signup",
        data={
            "name": f"{suffix.title()} User",
            "email": f"{suffix}@example.com",
            "password": "Sales1234",
            "cnic": cnic,
            "city": city,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_auth_dashboard_and_two_role_model():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        headers = _login(client)
        dashboard = client.get("/api/dashboard", headers=headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["stats"]["total_leads"] == 0
        assert dashboard.json()["stats"]["scope"] == "workspace"
        users = client.get("/api/users", headers=headers).json()["items"]
        assert {item["role"] for item in users} == {"admin"}


def test_public_signup_is_user_and_admin_is_notified_with_plain_cnic():
    with TestClient(app) as client:
        result = _signup(client)
        user = result["user"]
        assert user["role"] == "user"
        assert user["cnic"] == "35202-1234567-1"
        assert user["city"] == "Lahore"

        admin_headers = _login(client)
        notifications = client.get("/api/notifications", headers=admin_headers).json()["items"]
        assert any(item["title"] == "New user account" and "Sales User" in item["message"] for item in notifications)
        assert client.post("/api/users", headers=admin_headers).status_code == 405


def test_admin_team_controls_edit_reset_suspend_activate_and_delete():
    with TestClient(app) as client:
        created = _signup(client, suffix="team", cnic="35202-7654321-0", city="Multan")["user"]
        admin_headers = _login(client)

        detail = client.get(f"/api/users/{created['id']}", headers=admin_headers)
        assert detail.status_code == 200
        assert detail.json()["role"] == "user"

        updated = client.patch(
            f"/api/users/{created['id']}",
            headers=admin_headers,
            data={"name": "Updated User", "email": "updated@example.com", "cnic": "35202-7654321-0", "city": "Karachi", "role": "admin"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "Updated User"
        assert updated.json()["role"] == "user"  # role is immutable

        reset = client.post(
            f"/api/users/{created['id']}/reset-password",
            headers=admin_headers,
            json={"temporary_password": "Temp12345"},
        )
        assert reset.status_code == 200
        temp_login = client.post("/api/auth/login", json={"email": "updated@example.com", "password": "Temp12345"})
        assert temp_login.status_code == 200
        assert temp_login.json()["user"]["must_change_password"] is True
        user_headers = {"Authorization": f"Bearer {temp_login.json()['access_token']}"}
        changed = client.post(
            "/api/auth/change-password",
            headers=user_headers,
            json={"current_password": "Temp12345", "new_password": "Private12345"},
        )
        assert changed.status_code == 200

        suspended = client.post(f"/api/users/{created['id']}/suspend", headers=admin_headers)
        assert suspended.status_code == 200
        assert client.post("/api/auth/login", json={"email": "updated@example.com", "password": "Private12345"}).status_code == 401
        assert client.post(f"/api/users/{created['id']}/activate", headers=admin_headers).status_code == 200
        assert client.post("/api/auth/login", json={"email": "updated@example.com", "password": "Private12345"}).status_code == 200

        deleted = client.delete(f"/api/users/{created['id']}", headers=admin_headers)
        assert deleted.status_code == 200
        assert client.get(f"/api/users/{created['id']}", headers=admin_headers).status_code == 404


def test_admin_account_is_protected_from_role_status_and_deletion_actions():
    with TestClient(app) as client:
        headers = _login(client)
        admin = client.get("/api/users", headers=headers).json()["items"][0]
        assert admin["role"] == "admin"
        assert client.post(f"/api/users/{admin['id']}/suspend", headers=headers).status_code == 403
        assert client.delete(f"/api/users/{admin['id']}", headers=headers).status_code == 403
        assert client.post(f"/api/users/{admin['id']}/reset-password", headers=headers, json={"temporary_password": "Other12345"}).status_code == 403


def test_realtime_search_import_and_hide_already_qualified_leads():
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
        request = {"keyword": "Restaurant", "city": "Lahore", "province": "Punjab", "provider": "auto", "limit": 3}
        first = client.post("/api/leads/search", headers=headers, json=request)
        assert first.status_code == 200
        assert first.json()["count"] == 1
        imported = client.post("/api/leads/bulk", headers=headers, json={"leads": first.json()["items"]})
        assert imported.status_code == 200
        assert imported.json()["imported"] == 1

        second = client.post("/api/leads/search", headers=headers, json=request)
        assert second.status_code == 200
        assert second.json()["count"] == 0
        assert second.json()["excluded_existing"] == 1


def test_admin_sees_workspace_stats_user_sees_only_own_leads():
    with TestClient(app) as client:
        user_auth = _signup(client, suffix="owner", cnic="35202-3333333-3")["access_token"]
        user_headers = {"Authorization": f"Bearer {user_auth}"}
        admin_headers = _login(client)

        user_item = {**LIVE_ITEM, "business_name": "User Owned Lead", "phone": "+92 300 1111111"}
        admin_item = {**LIVE_ITEM, "business_name": "Admin Owned Lead", "phone": "+92 300 2222222"}
        assert client.post("/api/leads", headers=user_headers, json=user_item).status_code == 200
        assert client.post("/api/leads", headers=admin_headers, json=admin_item).status_code == 200

        user_dashboard = client.get("/api/dashboard", headers=user_headers).json()
        admin_dashboard = client.get("/api/dashboard", headers=admin_headers).json()
        assert user_dashboard["stats"]["total_leads"] == 1
        assert user_dashboard["stats"]["scope"] == "personal"
        assert admin_dashboard["stats"]["total_leads"] == 2
        assert client.get("/api/leads?page_size=100", headers=user_headers).json()["total"] == 1
        assert client.get("/api/leads?page_size=100", headers=admin_headers).json()["total"] == 2
        assert admin_dashboard["recent_leads"][0].get("created_by_name")


def test_pipeline_completed_cancelled_and_user_workflow_notifications():
    with TestClient(app) as client:
        user_auth = _signup(client, suffix="crm", cnic="35202-4444444-4")["access_token"]
        user_headers = {"Authorization": f"Bearer {user_auth}"}
        admin_headers = _login(client)

        lead = client.post("/api/leads", headers=user_headers, json={**LIVE_ITEM, "business_name": "CRM Lead", "phone": "+92 300 3333333"}).json()
        won = client.patch(f"/api/leads/{lead['id']}", headers=user_headers, json={"deal_status": "Won", "call_status": "Connected"})
        assert won.status_code == 200
        assert won.json()["status"] == "Completed"
        assert won.json()["deal_status"] == "Won"

        notifications = client.get("/api/notifications", headers=admin_headers).json()["items"]
        assert any(item["title"] == "Deal completed" and "CRM Lead" in item["message"] for item in notifications)
        dashboard = client.get("/api/dashboard", headers=user_headers).json()
        assert dashboard["stats"]["completed_deals"] == 1

        cancelled_lead = client.post("/api/leads", headers=user_headers, json={**LIVE_ITEM, "business_name": "Cancelled Lead", "phone": "+92 300 4444444"}).json()
        lost = client.patch(f"/api/leads/{cancelled_lead['id']}", headers=user_headers, json={"deal_status": "Lost"})
        assert lost.status_code == 200
        assert lost.json()["status"] == "Cancel"
        assert client.get("/api/dashboard", headers=user_headers).json()["stats"]["cancelled_deals"] == 1


def test_provider_status_saved_lists_and_contact_metadata():
    with TestClient(app) as client:
        headers = _login(client)
        providers = client.get("/api/leads/providers", headers=headers)
        assert providers.status_code == 200
        ids = {item["id"] for item in providers.json()["providers"]}
        assert ids == {"auto", "google", "geoapify", "osm"}

        created = client.post("/api/leads", headers=headers, json=LIVE_ITEM)
        assert created.status_code == 200
        saved = client.post("/api/lists", headers=headers, json={"name": "Hot Lahore", "description": "Local prospects"})
        assert saved.status_code == 200
        add = client.post(f"/api/lists/{saved.json()['id']}/leads", headers=headers, json={"lead_id": created.json()["id"]})
        assert add.status_code == 200
        assert add.json()["lead_count"] == 1


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


def test_user_contact_action_notifies_admin():
    with TestClient(app) as client:
        user_auth = _signup(client, suffix="contact", cnic="35202-5555555-5")["access_token"]
        user_headers = {"Authorization": f"Bearer {user_auth}"}
        admin_headers = _login(client)
        lead = client.post(
            "/api/leads",
            headers=user_headers,
            json={**LIVE_ITEM, "business_name": "Contact Action Lead", "phone": "+92 300 5555555"},
        ).json()
        updated = client.patch(
            f"/api/leads/{lead['id']}",
            headers=user_headers,
            json={"status": "Contacted", "call_status": "Connected"},
        )
        assert updated.status_code == 200
        notifications = client.get("/api/notifications", headers=admin_headers).json()["items"]
        assert any(item["title"] == "Lead contacted" and "Contact Action Lead" in item["message"] for item in notifications)


def test_legacy_duplicate_dedupe_migration_is_startup_safe():
    from datetime import datetime, timezone

    from app.core.database import mongo
    from app.services.seeding import _migrate_legacy_roles_and_pipeline

    with TestClient(app):
        now = datetime.now(timezone.utc)
        base = {
            "business_name": "Historical Duplicate",
            "category": "Restaurant",
            "city": "Lahore",
            "province": "Punjab",
            "phone": None,
            "website": None,
            "address": "Main Boulevard",
            "status": "Closed",
            "deal_status": "Open",
            "created_at": now,
            "updated_at": now,
        }
        mongo.db.leads.insert_one(dict(base))
        mongo.db.leads.insert_one(dict(base))
        _migrate_legacy_roles_and_pipeline()
        migrated = list(mongo.db.leads.find({"business_name": "Historical Duplicate"}))
        assert len(migrated) == 2
        assert sum(1 for item in migrated if item.get("dedupe_key")) == 1
        assert all(item.get("status") == "Cancel" for item in migrated)


def test_duplicate_aliases_hide_same_qualified_lead_when_provider_contact_fields_change():
    initial = {
        **LIVE_ITEM,
        "business_name": "Stable Identity Restaurant",
        "phone": "+92 300 7777777",
        "address": "12 Main Boulevard, Lahore",
    }
    changed_provider_record = {
        **initial,
        "phone": None,
        "source": "Geoapify",
        "source_url": "https://www.openstreetmap.org/way/2",
    }
    first_result = {
        "items": [initial],
        "provider": "osm",
        "cached": False,
        "attribution": "© OpenStreetMap contributors",
        "warnings": [],
        "endpoint": "provider-one",
    }
    second_result = {
        "items": [changed_provider_record],
        "provider": "geoapify",
        "cached": False,
        "attribution": "Geoapify",
        "warnings": [],
        "endpoint": "provider-two",
    }
    with TestClient(app) as client:
        headers = _login(client)
        request = {"keyword": "Restaurant", "city": "Lahore", "province": "Punjab", "provider": "auto", "limit": 3}
        with patch("app.api.leads.search_public_businesses", return_value=first_result):
            search = client.post("/api/leads/search", headers=headers, json=request).json()
            assert search["count"] == 1
            assert client.post("/api/leads/bulk", headers=headers, json={"leads": search["items"]}).json()["imported"] == 1
        with patch("app.api.leads.search_public_businesses", return_value=second_result):
            repeated = client.post("/api/leads/search", headers=headers, json=request)
            assert repeated.status_code == 200
            assert repeated.json()["count"] == 0
            assert repeated.json()["excluded_existing"] == 1


def test_tomtom_contact_enrichment_adds_verified_phone_without_replacing_discovery_source():
    from app.services.contact_enrichment import enrich_search_items

    item = {
        **LIVE_ITEM,
        "business_name": "Accurate Lahore Restaurant",
        "phone": None,
        "email": None,
        "website": None,
        "source": "OpenStreetMap",
        "contact_sources": [],
    }
    matched = {
        "tomtom_id": "tt-1",
        "matched_name": "Accurate Lahore Restaurant",
        "phone": "+92 42 12345678",
        "website": "https://accurate.example",
        "match_confidence": "High",
        "match_score": 0.97,
        "name_similarity": 1.0,
        "distance_m": 80,
        "city_match": True,
        "source": "TomTom Places Search API",
    }
    with patch("app.services.contact_enrichment.settings.tomtom_api_key", "configured"), \
         patch("app.services.contact_enrichment.settings.enable_website_contact_enrichment", False), \
         patch("app.services.contact_enrichment.tomtom_exact_lookup", return_value=matched):
        enriched, warnings = enrich_search_items([item], "osm")

    assert enriched[0]["source"] == "OpenStreetMap"
    assert enriched[0]["phone"] == "+92 42 12345678"
    assert enriched[0]["website"] == "https://accurate.example"
    assert "TomTom Places Search API" in enriched[0]["contact_sources"]
    assert enriched[0]["contact_confidence"] == "High"
    assert enriched[0]["contact_discovery"]["tomtom"]["distance_m"] == 80
    assert not any("add a free tomtom_api_key" in warning.lower() for warning in warnings)


def test_tomtom_strict_match_rejects_wrong_business_even_when_nearby():
    from app.providers.tomtom import _accepted_match, _candidate_score

    item = {
        "business_name": "Pak Tea House",
        "city": "Lahore",
        "latitude": 31.5204,
        "longitude": 74.3587,
    }
    good = {
        "type": "POI",
        "poi": {"name": "Pak Tea House", "phone": "+92 42 11111111"},
        "position": {"lat": 31.5205, "lon": 74.3588},
        "address": {"municipality": "Lahore", "freeformAddress": "Mall Road, Lahore"},
    }
    bad = {
        "type": "POI",
        "poi": {"name": "City Medical Centre", "phone": "+92 42 22222222"},
        "position": {"lat": 31.5205, "lon": 74.3588},
        "address": {"municipality": "Lahore", "freeformAddress": "Mall Road, Lahore"},
    }

    good_score = _candidate_score(item, good)
    bad_score = _candidate_score(item, bad)
    assert _accepted_match(*good_score)
    assert not _accepted_match(*bad_score)


def test_google_maps_verification_uses_specific_business_name_and_address():
    from app.services.contact_enrichment import finalise_contact_metadata

    item = finalise_contact_metadata({
        "business_name": "Waqas Biryani House",
        "address": "Beadon Road, Lahore",
        "city": "Lahore",
        "province": "Punjab",
        "latitude": 31.5204,
        "longitude": 74.3587,
        "phone": None,
        "email": None,
        "website": None,
    })
    assert "google.com/maps/search" in item["contact_search_url"]
    assert "Waqas+Biryani+House" in item["contact_search_url"]
    assert "Beadon+Road" in item["contact_search_url"]
    assert "openstreetmap.org" not in item["contact_search_url"]
    assert "31.5204000" not in item["contact_search_url"]


def test_tomtom_places_normalised_match_keeps_phone_and_website_fields():
    from app.providers.tomtom import _best_accepted

    item = {
        "business_name": "Pak Tea House",
        "city": "Lahore",
        "latitude": 31.5204,
        "longitude": 74.3587,
    }
    result = {
        "type": "POI",
        "id": "tt-123",
        "poi": {"name": "Pak Tea House", "phone": "+92 42 11111111", "url": "pakteahouse.example"},
        "position": {"lat": 31.5205, "lon": 74.3588},
        "address": {"municipality": "Lahore", "freeformAddress": "Mall Road, Lahore"},
    }
    matched = _best_accepted(item, [result])
    assert matched is not None
    assert matched["poi"]["phone"] == "+92 42 11111111"
    assert matched["poi"]["url"] == "pakteahouse.example"


def test_maps_verification_always_uses_google_maps_even_for_osm_leads():
    from app.services.contact_enrichment import finalise_contact_metadata

    item = finalise_contact_metadata({
        "business_name": "Mapped Hotel",
        "address": "Shahrah-e-Faisal, Karachi",
        "city": "Karachi",
        "province": "Sindh",
        "latitude": 24.8607,
        "longitude": 67.0011,
        "source_url": "https://www.openstreetmap.org/node/123456",
        "phone": None,
        "email": None,
        "website": None,
    })
    assert item["contact_search_url"].startswith("https://www.google.com/maps/search/?api=1&query=")
    assert "Mapped+Hotel" in item["contact_search_url"]
    assert "Shahrah-e-Faisal" in item["contact_search_url"]
    assert "openstreetmap.org" not in item["contact_search_url"]


def test_tomtom_places_search_api_request_contract_and_details_fallback():
    from app.providers.tomtom import _candidate_with_contacts

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self):
            self.calls = []

        def post(self, endpoint, json=None, headers=None):
            self.calls.append(("POST", endpoint, json or {}, headers or {}))
            return FakeResponse({
                "results": [{
                    "type": "poi",
                    "id": "tt-places-123",
                    "title": "Contract Test Restaurant",
                    "position": {"type": "Point", "coordinates": [74.3588, 31.5205]},
                    "subtitles": ["Mall Road", "Lahore", "Pakistan"],
                    "address": {"municipality": "Lahore", "street": "Mall Road", "countryCodeIso2": "PK"},
                    "contacts": [],
                }]
            })

        def get(self, endpoint, params=None, headers=None):
            self.calls.append(("GET", endpoint, params or {}, headers or {}))
            return FakeResponse({
                "type": "poi",
                "id": "tt-places-123",
                "title": "Contract Test Restaurant",
                "position": {"type": "Point", "coordinates": [74.3588, 31.5205]},
                "subtitles": ["Mall Road", "Lahore", "Pakistan"],
                "address": {"municipality": "Lahore", "street": "Mall Road", "countryCodeIso2": "PK"},
                "contacts": [{
                    "type": "default",
                    "phones": ["+92 42 12345678"],
                    "websites": ["https://contract.example"],
                }],
            })

    client = FakeClient()
    item = {
        "business_name": "Contract Test Restaurant",
        "city": "Lahore",
        "province": "Punjab",
        "latitude": 31.5204,
        "longitude": 74.3587,
    }
    with patch("app.providers.tomtom.settings.tomtom_api_key", "places-key"):
        matched = _candidate_with_contacts(client, item)

    assert matched is not None
    assert matched["poi"]["phone"] == "+92 42 12345678"
    assert matched["poi"]["url"] == "https://contract.example"

    method, endpoint, body, headers = client.calls[0]
    assert method == "POST"
    assert endpoint.endswith("/maps/orbis/places/discover")
    assert body["filters"]["types"] == ["poi"]
    assert body["filters"]["countryCodesIso2"] == ["PK"]
    assert body["origin"]["coordinates"] == [74.3587, 31.5204]
    assert headers["TomTom-Api-Version"] == "3"
    assert headers["TomTom-Api-Key"] == "places-key"
    assert "contacts" in headers["Attributes"]

    method, endpoint, params, headers = client.calls[1]
    assert method == "GET"
    assert endpoint.endswith("/maps/orbis/places/details/pois/tt-places-123")
    assert params["origin"] == "74.3587,31.5204"
    assert headers["TomTom-Api-Version"] == "3"
    assert "contacts" in headers["Attributes"]


def test_tomtom_places_discover_contacts_avoid_details_call():
    from app.providers.tomtom import _candidate_with_contacts

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [{
                    "type": "poi",
                    "id": "tt-direct",
                    "title": "Pak Tea House",
                    "position": {"type": "Point", "coordinates": [74.3588, 31.5205]},
                    "subtitles": ["Mall Road", "Lahore", "Pakistan"],
                    "address": {"municipality": "Lahore", "countryCodeIso2": "PK"},
                    "contacts": [{"type": "default", "phones": ["+92 42 11111111"]}],
                }]
            }

    class FakeClient:
        def __init__(self):
            self.post_calls = 0
            self.get_calls = 0

        def post(self, endpoint, json=None, headers=None):
            self.post_calls += 1
            return FakeResponse()

        def get(self, endpoint, params=None, headers=None):
            self.get_calls += 1
            raise AssertionError("Details should not be called when Discover already has contact data")

    client = FakeClient()
    item = {
        "business_name": "Pak Tea House",
        "city": "Lahore",
        "latitude": 31.5204,
        "longitude": 74.3587,
    }
    with patch("app.providers.tomtom.settings.tomtom_api_key", "places-key"):
        matched = _candidate_with_contacts(client, item)

    assert matched is not None
    assert matched["poi"]["phone"] == "+92 42 11111111"
    assert client.post_calls == 1
    assert client.get_calls == 0



def test_repeated_search_advances_to_later_pages_after_qualified_leads():
    existing_one = {**LIVE_ITEM, "business_name": "Existing One", "phone": "+92 300 9000001", "address": "One Road, Lahore"}
    existing_two = {**LIVE_ITEM, "business_name": "Existing Two", "phone": "+92 300 9000002", "address": "Two Road, Lahore"}
    fresh_one = {**LIVE_ITEM, "business_name": "Fresh One", "phone": "+92 300 9000003", "address": "Three Road, Lahore"}
    fresh_two = {**LIVE_ITEM, "business_name": "Fresh Two", "phone": "+92 300 9000004", "address": "Four Road, Lahore"}

    offsets = []

    def fake_page(provider, keyword, city, province, limit, offset=0, enrich=True):
        offsets.append(offset)
        if offset == 0:
            items = [existing_one, existing_two]
        elif offset == 30:
            items = [fresh_one, fresh_two]
        else:
            items = []
        return {
            "items": items,
            "provider": "geoapify",
            "cached": False,
            "attribution": "Geoapify",
            "warnings": [],
            "endpoint": "Geoapify Places API",
        }

    with TestClient(app) as client:
        headers = _login(client)
        assert client.post("/api/leads", headers=headers, json=existing_one).status_code == 200
        assert client.post("/api/leads", headers=headers, json=existing_two).status_code == 200
        with patch("app.api.leads.search_public_businesses", side_effect=fake_page):
            response = client.post(
                "/api/leads/search",
                headers=headers,
                json={"keyword": "Restaurant", "city": "Lahore", "province": "Punjab", "provider": "auto", "limit": 2},
            )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["business_name"] for item in payload["items"]] == ["Fresh One", "Fresh Two"]
    assert payload["excluded_existing"] == 2
    assert offsets[:2] == [0, 30]


def test_geoapify_search_uses_native_limit_and_offset_paging():
    from app.providers.geoapify import geoapify_search

    seen_params = {}

    def fake_places(client, url, params):
        seen_params.update(params)
        return {"features": []}

    with patch("app.providers.geoapify.settings.geoapify_api_key", "configured"), \
         patch("app.providers.geoapify.geocode_city", return_value={"place_id": "city-1", "lat": 31.52, "lon": 74.35}), \
         patch("app.providers.geoapify._request_json", side_effect=fake_places):
        result = geoapify_search("Restaurant", "Lahore", "Punjab", 20, offset=40)

    assert result.items == []
    assert seen_params["limit"] == 20
    assert seen_params["offset"] == 40


def test_provider_cache_separates_paging_offsets():
    from app.providers import search_public_businesses
    from app.providers.common import ProviderSearchResult

    result = ProviderSearchResult(
        items=[LIVE_ITEM],
        provider="osm",
        attribution="© OpenStreetMap contributors",
        endpoint="paged-overpass",
    )
    with patch("app.providers.osm_search", return_value=result) as mocked:
        search_public_businesses("osm", "Restaurant", "Paging Cache City", "Punjab", 1, offset=0, enrich=False)
        search_public_businesses("osm", "Restaurant", "Paging Cache City", "Punjab", 1, offset=1, enrich=False)
        search_public_businesses("osm", "Restaurant", "Paging Cache City", "Punjab", 1, offset=0, enrich=False)
    assert mocked.call_count == 2


def test_city_resolution_corrects_small_typo_without_network():
    from app.services.city_resolution import resolve_city

    result = resolve_city("Lahroe", "Punjab")
    assert result["city"] == "Lahore"
    assert result["corrected"] is True


def test_tomtom_branch_label_matches_same_nearby_business():
    from app.providers.tomtom import _best_accepted

    item = {
        "business_name": "Pak Tea House Actual Location",
        "city": "Lahore",
        "latitude": 31.5204,
        "longitude": 74.3587,
    }
    result = {
        "type": "POI",
        "id": "pak-tea",
        "poi": {"name": "Pak Tea House", "phone": "+92 42 38089841", "url": None},
        "position": {"lat": 31.52045, "lon": 74.35875},
        "address": {"municipality": "Lahore", "freeformAddress": "Lahore, Pakistan"},
    }
    matched = _best_accepted(item, [result])
    assert matched is not None
    assert matched["poi"]["phone"] == "+92 42 38089841"


def test_tomtom_details_called_when_discover_has_website_but_no_phone():
    from app.providers.tomtom import _candidate_with_contacts

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self):
            self.get_calls = 0

        def post(self, endpoint, json=None, headers=None):
            return FakeResponse({
                "results": [{
                    "type": "poi",
                    "id": "same-poi",
                    "title": "Same Business",
                    "position": {"type": "Point", "coordinates": [74.3588, 31.5205]},
                    "address": {"municipality": "Lahore"},
                    "contacts": [{"type": "default", "websites": ["https://same.example"]}],
                }]
            })

        def get(self, endpoint, params=None, headers=None):
            self.get_calls += 1
            return FakeResponse({
                "type": "poi",
                "id": "same-poi",
                "title": "Same Business",
                "position": {"type": "Point", "coordinates": [74.3588, 31.5205]},
                "address": {"municipality": "Lahore"},
                "contacts": [{"type": "default", "phones": ["+92 300 1234567"], "websites": ["https://same.example"]}],
            })

    client = FakeClient()
    item = {"business_name": "Same Business", "city": "Lahore", "latitude": 31.5204, "longitude": 74.3587}
    with patch("app.providers.tomtom.settings.tomtom_api_key", "places-key"):
        matched = _candidate_with_contacts(client, item)
    assert matched is not None
    assert matched["poi"]["phone"] == "+92 300 1234567"
    assert client.get_calls == 1


def test_tomtom_placeholder_timeout_value_falls_back_to_numeric_default():
    from app.core.config import Settings

    configured = Settings(_env_file=None, tomtom_contact_timeout_seconds="TOMTOM_CONTACT_TIMEOUT_SECONDS")
    assert configured.tomtom_contact_timeout_seconds == 8.0


def test_google_maps_metadata_overrides_legacy_osm_contact_link():
    from app.services.contact_enrichment import finalise_contact_metadata

    item = finalise_contact_metadata({
        "business_name": "Waqas Biryani",
        "address": "Kacha Hall Road, Lahore",
        "city": "Lahore",
        "province": "Punjab",
        "latitude": 31.5643017,
        "longitude": 74.3207201,
        "source_url": "https://www.openstreetmap.org/node/5793097159",
        "contact_search_url": "https://www.openstreetmap.org/node/5793097159",
        "google_business_url": None,
    })
    assert item["contact_search_url"].startswith("https://www.google.com/maps/search/?api=1&query=")
    assert "openstreetmap.org" not in item["contact_search_url"]
    assert "Waqas+Biryani" in item["contact_search_url"]


def test_cold_call_is_roman_urdu_while_other_outreach_stays_english():
    from app.services.scoring import build_outreach

    outreach = build_outreach(
        {**LIVE_ITEM, "business_name": "Roman Script Restaurant", "phone": "+92 300 9999999"},
        "Website Development",
        ["Website missing", "WhatsApp conversion path missing"],
    )
    cold = outreach["cold_call"]
    assert "CALL SE PEHLE" in cold
    assert "website maujood nahin hai" in cold
    assert "kya meri baat" in cold
    assert "Aap ke zyada tar naye customers" in cold
    assert "Would a 15-minute review" in outreach["email"]
    assert "Primary objective:" in outreach["call_plan"]


def test_qualified_lead_can_be_deleted_and_can_reappear_in_search():
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
        request = {"keyword": "Restaurant", "city": "Lahore", "province": "Punjab", "provider": "auto", "limit": 3}
        first = client.post("/api/leads/search", headers=headers, json=request).json()
        imported = client.post("/api/leads/bulk", headers=headers, json={"leads": first["items"]}).json()
        lead_id = imported["items"][0]["id"]

        deleted = client.delete(f"/api/leads/{lead_id}", headers=headers)
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["ok"] is True
        assert client.get(f"/api/leads/{lead_id}", headers=headers).status_code == 404

        repeated = client.post("/api/leads/search", headers=headers, json=request)
        assert repeated.status_code == 200
        assert repeated.json()["count"] == 1


def test_delete_lead_removes_saved_list_reference():
    with TestClient(app) as client:
        headers = _login(client)
        lead = client.post(
            "/api/leads",
            headers=headers,
            json={**LIVE_ITEM, "business_name": "Delete From List Lead", "phone": "+92 300 1212121"},
        ).json()
        saved = client.post(
            "/api/lists",
            headers=headers,
            json={"name": "Deletion Test", "description": ""},
        ).json()
        added = client.post(
            f"/api/lists/{saved['id']}/leads",
            headers=headers,
            json={"lead_id": lead["id"]},
        )
        assert added.status_code == 200
        assert added.json()["lead_count"] == 1

        deleted = client.delete(f"/api/leads/{lead['id']}", headers=headers)
        assert deleted.status_code == 200
        refreshed = client.get("/api/lists", headers=headers).json()["items"]
        target = next(item for item in refreshed if item["id"] == saved["id"])
        assert target["lead_count"] == 0
        assert target["leads"] == []


def test_tomtom_places_contact_parser_is_forward_compatible():
    from app.providers.tomtom import _first_contact

    phone, website = _first_contact({
        "contacts": [
            {
                "type": "default",
                "phones": [{"value": "+92 42 35700000"}],
                "websites": [{"url": "https://example.pk"}],
            }
        ]
    })
    assert phone == "+92 42 35700000"
    assert website == "https://example.pk"


def test_tomtom_nearby_branch_name_can_match_when_address_agrees():
    from app.providers.tomtom import _best_accepted, _normalise_places_result

    item = {
        "business_name": "Sea Hawk Family Restaurant",
        "city": "Lahore",
        "address": "Sheikh Abdul Qadir Jillani Road, Sant Nagar, Lahore",
        "latitude": 31.56430,
        "longitude": 74.32072,
    }
    raw = {
        "id": "branch-1",
        "type": "poi",
        "title": "Sea Hawk Restaurant",
        "position": {"type": "Point", "coordinates": [74.32075, 31.56432]},
        "subtitles": ["Sheikh Abdul Qadir Jillani Road", "Lahore", "Pakistan"],
        "address": {"municipality": "Lahore", "street": "Sheikh Abdul Qadir Jillani Road"},
        "contacts": [{"phones": ["+92 42 30000000"]}],
    }
    match = _best_accepted(item, [_normalise_places_result(raw)])
    assert match is not None
    assert match["poi"]["phone"] == "+92 42 30000000"
    assert match["_match"]["distance"] < 10


def test_geoapify_place_details_extracts_richer_contact_fields():
    import app.providers.geoapify as geo

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "features": [{
                    "properties": {
                        "feature_type": "details",
                        "contact": {
                            "phone": "+92 42 11111111",
                            "phone_other": ["+92 300 2222222"],
                            "email": "hello@example.pk",
                        },
                        "website": "https://example.pk",
                    }
                }]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            assert kwargs["params"]["id"] == "geo-place-unique-test"
            assert kwargs["params"]["features"] == "details"
            return FakeResponse()

    with patch.object(geo.settings, "geoapify_api_key", "geo-key"), patch.object(geo.httpx, "Client", FakeClient):
        result = geo.geoapify_contact_lookup({"provider_place_id": "geo-place-unique-test"})
    assert result["phone"] == "+92 42 11111111"
    assert result["email"] == "hello@example.pk"
    assert result["website"] == "https://example.pk"
    assert result["source"] == "Geoapify Place Details"
