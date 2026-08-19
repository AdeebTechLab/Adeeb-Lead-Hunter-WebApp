from functools import lru_cache
from typing import Annotated, List, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Adeeb Lead Hunter"
    environment: Literal["development", "production", "test"] = "development"
    api_prefix: str = "/api"
    secret_key: str = "development-secret-change-before-production-123456"
    access_token_expire_minutes: int = 480
    enable_api_docs: bool = True

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "ai_lead_hunter"
    mongodb_max_pool_size: int = 30
    mongodb_min_pool_size: int = 0

    frontend_origins: Annotated[List[str], NoDecode] = ["http://localhost:5173"]
    allow_public_signup: bool = True

    # An administrator is created automatically on first boot when one does not exist.
    default_admin_name: str = "Admin User"
    default_admin_email: str = "admin@example.com"
    default_admin_password: str = "Admin@123"
    default_admin_cnic: str = "00000-0000000-0"
    default_admin_city: str = "Islamabad"

    # Cloudinary profile images. API secret is backend-only.
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    cloudinary_profile_folder: str = "ai-lead-hunter/profiles"
    profile_image_max_bytes: int = 1_048_576

    # Public business-data providers.
    public_data_user_agent: str = "AILeadHunter/1.0 (contact: replace-with-your-email@example.com)"
    public_data_referer: str = "http://localhost:5173"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    overpass_urls: Annotated[List[str], NoDecode] = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.nchc.org.tw/api/interpreter",
    ]
    provider_retry_attempts: int = 2
    provider_timeout_seconds: float = 35.0
    provider_cache_ttl_seconds: int = 900

    geoapify_api_key: str = ""
    geoapify_base_url: str = "https://api.geoapify.com"
    # Optional same-key contact fallback. Place Details is only called for a
    # small number of leads still missing direct contact after TomTom/website
    # enrichment because Geoapify bills it at a higher credit cost than Places.
    geoapify_contact_details_limit: int = 5
    geoapify_contact_timeout_seconds: float = 8.0
    geoapify_contact_cache_ttl_seconds: int = 604800

    google_places_api_key: str = ""
    google_places_base_url: str = "https://places.googleapis.com/v1"
    google_contact_enrichment_limit: int = 8

    # Optional free-tier contact enrichment. TomTom is not used for lead discovery;
    # it only cross-checks Geoapify/OpenStreetMap results for public phone/website data.
    tomtom_api_key: str = ""
    tomtom_base_url: str = "https://api.tomtom.com"
    tomtom_contact_enrichment_limit: int = 20
    tomtom_contact_match_radius_m: int = 3500
    tomtom_contact_timeout_seconds: float = 8.0
    tomtom_contact_cache_ttl_seconds: int = 604800

    enable_website_contact_enrichment: bool = True
    website_contact_enrichment_limit: int = 20
    website_contact_timeout_seconds: float = 6.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("frontend_origins", "overpass_urls", mode="before")
    @classmethod
    def split_csv(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                import json

                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


    @field_validator(
        "tomtom_contact_enrichment_limit",
        "tomtom_contact_match_radius_m",
        "tomtom_contact_timeout_seconds",
        "tomtom_contact_cache_ttl_seconds",
        mode="before",
    )
    @classmethod
    def tolerate_tomtom_placeholder_values(cls, value, info):
        """Do not crash deployment when an env placeholder name was pasted as its value.

        Render users sometimes enter e.g. TOMTOM_CONTACT_TIMEOUT_SECONDS as the
        value instead of 8. Only blank/self-referential placeholders fall back
        to safe defaults; genuinely invalid numeric values still fail validation.
        """
        defaults = {
            "tomtom_contact_enrichment_limit": 20,
            "tomtom_contact_match_radius_m": 3500,
            "tomtom_contact_timeout_seconds": 8.0,
            "tomtom_contact_cache_ttl_seconds": 604800,
        }
        if value is None:
            return defaults[info.field_name]
        if isinstance(value, str):
            cleaned = value.strip()
            env_name = info.field_name.upper()
            if not cleaned or cleaned.upper() in {env_name, f"${{{env_name}}}", f"${env_name}"}:
                return defaults[info.field_name]
        return value

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.environment != "production":
            return self
        if len(self.secret_key) < 32 or "change-before-production" in self.secret_key:
            raise ValueError("SECRET_KEY must be a unique value of at least 32 characters in production")
        if not self.mongodb_uri or "localhost" in self.mongodb_uri:
            raise ValueError("MONGODB_URI must point to the production MongoDB deployment")
        if not self.frontend_origins:
            raise ValueError("FRONTEND_ORIGINS must include the deployed frontend origin")
        if not self.default_admin_password or self.default_admin_password == "Admin@123":
            raise ValueError("DEFAULT_ADMIN_PASSWORD must be changed before production deployment")
        if self.default_admin_cnic == "00000-0000000-0":
            raise ValueError("DEFAULT_ADMIN_CNIC must be set before production deployment")
        if not self.cloudinary_configured:
            raise ValueError("Cloudinary credentials are required in production")
        if not (self.geoapify_api_key or self.google_places_api_key):
            raise ValueError("Configure GEOAPIFY_API_KEY or GOOGLE_PLACES_API_KEY for production lead search")
        if "localhost" in self.public_data_referer:
            raise ValueError("PUBLIC_DATA_REFERER must use the deployed frontend URL in production")
        return self

    @property
    def cloudinary_configured(self) -> bool:
        return bool(self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
