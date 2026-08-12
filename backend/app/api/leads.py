from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import BytesIO, StringIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.core.database import mongo
from app.core.db_compat import is_duplicate_key_error

ASCENDING, DESCENDING = 1, -1
from app.core.dependencies import get_current_user
from app.core.objectid import ObjectId
from app.core.serializers import serialize_doc
from app.models import BulkImportRequest, LeadCreateRequest, LeadUpdateRequest, SearchRequest
from app.providers import provider_status, search_public_businesses
from app.providers.common import ProviderError
from app.services.activity import create_admin_notification, create_notification, log_activity
from app.services.audit import UnsafeURL, audit_website
from app.services.contact_enrichment import enrich_single_lead, finalise_contact_metadata
from app.services.dedupe import make_dedupe_key, make_identity_keys
from app.services.scoring import (
    build_outreach,
    build_score_breakdown,
    build_summary,
    score_lead,
    score_profile,
)

router = APIRouter(prefix="/leads", tags=["Leads"])


def _scope_for_user(user: dict) -> dict:
    return {} if user.get("role") == "admin" else {"created_by": user["_id"]}


def _lead_or_404(lead_id: str, user: dict) -> dict:
    if not ObjectId.is_valid(lead_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    query = {"_id": ObjectId(lead_id), **_scope_for_user(user)}
    lead = mongo.db.leads.find_one(query)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def _lead_view(lead: dict) -> dict:
    result = serialize_doc(lead)
    if not result.get("created_by_name") and lead.get("created_by"):
        creator = mongo.db.users.find_one({"_id": lead.get("created_by")})
        result["created_by_name"] = creator.get("name") if creator else "Former user"
    return result


def _score_fields(data: dict, audit: dict | None = None) -> dict:
    score, priority, service, reasons = score_lead(data, audit)
    return {
        "lead_score": score,
        "priority": priority,
        "recommended_service": service,
        "score_reasons": reasons,
        "score_profile": score_profile(score),
        "score_breakdown": build_score_breakdown(data, score),
        "business_summary": build_summary(data, score, priority, service, reasons),
        "outreach": build_outreach(data, service, reasons),
    }


def _prepare_lead(data: dict, user: dict) -> dict:
    now = datetime.now(timezone.utc)
    data = finalise_contact_metadata(data)
    data.update(_score_fields(data, data.get("audit") or None))
    data.update(
        {
            "dedupe_key": make_dedupe_key(data),
            "dedupe_aliases": make_identity_keys(data),
            "audit": data.get("audit", {}),
            "status": data.get("status", "Not Contacted"),
            "notes": data.get("notes", ""),
            "follow_up_date": data.get("follow_up_date"),
            "last_contact_date": data.get("last_contact_date"),
            "assigned_salesperson": data.get("assigned_salesperson", ""),
            "call_status": data.get("call_status", "Pending"),
            "proposal_status": data.get("proposal_status", "Not sent"),
            "deal_status": data.get("deal_status", "Open"),
            "meeting_notes": data.get("meeting_notes", ""),
            "created_by": user["_id"],
            "created_by_name": user.get("name", "User"),
            "created_by_email": user.get("email", ""),
            "created_at": now,
            "updated_at": now,
        }
    )
    return data


def _social_audit(lead: dict) -> dict:
    profiles = {
        "facebook": bool(lead.get("facebook")),
        "instagram": bool(lead.get("instagram")),
        "linkedin": bool(lead.get("linkedin")),
    }
    count = sum(profiles.values())
    if count == 0:
        presence = "No public profiles found"
        presence_score = 0
        action = "Verify whether profiles exist. If none are active, pitch Social Media Marketing with a basic profile, content and enquiry plan."
    elif count == 1:
        presence = "Limited public presence"
        presence_score = 40
        action = "Review the available profile manually, confirm the last post date, and pitch a consistent multi-channel content plan if activity is weak."
    else:
        presence = "Multiple profiles found"
        presence_score = 75
        action = "Open each verified profile, record the last post date and engagement, then pitch content, paid campaigns or automation only where a gap is confirmed."

    return {
        "facebook_available": profiles["facebook"],
        "instagram_available": profiles["instagram"],
        "linkedin_available": profiles["linkedin"],
        "presence_level": presence,
        "presence_score": presence_score,
        "last_post_date": None,
        "activity_level": "Not verified",
        "activity_explanation": (
            "Posting recency and engagement are not guessed. Accurate activity requires the platform's official API, an authorized account connection, "
            "or a manual review of the public profile."
        ),
        "recommended_action": action,
        "verification_status": "Presence links verified where available; posting activity pending official API or manual review",
    }


@router.get("/providers")
def get_provider_status(user: dict = Depends(get_current_user)):
    return provider_status()


@router.post("/search")
def search_leads(payload: SearchRequest, user: dict = Depends(get_current_user)):
    try:
        result = search_public_businesses(payload.provider, payload.keyword, payload.city, payload.province, payload.limit)
    except ProviderError as exc:
        # Never expose raw upstream URLs, status traces or internal exception strings.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Live business search could not complete. Automatic retries were attempted. Check the API configuration and try again.",
        ) from exc

    # Leads already present in the qualified database are hidden from future searches.
    # The same production dedupe key used by MongoDB is used here, so search/import stay consistent.
    normalised_items = []
    all_candidate_keys: set[str] = set()
    seen_candidate_keys: set[str] = set()
    for raw_item in result["items"]:
        item = finalise_contact_metadata(raw_item)
        identity_keys = make_identity_keys(item)
        if not identity_keys:
            identity_keys = [make_dedupe_key(item)]
        if seen_candidate_keys.intersection(identity_keys):
            continue
        seen_candidate_keys.update(identity_keys)
        all_candidate_keys.update(identity_keys)
        item["_identity_keys"] = identity_keys
        normalised_items.append(item)

    existing_keys: set[str] = set()
    if all_candidate_keys:
        existing_docs = mongo.db.leads.find({
            "$or": [
                {"dedupe_key": {"$in": list(all_candidate_keys)}},
                {"dedupe_aliases": {"$in": list(all_candidate_keys)}},
            ]
        })
        for doc in existing_docs:
            if doc.get("dedupe_key"):
                existing_keys.add(doc["dedupe_key"])
            existing_keys.update(doc.get("dedupe_aliases") or [])

    prepared = []
    excluded_existing = 0
    for item in normalised_items:
        identity_keys = item.pop("_identity_keys", [])
        if existing_keys.intersection(identity_keys):
            excluded_existing += 1
            continue
        item.update(_score_fields(item))
        prepared.append(item)

    used_provider = result.get("provider", payload.provider)
    cache_label = "cached" if result.get("cached") else "live"
    log_activity(
        user,
        "Searched",
        "Public businesses",
        detail=f"{payload.keyword} in {payload.city} via {used_provider} ({cache_label})",
    )
    return {
        "items": prepared,
        "count": len(prepared),
        "excluded_existing": excluded_existing,
        "provider": used_provider,
        "cached": bool(result.get("cached")),
        "attribution": result.get("attribution"),
        "warnings": result.get("warnings", []),
        "endpoint": result.get("endpoint"),
    }


@router.post("")
def create_lead(payload: LeadCreateRequest, user: dict = Depends(get_current_user)):
    lead = _prepare_lead(payload.model_dump(), user)
    try:
        result = mongo.db.leads.insert_one(lead)
    except Exception as exc:
        if is_duplicate_key_error(exc):
            raise HTTPException(status_code=409, detail="This lead already exists") from exc
        raise
    lead["_id"] = result.inserted_id
    log_activity(user, "Created", "Lead", str(result.inserted_id), lead["business_name"])
    if lead["priority"] == "Hot":
        create_notification("Hot lead added", lead["business_name"], "lead", user["_id"], f"/leads/{result.inserted_id}")
    return _lead_view(lead)


@router.post("/bulk")
def bulk_import(payload: BulkImportRequest, user: dict = Depends(get_current_user)):
    imported = 0
    duplicates = 0
    items = []
    for input_lead in payload.leads:
        lead = _prepare_lead(input_lead.model_dump(), user)
        try:
            result = mongo.db.leads.insert_one(lead)
            lead["_id"] = result.inserted_id
            items.append(_lead_view(lead))
            imported += 1
        except Exception as exc:
            if is_duplicate_key_error(exc):
                duplicates += 1
            else:
                raise
    log_activity(user, "Imported", "Leads", detail=f"{imported} added, {duplicates} duplicates skipped")
    return {"imported": imported, "duplicates": duplicates, "items": items}


@router.get("")
def list_leads(
    user: dict = Depends(get_current_user),
    q: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    service: Optional[str] = None,
    website: Optional[str] = Query(default=None, pattern="^(available|missing)$"),
    social: Optional[str] = Query(default=None, pattern="^(available|missing)$"),
    contact: Optional[str] = Query(default=None, pattern="^(available|missing)$"),
    min_score: int = 0,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    query: dict = {**_scope_for_user(user), "lead_score": {"$gte": min_score}}
    clauses = []
    if q:
        clauses.append({"$or": [
            {"business_name": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
        ]})
    if city:
        query["city"] = {"$regex": f"^{city}$", "$options": "i"}
    if category:
        query["category"] = {"$regex": category, "$options": "i"}
    if priority:
        query["priority"] = priority
    if status:
        query["status"] = status
    if service:
        query["recommended_service"] = service
    if website == "available":
        query["website"] = {"$regex": ".+"}
    elif website == "missing":
        clauses.append({"$or": [{"website": None}, {"website": ""}]})
    if social == "available":
        clauses.append({"$or": [
            {"facebook": {"$regex": ".+"}},
            {"instagram": {"$regex": ".+"}},
            {"linkedin": {"$regex": ".+"}},
        ]})
    elif social == "missing":
        clauses.extend([
            {"$or": [{"facebook": None}, {"facebook": ""}]},
            {"$or": [{"instagram": None}, {"instagram": ""}]},
            {"$or": [{"linkedin": None}, {"linkedin": ""}]},
        ])
    if contact == "available":
        clauses.append({"$or": [{"phone": {"$regex": ".+"}}, {"email": {"$regex": ".+"}}]})
    elif contact == "missing":
        clauses.extend([
            {"$or": [{"phone": None}, {"phone": ""}]},
            {"$or": [{"email": None}, {"email": ""}]},
        ])
    if clauses:
        query["$and"] = clauses
    allowed_sort = {"created_at", "lead_score", "business_name", "city", "updated_at"}
    order = ASCENDING if sort_order == "asc" else DESCENDING
    cursor = mongo.db.leads.find(query).sort(sort_by if sort_by in allowed_sort else "created_at", order)
    total = mongo.db.leads.count_documents(query)
    items = [_lead_view(doc) for doc in cursor.skip((page - 1) * page_size).limit(page_size)]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/options")
def lead_options(user: dict = Depends(get_current_user)):
    scoped = list(mongo.db.leads.find(_scope_for_user(user)))
    return {
        "cities": sorted({item.get("city") for item in scoped if item.get("city")}),
        "categories": sorted({item.get("category") for item in scoped if item.get("category")}),
        "services": sorted({item.get("recommended_service") for item in scoped if item.get("recommended_service")}),
    }


@router.get("/export")
def export_leads(
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
    priority: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    query = _scope_for_user(user)
    if priority:
        query["priority"] = priority
    if status:
        query["status"] = status
    leads = list(mongo.db.leads.find(query).sort("lead_score", DESCENDING))
    fields = [
        "business_name", "category", "city", "province", "phone", "email", "website", "google_business_url",
        "facebook", "instagram", "linkedin", "contact_status", "contact_confidence", "contact_sources",
        "lead_score", "priority", "recommended_service", "status", "created_by_name", "assigned_salesperson", "follow_up_date", "notes",
    ]
    log_activity(user, "Exported", "Leads", detail=f"{len(leads)} leads as {format.upper()}")
    if format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Qualified Leads"
        sheet.append([field.replace("_", " ").title() for field in fields])
        for lead in leads:
            row = []
            for field in fields:
                value = lead.get(field, "") or ""
                if isinstance(value, list):
                    value = ", ".join(str(item) for item in value)
                row.append(value)
            sheet.append(row)
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=qualified-leads.xlsx"},
        )
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for lead in leads:
        row = {}
        for field in fields:
            value = lead.get(field, "") or ""
            row[field] = ", ".join(str(item) for item in value) if isinstance(value, list) else value
        writer.writerow(row)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=qualified-leads.csv"},
    )


@router.get("/{lead_id}")
def get_lead(lead_id: str, user: dict = Depends(get_current_user)):
    lead = _lead_or_404(lead_id, user)
    result = _lead_view(lead)
    # Old records created by previous builds still receive the new display metadata.
    result.setdefault("score_profile", score_profile(int(result.get("lead_score") or 0)))
    result.setdefault("score_breakdown", build_score_breakdown(result, int(result.get("lead_score") or 0)))
    result = finalise_contact_metadata(result)
    competitors = [
        _lead_view(item)
        for item in mongo.db.leads.find({
            **_scope_for_user(user),
            "_id": {"$nin": [lead["_id"]]},
            "city": lead.get("city"),
            "category": lead.get("category"),
        }).sort("lead_score", DESCENDING).limit(3)
    ]
    result["competitor_insights"] = competitors
    return result


@router.patch("/{lead_id}")
def update_lead(lead_id: str, payload: LeadUpdateRequest, user: dict = Depends(get_current_user)):
    lead = _lead_or_404(lead_id, user)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in list(changes.items()):
        if hasattr(value, "isoformat"):
            changes[key] = value.isoformat()

    # Keep the CRM stage and deal outcome consistent.
    if changes.get("deal_status") == "Won":
        changes["status"] = "Completed"
    elif changes.get("deal_status") == "Lost":
        changes["status"] = "Cancel"
    if changes.get("status") == "Completed":
        changes["deal_status"] = "Won"
    elif changes.get("status") == "Cancel":
        changes["deal_status"] = "Lost"
    elif changes.get("status") in {"Not Contacted", "Contacted", "Follow-up"} and lead.get("deal_status") in {"Won", "Lost"}:
        changes.setdefault("deal_status", "Open")

    if changes.get("status") == "Contacted" and not changes.get("last_contact_date") and not lead.get("last_contact_date"):
        changes["last_contact_date"] = datetime.now(timezone.utc).date().isoformat()

    workflow_fields = ["status", "call_status", "proposal_status", "deal_status"]
    workflow_changes = {
        key: value for key, value in changes.items()
        if key in workflow_fields and value != lead.get(key)
    }

    changes["updated_at"] = datetime.now(timezone.utc)
    mongo.db.leads.update_one({"_id": lead["_id"]}, {"$set": changes})
    updated = mongo.db.leads.find_one({"_id": lead["_id"]})
    log_activity(user, "Updated", "Lead", lead_id, ", ".join(key for key in changes if key != "updated_at"))

    if user.get("role") == "user" and workflow_changes:
        if workflow_changes.get("status") == "Completed" or workflow_changes.get("deal_status") == "Won":
            title = "Deal completed"
            kind = "completed"
        elif workflow_changes.get("status") == "Cancel" or workflow_changes.get("deal_status") == "Lost":
            title = "Deal cancelled"
            kind = "cancelled"
        elif workflow_changes.get("status") == "Contacted" or workflow_changes.get("call_status") == "Connected":
            title = "Lead contacted"
            kind = "contact"
        else:
            title = "Lead workflow updated"
            kind = "followup"
        detail = " · ".join(f"{key.replace('_', ' ').title()}: {value}" for key, value in workflow_changes.items())
        create_admin_notification(
            title,
            f"{user.get('name', 'A user')} updated {lead.get('business_name', 'a lead')}. {detail}",
            kind,
            f"/leads/{lead_id}",
        )

    return _lead_view(updated)


@router.post("/{lead_id}/enrich-contact")
def enrich_contact(lead_id: str, user: dict = Depends(get_current_user)):
    lead = _lead_or_404(lead_id, user)
    enriched, notes = enrich_single_lead(lead)
    score_fields = _score_fields(enriched, enriched.get("audit") or None)
    update = {
        **{key: enriched.get(key) for key in [
            "phone", "email", "website", "google_business_url", "google_place_id", "facebook", "instagram", "linkedin",
            "address", "latitude", "longitude", "rating", "reviews_count", "contact_sources", "contact_confidence",
            "contact_status", "contact_search_url", "contact_discovery",
        ]},
        **score_fields,
        "dedupe_aliases": make_identity_keys(enriched),
        "updated_at": datetime.now(timezone.utc),
    }
    mongo.db.leads.update_one({"_id": lead["_id"]}, {"$set": update})
    updated = mongo.db.leads.find_one({"_id": lead["_id"]})
    log_activity(user, "Enriched", "Lead contact", lead_id, lead["business_name"])
    return {"lead": _lead_view(updated), "notes": notes}


@router.post("/{lead_id}/audit")
def run_audit(lead_id: str, user: dict = Depends(get_current_user)):
    lead = _lead_or_404(lead_id, user)
    enriched, enrichment_notes = enrich_single_lead(lead)
    lead.update(enriched)

    if lead.get("website"):
        try:
            audit = audit_website(lead["website"])
        except (UnsafeURL, Exception) as exc:
            audit = {
                "website_available": True,
                "audit_error": "Website audit could not complete. The site may block automated checks or be temporarily unavailable.",
                "ssl_enabled": str(lead.get("website", "")).startswith("https://"),
                "mobile_friendly": False,
                "seo_score": 0,
                "contact_form": False,
                "whatsapp_button": False,
                "booking_system": False,
                "broken_links": 0,
            }
    else:
        audit = {
            "website_available": False,
            "ssl_enabled": False,
            "mobile_friendly": False,
            "seo_score": 0,
            "contact_form": False,
            "whatsapp_button": False,
            "booking_system": False,
            "broken_links": 0,
            "website_age": None,
        }
    audit["social_media"] = _social_audit(lead)
    audit["contact_verification"] = {
        "status": lead.get("contact_status"),
        "confidence": lead.get("contact_confidence"),
        "sources": lead.get("contact_sources") or [],
        "notes": enrichment_notes,
        "rule": "Only public, source-attributed contact details are stored. Unverified numbers are never invented.",
    }

    score_fields = _score_fields(lead, audit)
    update = {
        "audit": audit,
        **score_fields,
        "dedupe_aliases": make_identity_keys(lead),
        **{key: lead.get(key) for key in [
            "phone", "email", "website", "google_business_url", "google_place_id", "facebook", "instagram", "linkedin",
            "address", "latitude", "longitude", "rating", "reviews_count", "contact_sources", "contact_confidence",
            "contact_status", "contact_search_url", "contact_discovery",
        ]},
        "updated_at": datetime.now(timezone.utc),
    }
    mongo.db.leads.update_one({"_id": lead["_id"]}, {"$set": update})
    log_activity(user, "Audited", "Lead", lead_id, lead["business_name"])
    return {"lead_id": lead_id, **update}
