from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import Decimal


def strict_json_loads(source: str | bytes | bytearray) -> object:
    """Decode standards-compliant JSON without silently replacing duplicate keys."""
    return json.loads(
        source,
        parse_float=_parse_json_number,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_unique_object,
    )


def _parse_json_number(text: str) -> Decimal:
    try:
        return Decimal(text)
    except ArithmeticError as exc:
        # Decimal answers an exponent past MAX_EMAX with InvalidOperation, an
        # ArithmeticError. Readers guard against ValueError and its neighbours,
        # so a number the parser cannot represent has to leave by the same door
        # a duplicate key or a NaN does rather than as a traceback. Only the
        # conversion is wrapped: an arithmetic error from anywhere else in the
        # parse would be a bug, and must not be relabelled malformed input.
        raise ValueError("JSON number is out of range") from exc


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
