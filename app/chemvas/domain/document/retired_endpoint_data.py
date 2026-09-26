"""Opaque v2 endpoint archive; never interpreted as calculation input.

Remove only when the durable calculation-plan v2 reader is retired.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal

from chemvas.domain.json_io import strict_json_loads

NO_PRECOMPLEX_JSON = '{"kind":"none"}'


def canonicalize_precomplex_state(value: object) -> tuple[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("Invalid retired endpoint archive.")
    kind = value.get("kind")
    if kind == "none":
        if set(value) != {"kind"}:
            raise ValueError("Invalid empty endpoint archive.")
        return "none", NO_PRECOMPLEX_JSON
    if kind != "candidate_ensemble":
        raise ValueError("Unknown retired endpoint archive kind.")
    try:
        payload = json.dumps(
            _numbers(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError("Invalid retired endpoint archive JSON.") from exc
    return kind, payload


def _numbers(value: object) -> object:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, Mapping):
        return {str(key): _numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_numbers(item) for item in value]
    return value


def precomplex_state_from_json(payload_json: str) -> dict[str, object]:
    value = _numbers(strict_json_loads(payload_json))
    if not isinstance(value, dict):
        raise ValueError("Invalid retired endpoint archive.")
    return value
