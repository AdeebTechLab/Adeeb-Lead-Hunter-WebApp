from datetime import datetime, timezone

from app.core.objectid import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.core.database import mongo
from app.core.dependencies import get_current_user
from app.core.serializers import serialize_doc
from app.models import LeadListCreateRequest, LeadListMemberRequest, LeadListUpdateRequest
from app.services.activity import log_activity

router = APIRouter(prefix="/lists", tags=["Saved Lead Lists"])


def _list_or_404(list_id: str, user: dict) -> dict:
    if not ObjectId.is_valid(list_id):
        raise HTTPException(status_code=404, detail="Lead list not found")
    item = mongo.db.lead_lists.find_one({"_id": ObjectId(list_id), "created_by": user["_id"]})
    if not item:
        raise HTTPException(status_code=404, detail="Lead list not found")
    return item


def _serialize_list(item: dict) -> dict:
    result = serialize_doc(item)
    ids = item.get("lead_ids", [])
    leads = [serialize_doc(lead) for lead in mongo.db.leads.find({"_id": {"$in": ids}}).sort("lead_score", -1)] if ids else []
    result["lead_count"] = len(leads)
    result["leads"] = leads
    return result


@router.get("")
def list_saved_lists(user: dict = Depends(get_current_user)):
    items = [_serialize_list(item) for item in mongo.db.lead_lists.find({"created_by": user["_id"]}).sort("updated_at", -1)]
    return {"items": items}


@router.post("")
def create_saved_list(payload: LeadListCreateRequest, user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    item = {
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "lead_ids": [],
        "created_by": user["_id"],
        "created_at": now,
        "updated_at": now,
    }
    item["_id"] = mongo.db.lead_lists.insert_one(item).inserted_id
    log_activity(user, "Created", "Lead list", str(item["_id"]), item["name"])
    return _serialize_list(item)


@router.patch("/{list_id}")
def update_saved_list(list_id: str, payload: LeadListUpdateRequest, user: dict = Depends(get_current_user)):
    item = _list_or_404(list_id, user)
    changes = payload.model_dump(exclude_unset=True)
    changes["updated_at"] = datetime.now(timezone.utc)
    mongo.db.lead_lists.update_one({"_id": item["_id"]}, {"$set": changes})
    return _serialize_list(mongo.db.lead_lists.find_one({"_id": item["_id"]}))


@router.post("/{list_id}/leads")
def add_to_saved_list(list_id: str, payload: LeadListMemberRequest, user: dict = Depends(get_current_user)):
    item = _list_or_404(list_id, user)
    if not ObjectId.is_valid(payload.lead_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    lead_id = ObjectId(payload.lead_id)
    if not mongo.db.leads.find_one({"_id": lead_id}):
        raise HTTPException(status_code=404, detail="Lead not found")
    ids = item.get("lead_ids", [])
    if lead_id not in ids:
        ids.append(lead_id)
        mongo.db.lead_lists.update_one({"_id": item["_id"]}, {"$set": {"lead_ids": ids, "updated_at": datetime.now(timezone.utc)}})
        log_activity(user, "Added", "Lead list", list_id, payload.lead_id)
    return _serialize_list(mongo.db.lead_lists.find_one({"_id": item["_id"]}))


@router.delete("/{list_id}/leads/{lead_id}")
def remove_from_saved_list(list_id: str, lead_id: str, user: dict = Depends(get_current_user)):
    item = _list_or_404(list_id, user)
    ids = [value for value in item.get("lead_ids", []) if str(value) != lead_id]
    mongo.db.lead_lists.update_one({"_id": item["_id"]}, {"$set": {"lead_ids": ids, "updated_at": datetime.now(timezone.utc)}})
    log_activity(user, "Removed", "Lead list", list_id, lead_id)
    return _serialize_list(mongo.db.lead_lists.find_one({"_id": item["_id"]}))


@router.delete("/{list_id}")
def delete_saved_list(list_id: str, user: dict = Depends(get_current_user)):
    item = _list_or_404(list_id, user)
    mongo.db.lead_lists.delete_one({"_id": item["_id"]})
    log_activity(user, "Deleted", "Lead list", list_id, item["name"])
    return {"ok": True}
