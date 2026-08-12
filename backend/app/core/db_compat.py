from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.core.objectid import ObjectId

ASCENDING = 1
DESCENDING = -1


class DuplicateKeyError(Exception):
    pass


def is_duplicate_key_error(exc: Exception) -> bool:
    if isinstance(exc, DuplicateKeyError):
        return True
    try:
        from pymongo.errors import DuplicateKeyError as PyMongoDuplicateKeyError
        return isinstance(exc, PyMongoDuplicateKeyError)
    except ImportError:
        return False


@dataclass
class InsertOneResult:
    inserted_id: Any


@dataclass
class UpdateResult:
    matched_count: int
    modified_count: int


class MemoryCursor:
    def __init__(self, documents: Iterable[dict]):
        self.documents = [copy.deepcopy(item) for item in documents]

    def sort(self, key: str, direction: int = ASCENDING):
        reverse = direction == DESCENDING
        self.documents.sort(key=lambda item: (item.get(key) is None, item.get(key)), reverse=reverse)
        return self

    def skip(self, count: int):
        self.documents = self.documents[count:]
        return self

    def limit(self, count: int):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


def _compare(value: Any, condition: Any) -> bool:
    if not isinstance(condition, dict) or not any(str(key).startswith("$") for key in condition):
        return value == condition
    regex_options = condition.get("$options", "")
    for operator, expected in condition.items():
        if operator == "$options":
            continue
        if operator == "$gte" and not (value is not None and value >= expected):
            return False
        if operator == "$in":
            if isinstance(value, list):
                if not any(item in expected for item in value):
                    return False
            elif value not in expected:
                return False
        if operator == "$nin":
            if isinstance(value, list):
                if any(item in expected for item in value):
                    return False
            elif value in expected:
                return False
        if operator == "$regex":
            flags = re.I if "i" in regex_options else 0
            if re.search(expected, str(value or ""), flags) is None:
                return False
    return True


def matches(document: dict, query: dict | None) -> bool:
    if not query:
        return True
    for key, condition in query.items():
        if key == "$or":
            if not any(matches(document, child) for child in condition):
                return False
            continue
        if key == "$and":
            if not all(matches(document, child) for child in condition):
                return False
            continue
        if not _compare(document.get(key), condition):
            return False
    return True


class MemoryCollection:
    def __init__(self, name: str):
        self.name = name
        self.documents: list[dict] = []
        self.unique_fields: set[str] = set()

    def create_index(self, spec, unique: bool = False, sparse: bool = False, **kwargs):
        if unique and spec:
            self.unique_fields.add(spec[0][0])
        return None

    def _check_unique(self, document: dict, ignore_id=None):
        for field in self.unique_fields:
            value = document.get(field)
            if value is None:
                continue
            for item in self.documents:
                if ignore_id is not None and item.get("_id") == ignore_id:
                    continue
                if item.get(field) == value:
                    raise DuplicateKeyError(f"Duplicate value for {field}")

    def insert_one(self, document: dict):
        item = copy.deepcopy(document)
        item.setdefault("_id", ObjectId())
        self._check_unique(item)
        self.documents.append(item)
        document["_id"] = item["_id"]
        return InsertOneResult(item["_id"])

    def insert_many(self, documents: list[dict]):
        ids = []
        for document in documents:
            ids.append(self.insert_one(document).inserted_id)
        return type("InsertManyResult", (), {"inserted_ids": ids})()

    def find_one(self, query: dict | None = None):
        for document in self.documents:
            if matches(document, query):
                return copy.deepcopy(document)
        return None

    def find(self, query: dict | None = None):
        return MemoryCursor(document for document in self.documents if matches(document, query))

    def count_documents(self, query: dict | None = None):
        return sum(1 for document in self.documents if matches(document, query))

    def distinct(self, field: str):
        values = []
        for document in self.documents:
            value = document.get(field)
            if value not in values:
                values.append(value)
        return values

    def update_one(self, query: dict, update: dict):
        for index, document in enumerate(self.documents):
            if not matches(document, query):
                continue
            updated = copy.deepcopy(document)
            updated.update(update.get("$set", {}))
            self._check_unique(updated, ignore_id=document.get("_id"))
            self.documents[index] = updated
            return UpdateResult(1, 1)
        return UpdateResult(0, 0)

    def update_many(self, query: dict, update: dict):
        matched = 0
        for index, document in enumerate(self.documents):
            if matches(document, query):
                updated = copy.deepcopy(document)
                updated.update(update.get("$set", {}))
                self.documents[index] = updated
                matched += 1
        return UpdateResult(matched, matched)

    def delete_one(self, query: dict):
        for index, document in enumerate(self.documents):
            if matches(document, query):
                self.documents.pop(index)
                return type("DeleteResult", (), {"deleted_count": 1})()
        return type("DeleteResult", (), {"deleted_count": 0})()

    def delete_many(self, query: dict):
        kept = []
        deleted = 0
        for document in self.documents:
            if matches(document, query):
                deleted += 1
            else:
                kept.append(document)
        self.documents = kept
        return type("DeleteResult", (), {"deleted_count": deleted})()

    def aggregate(self, pipeline: list[dict]):
        if pipeline and "$group" in pipeline[0]:
            group = pipeline[0]["$group"]
            value_spec = group.get("value", {})
            avg_field = value_spec.get("$avg", "").removeprefix("$")
            values = [item.get(avg_field) for item in self.documents if isinstance(item.get(avg_field), (int, float))]
            return [{"_id": None, "value": sum(values) / len(values)}] if values else []
        return []


class MemoryDatabase:
    def __init__(self):
        self._collections: dict[str, MemoryCollection] = {}

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._collections:
            self._collections[name] = MemoryCollection(name)
        return self._collections[name]
