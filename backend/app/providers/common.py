from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from threading import Lock
from time import monotonic
from typing import Any, Dict, List, Optional


class ProviderError(RuntimeError):
    """A safe, user-facing provider failure."""


@dataclass
class ProviderSearchResult:
    items: List[dict]
    provider: str
    attribution: str
    cached: bool = False
    warnings: List[str] = field(default_factory=list)
    endpoint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TTLCache:
    def __init__(self) -> None:
        self._items: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        now = monotonic()
        with self._lock:
            record = self._items.get(key)
            if not record:
                return None
            expires_at, value = record
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            result = deepcopy(value)
            result["cached"] = True
            return result

    def set(self, key: str, value: Dict[str, Any], ttl_seconds: int) -> None:
        with self._lock:
            self._items[key] = (monotonic() + max(1, ttl_seconds), deepcopy(value))


search_cache = TTLCache()
