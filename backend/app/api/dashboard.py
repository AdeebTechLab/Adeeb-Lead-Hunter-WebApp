from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from app.core.database import mongo
from app.core.dependencies import get_current_user
from app.core.serializers import serialize_doc

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard")
def dashboard(user: dict = Depends(get_current_user)):
    total = mongo.db.leads.count_documents({})
    hot = mongo.db.leads.count_documents({"priority": "Hot"})
    followups = mongo.db.leads.count_documents({"status": "Follow-up"})
    won = mongo.db.leads.count_documents({"deal_status": "Won"})
    contacted = mongo.db.leads.count_documents({"status": {"$in": ["Contacted", "Follow-up", "Closed"]}})
    conversion = round((won / contacted) * 100, 1) if contacted else 0
    recent = [serialize_doc(item) for item in mongo.db.leads.find().sort("created_at", -1).limit(6)]
    top = [serialize_doc(item) for item in mongo.db.leads.find().sort("lead_score", -1).limit(5)]
    pipeline = []
    for label in ["Not Contacted", "Contacted", "Follow-up", "Closed"]:
        pipeline.append({"name": label, "value": mongo.db.leads.count_documents({"status": label})})
    services = []
    for service in mongo.db.leads.distinct("recommended_service"):
        services.append({"name": service, "value": mongo.db.leads.count_documents({"recommended_service": service})})
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    new_this_week = mongo.db.leads.count_documents({"created_at": {"$gte": cutoff}})
    return {
        "stats": {
            "total_leads": total,
            "hot_leads": hot,
            "follow_ups": followups,
            "conversion_rate": conversion,
            "new_this_week": new_this_week,
        },
        "pipeline": pipeline,
        "services": services,
        "recent_leads": recent,
        "top_leads": top,
    }


@router.get("/analytics")
def analytics(user: dict = Depends(get_current_user)):
    priorities = [{"name": key, "value": mongo.db.leads.count_documents({"priority": key})} for key in ["Hot", "Warm", "Cold"]]
    statuses = [{"name": key, "value": mongo.db.leads.count_documents({"status": key})} for key in ["Not Contacted", "Contacted", "Follow-up", "Closed"]]
    cities = []
    for city in mongo.db.leads.distinct("city"):
        cities.append({"name": city, "value": mongo.db.leads.count_documents({"city": city})})
    cities.sort(key=lambda item: item["value"], reverse=True)
    average = list(mongo.db.leads.aggregate([{"$group": {"_id": None, "value": {"$avg": "$lead_score"}}}]))
    return {
        "priorities": priorities,
        "statuses": statuses,
        "cities": cities[:8],
        "average_score": round(average[0]["value"], 1) if average else 0,
        "won": mongo.db.leads.count_documents({"deal_status": "Won"}),
        "lost": mongo.db.leads.count_documents({"deal_status": "Lost"}),
        "open": mongo.db.leads.count_documents({"deal_status": "Open"}),
    }
