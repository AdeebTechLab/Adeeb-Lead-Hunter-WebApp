from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import mongo
from app.core.dependencies import get_current_user
from app.core.serializers import serialize_doc

router = APIRouter(tags=["Dashboard"])


def _scope(user: dict) -> dict:
    return {} if user.get("role") == "admin" else {"created_by": user["_id"]}


def _lead_view(item: dict) -> dict:
    result = serialize_doc(item)
    if not result.get("created_by_name") and item.get("created_by"):
        creator = mongo.db.users.find_one({"_id": item.get("created_by")})
        result["created_by_name"] = creator.get("name") if creator else "Former user"
    return result


def _as_utc(value) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _period_bounds(period: str, from_date: date | None, to_date: date | None, month_value: str | None = None) -> tuple[datetime | None, datetime | None, str]:
    now = datetime.now(timezone.utc)
    if period == "all":
        return None, None, "All time"
    if period == "month":
        year, month = now.year, now.month
        if month_value:
            try:
                parsed = datetime.strptime(month_value, "%Y-%m")
                year, month = parsed.year, parsed.month
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Month must use YYYY-MM format") from exc
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        end = min(now, next_month - timedelta(microseconds=1)) if start <= now else next_month - timedelta(microseconds=1)
        return start, end, start.strftime("%B %Y")
    if period != "custom":
        raise HTTPException(status_code=422, detail="Unsupported dashboard period")
    if not from_date or not to_date:
        raise HTTPException(status_code=422, detail="Select both From and To dates")
    if from_date > to_date:
        raise HTTPException(status_code=422, detail="From date cannot be after To date")
    start = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(to_date, time.max, tzinfo=timezone.utc)
    return start, end, f"{from_date.strftime('%d %b %Y')} – {to_date.strftime('%d %b %Y')}"


def _within_period(items: Iterable[dict], start: datetime | None, end: datetime | None) -> list[dict]:
    if start is None and end is None:
        return list(items)
    rows: list[dict] = []
    for item in items:
        created = _as_utc(item.get("created_at"))
        if created is None:
            continue
        if start is not None and created < start:
            continue
        if end is not None and created > end:
            continue
        rows.append(item)
    return rows


def _trend(items: list[dict], start: datetime | None, end: datetime | None) -> tuple[list[dict], str]:
    timestamps = [_as_utc(item.get("created_at")) for item in items]
    timestamps = [value for value in timestamps if value is not None]
    if start is None:
        start = min(timestamps) if timestamps else datetime.now(timezone.utc)
    if end is None:
        end = max(timestamps) if timestamps else datetime.now(timezone.utc)
    span_days = max(0, (end.date() - start.date()).days)
    monthly = span_days > 62
    buckets: dict[str, dict] = defaultdict(lambda: {"leads": 0, "completed": 0, "cancelled": 0})
    labels: dict[str, str] = {}
    for item in items:
        created = _as_utc(item.get("created_at"))
        if created is None:
            continue
        if monthly:
            key = created.strftime("%Y-%m")
            label = created.strftime("%b %Y")
        else:
            key = created.strftime("%Y-%m-%d")
            label = created.strftime("%d %b")
        labels[key] = label
        buckets[key]["leads"] += 1
        if item.get("status") == "Completed":
            buckets[key]["completed"] += 1
        elif item.get("status") == "Cancel":
            buckets[key]["cancelled"] += 1
    result = [{"key": key, "name": labels[key], **buckets[key]} for key in sorted(buckets)]
    return result, "month" if monthly else "day"


@router.get("/dashboard")
def dashboard(
    period: str = Query("all", pattern="^(all|month|custom)$"),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    user: dict = Depends(get_current_user),
):
    scope = _scope(user)
    start, end, period_label = _period_bounds(period, from_date, to_date, month)
    all_scoped = list(mongo.db.leads.find(scope))
    scoped_leads = _within_period(all_scoped, start, end)

    total = len(scoped_leads)
    hot = sum(1 for item in scoped_leads if item.get("priority") == "Hot")
    followups = sum(1 for item in scoped_leads if item.get("status") == "Follow-up")
    completed = sum(1 for item in scoped_leads if item.get("status") == "Completed")
    cancelled = sum(1 for item in scoped_leads if item.get("status") == "Cancel")
    contacted = sum(1 for item in scoped_leads if item.get("status") in {"Contacted", "Follow-up", "Cancel", "Completed"})
    conversion = round((completed / contacted) * 100, 1) if contacted else 0

    recent_rows = sorted(scoped_leads, key=lambda item: _as_utc(item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:6]
    top_rows = sorted(scoped_leads, key=lambda item: float(item.get("lead_score") or 0), reverse=True)[:5]

    pipeline = [
        {"name": label, "value": sum(1 for item in scoped_leads if item.get("status") == label)}
        for label in ["Not Contacted", "Contacted", "Follow-up", "Cancel", "Completed"]
    ]

    service_names = sorted({item.get("recommended_service") for item in scoped_leads if item.get("recommended_service")})
    services = [
        {"name": service, "value": sum(1 for item in scoped_leads if item.get("recommended_service") == service)}
        for service in service_names
    ]

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    new_this_week = sum(1 for item in scoped_leads if (_as_utc(item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff)
    trend, trend_granularity = _trend(scoped_leads, start, end)

    actual_dates = [_as_utc(item.get("created_at")) for item in scoped_leads]
    actual_dates = [value for value in actual_dates if value]
    display_from = start or (min(actual_dates) if actual_dates else None)
    display_to = end or (max(actual_dates) if actual_dates else datetime.now(timezone.utc))

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
        "period": {
            "mode": period,
            "label": period_label,
            "from_date": display_from.date().isoformat() if display_from else None,
            "to_date": display_to.date().isoformat() if display_to else None,
            "trend_granularity": trend_granularity,
        },
        "trend": trend,
        "pipeline": pipeline,
        "services": services,
        "recent_leads": [_lead_view(item) for item in recent_rows],
        "top_leads": [_lead_view(item) for item in top_rows],
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
        "won": completed,
        "lost": cancelled,
    }
