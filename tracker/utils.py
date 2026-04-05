from __future__ import annotations

import hashlib
from typing import Iterable


def stable_hash(*parts: str) -> str:
    payload = "||".join(part or "" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def first_non_empty(values: Iterable[str | None], default: str = "") -> str:
    for value in values:
        if value:
            return value
    return default
