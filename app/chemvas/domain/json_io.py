from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import Decimal


def strict_json_loads(source: str | bytes | bytearray) -> object:
    """Decode standards-compliant JSON without silently replacing duplicate keys."""
    return json.loads(
        source,
        parse_float=Decimal,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_unique_object,
    )


def _unique_object(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON number is not allowed: {value}")


__all__ = ["strict_json_loads"]
