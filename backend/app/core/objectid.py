from __future__ import annotations

import re
import secrets

try:
    from bson import ObjectId as ObjectId  # type: ignore
except ImportError:
    class ObjectId(str):
        """Small compatibility ID used only when PyMongo is unavailable in test mode."""

        def __new__(cls, value: str | None = None):
            value = value or secrets.token_hex(12)
            if not cls.is_valid(value):
                raise ValueError("Invalid ObjectId")
            return str.__new__(cls, value)

        @staticmethod
        def is_valid(value) -> bool:
            return bool(re.fullmatch(r"[0-9a-fA-F]{24}", str(value or "")))
