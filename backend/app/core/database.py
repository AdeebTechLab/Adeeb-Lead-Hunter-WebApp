from __future__ import annotations

from typing import Any

from app.core.config import settings


class Database:
    def __init__(self) -> None:
        self.client: Any = None
        self.db: Any = None

    def connect(self) -> None:
        if settings.environment == "test":
            from app.core.db_compat import MemoryDatabase

            self.db = MemoryDatabase()
        else:
            from pymongo import MongoClient

            self.client = MongoClient(
                settings.mongodb_uri,
                appName="adeeb-lead-hunter-api",
                serverSelectionTimeoutMS=8000,
                connectTimeoutMS=8000,
                socketTimeoutMS=20000,
                retryWrites=True,
                maxPoolSize=settings.mongodb_max_pool_size,
                minPoolSize=settings.mongodb_min_pool_size,
            )
            self.client.admin.command("ping")
            self.db = self.client[settings.mongodb_db]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        ASCENDING, DESCENDING = 1, -1

        self.db.users.create_index([("email", ASCENDING)], unique=True)
        self.db.users.create_index([("cnic", ASCENDING)], unique=True, sparse=True)
        self.db.users.create_index([("role", ASCENDING), ("active", ASCENDING)])
        self.db.leads.create_index([("dedupe_key", ASCENDING)], unique=True, sparse=True)
        self.db.leads.create_index([("dedupe_aliases", ASCENDING)])
        self.db.leads.create_index([("created_at", DESCENDING)])
        self.db.leads.create_index([("created_by", ASCENDING), ("created_at", DESCENDING)])
        self.db.leads.create_index([("lead_score", DESCENDING)])
        self.db.leads.create_index([("city", ASCENDING), ("category", ASCENDING), ("lead_score", DESCENDING)])
        self.db.activity_logs.create_index([("created_at", DESCENDING)])
        self.db.notifications.create_index([("user_id", ASCENDING), ("read", ASCENDING), ("created_at", DESCENDING)])
        self.db.lead_lists.create_index([("created_by", ASCENDING), ("created_at", DESCENDING)])

    def close(self) -> None:
        if self.client:
            self.client.close()


mongo = Database()
