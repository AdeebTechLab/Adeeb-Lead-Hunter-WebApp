from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from app.core.database import mongo
from app.core.dependencies import get_current_user
from app.core.serializers import serialize_doc

router = APIRouter(tags=["Dashboard"])


def _scope(user: dict) -> dict:
    return {} if user.get("role") == "admin" else {"created_by": user["_id"]}


def _merge(scope: dict, extra: dict | None = None) -> dict:
    return {**scope, **(extra or {})}


def _lead_view(item: dict) -> dict:
    result = serialize_doc(item)
    if not result.get("created_by_name") and item.get("created_by"):
        creator = mongo.db.users.find_one({"_id": item.get("created_by")})
        result["created_by_name"] = creator.get("name") if creator else "Former user"
    return result


@router.get("/dashboard")
def dashboard(
    period: str = Query("all", description="all, month or custom"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    scope = _scope(user)
    date_filter = {}
    now = datetime.now(timezone.utc)
    if period == "month":
        date_filter = {"created_at": {"$gte": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)}}
    elif period == "custom" and start_date and end_date:
        try:
            date_filter = {"created_at": {"$gte": datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc), "$lte": datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)}}
        except ValueError:
            date_filter = {}
    scope = _merge(scope, date_filter)
    total = mongo.db.leads.count_documents(scope)
    hot = mongo.db.leads.count_documents(_merge(scope, {"priority": "Hot"}))
    followups = mongo.db.leads.count_documents(_merge(scope, {"status": "Follow-up"}))
    completed = mongo.db.leads.count_documents(_merge(scope, {"status": "Completed"}))
    cancelled = mongo.db.leads.count_documents(_merge(scope, {"status": "Cancel"}))
    contacted = mongo.db.leads.count_documents(
        _merge(scope, {"status": {"$in": ["Contacted", "Follow-up", "Cancel", "Completed"]}})
    )
    conversion = round((completed / contacted) * 100, 1) if contacted else 0
    recent = [_lead_view(item) for item in mongo.db.leads.find(scope).sort("created_at", -1).limit(6)]
    top = [_lead_view(item) for item in mongo.db.leads.find(scope).sort("lead_score", -1).limit(5)]

    pipeline = [
        {"name": label, "value": mongo.db.leads.count_documents(_merge(scope, {"status": label}))}
        for label in ["Not Contacted", "Contacted", "Follow-up", "Cancel", "Completed"]
    ]

    scoped_leads = list(mongo.db.leads.find(scope))
    service_names = sorted({item.get("recommended_service") for item in scoped_leads if item.get("recommended_service")})
    services = [
        {"name": service, "value": sum(1 for item in scoped_leads if item.get("recommended_service") == service)}
        for service in service_names
    ]

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    new_this_week = mongo.db.leads.count_documents(_merge(scope, {"created_at": {"$gte": cutoff}}))
    return {
        "stats": {
            "total_leads": total,
            "hot_leads": hot,
            "follow_ups": followups,
            "completed_deals": completed,
            "cancelled_deals": cancelled,
            "conversion_rate": conversion,
            "new_this_week": new_this_week,
            "scope": "workspace" if user.get("role") == "admin" else "personal",
        },
        "pipeline": pipeline,
        "services": services,
        "recent_leads": recent,
        "top_leads": top,
    }


@router.get("/analytics")
def analytics(user: dict = Depends(get_current_user)):
    scope = _scope(user)
    scoped_leads = list(mongo.db.leads.find(scope))

    priorities = [
        {"name": key, "value": sum(1 for item in scoped_leads if item.get("priority") == key)}
        for key in ["Hot", "Warm", "Cold"]
    ]
    statuses = [
        {"name": key, "value": sum(1 for item in scoped_leads if item.get("status") == key)}
        for key in ["Not Contacted", "Contacted", "Follow-up", "Cancel", "Completed"]
    ]
    city_names = sorted({item.get("city") for item in scoped_leads if item.get("city")})
    cities = [
        {"name": city, "value": sum(1 for item in scoped_leads if item.get("city") == city)}
        for city in city_names
    ]
    cities.sort(key=lambda item: item["value"], reverse=True)

    scores = [item.get("lead_score") for item in scoped_leads if isinstance(item.get("lead_score"), (int, float))]
    average_score = round(sum(scores) / len(scores), 1) if scores else 0
    completed = sum(1 for item in scoped_leads if item.get("status") == "Completed")
    cancelled = sum(1 for item in scoped_leads if item.get("status") == "Cancel")
    open_deals = sum(1 for item in scoped_leads if item.get("status") not in {"Completed", "Cancel"})

    return {
        "priorities": priorities,
        "statuses": statuses,
        "cities": cities[:8],
        "average_score": average_score,
        "completed": completed,
        "cancelled": cancelled,
        "open": open_deals,
        # Compatibility aliases for any cached frontend during rolling deployment.
        "won": completed,
        "lost": cancelled,
    }
