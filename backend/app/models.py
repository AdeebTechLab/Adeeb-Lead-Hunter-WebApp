from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

Role = Literal["admin", "user"]
LeadPriority = Literal["Hot", "Warm", "Cold"]
LeadStatus = Literal["Not Contacted", "Contacted", "Follow-up", "Cancel", "Completed"]
ProviderId = Literal["auto", "google", "geoapify", "osm"]


def normalize_cnic(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 13:
        raise ValueError("CNIC must contain exactly 13 digits")
    return f"{digits[:5]}-{digits[5:12]}-{digits[12]}"


def validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("Password must include at least one letter and one number")
    return value


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    cnic: str
    city: str = Field(min_length=2, max_length=80)

    @field_validator("name", "city")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("cnic")
    @classmethod
    def clean_cnic(cls, value: str) -> str:
        return normalize_cnic(value)

    @field_validator("password")
    @classmethod
    def password_rules(cls, value: str) -> str:
        return validate_password(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    email: Optional[EmailStr] = None
    cnic: Optional[str] = None
    city: Optional[str] = Field(default=None, min_length=2, max_length=80)

    @field_validator("name", "city")
    @classmethod
    def clean_text(cls, value: Optional[str]) -> Optional[str]:
        return " ".join(value.strip().split()) if value is not None else value

    @field_validator("cnic")
    @classmethod
    def clean_cnic(cls, value: Optional[str]) -> Optional[str]:
        return normalize_cnic(value) if value is not None else value


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_rules(cls, value: str) -> str:
        return validate_password(value)


class PasswordResetRequest(BaseModel):
    temporary_password: str = Field(min_length=8, max_length=128)

    @field_validator("temporary_password")
    @classmethod
    def password_rules(cls, value: str) -> str:
        return validate_password(value)


class SearchRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=80)
    province: str = Field(default="Punjab", max_length=80)
    provider: ProviderId = "auto"
    limit: int = Field(default=12, ge=1, le=40)


class LeadCreateRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=180)
    category: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=2, max_length=80)
    province: str = Field(default="Punjab", max_length=80)
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    google_business_url: Optional[str] = None
    google_place_id: Optional[str] = None
    facebook: Optional[str] = None
    instagram: Optional[str] = None
    linkedin: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source: str = "manual"
    source_url: Optional[str] = None
    reviews_count: int = 0
    rating: Optional[float] = None
    tags: List[str] = Field(default_factory=list)
    contact_sources: List[str] = Field(default_factory=list)
    contact_confidence: Optional[str] = None
    contact_status: Optional[str] = None
    contact_search_url: Optional[str] = None
    contact_discovery: Dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "website",
        "google_business_url",
        "facebook",
        "instagram",
        "linkedin",
        "contact_search_url",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class BulkImportRequest(BaseModel):
    leads: List[LeadCreateRequest]


class LeadUpdateRequest(BaseModel):
    status: Optional[LeadStatus] = None
    notes: Optional[str] = None
    follow_up_date: Optional[date] = None
    last_contact_date: Optional[date] = None
    assigned_salesperson: Optional[str] = None
    call_status: Optional[str] = None
    proposal_status: Optional[str] = None
    deal_status: Optional[str] = None
    meeting_notes: Optional[str] = None
    tags: Optional[List[str]] = None


class LeadListCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=240)


class LeadListUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=240)


class LeadListMemberRequest(BaseModel):
    lead_id: str


class NotificationUpdateRequest(BaseModel):
    read: bool = True


class AuditResponse(BaseModel):
    lead_id: str
    audit: Dict[str, Any]
    lead_score: int
    priority: LeadPriority
    recommended_service: str
    score_reasons: List[str]
    business_summary: str
    outreach: Dict[str, str]
