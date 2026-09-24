"""Value predicates and normalizers shared by document serialization and validation."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypeGuard, cast

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from .model import MoleculeModel

POINT_COORDINATE_TOLERANCE = Decimal("0.000001")


MAX_SAFE_NUMBER = float(2**53 - 1)


MAX_SAFE_NUMBER_DECIMAL = Decimal(2**53 - 1)


def _bond_pair_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def model_bond_pairs(model: MoleculeModel) -> set[tuple[int, int]]:
    """Normalized (low, high) atom-id pairs of the model's live bonds."""
    return {
        _bond_pair_key(bond.a, bond.b)
        for bond in model.bonds
        if bond is not None and bond.a != bond.b
    }


def ring_atom_ids_form_cycle(
    ring_atom_ids: Collection[int],
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
) -> bool:
    """Public wrapper of the ring-cycle rule used by document validation.

    Snapshot code uses this to drop ring fills that no longer describe a real
    bonded cycle, so a stale ring can never make saving fail validation.
    """
    return _is_atom_id_cycle(list(ring_atom_ids), atom_ids, bond_pairs)


def _validated_id(value: object) -> int:
    if type(value) is int:
        parsed = value
    elif isinstance(value, str) and value.isdecimal():
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError("Invalid Chemvas file.") from exc
    else:
        raise ValueError("Invalid Chemvas file.")
    if parsed < 0:
        raise ValueError("Invalid Chemvas file.")
    return parsed


def _validated_clipboard_id(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Invalid clipboard payload.")
    return value


def _is_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _is_number(value: object) -> bool:
    if type(value) not in (int, float, Decimal):
        return False
    try:
        if type(value) is Decimal:
            decimal_value = value
            if (
                not decimal_value.is_finite()
                or abs(decimal_value) > MAX_SAFE_NUMBER_DECIMAL
            ):
                return False
            return Decimal(str(float(decimal_value))) == decimal_value
        float_value = float(cast("Any", value))
        if not math.isfinite(float_value) or abs(float_value) > MAX_SAFE_NUMBER:
            return False
        if type(value) is int:
            return int(float_value) == value
        return True
    except ArithmeticError:
        # float() on an oversized int raises OverflowError, while the abs()
        # in the range check above raises decimal.Overflow -- a sibling of that
        # under ArithmeticError rather than a subclass, so naming only
        # OverflowError left the Decimal path uncovered. Either way this is a
        # value the document cannot carry, which is exactly what False says.
        return False


def normalize_json_numbers(value: object) -> object:
    if type(value) is Decimal:
        return float(value)
    if isinstance(value, list):
        normalized_list = [normalize_json_numbers(item) for item in value]
        if all(
            normalized is original
            for normalized, original in zip(normalized_list, value, strict=True)
        ):
            return value
        return normalized_list
    if isinstance(value, tuple):
        normalized_tuple = tuple(normalize_json_numbers(item) for item in value)
        if all(
            normalized is original
            for normalized, original in zip(normalized_tuple, value, strict=True)
        ):
            return value
        return normalized_tuple
    if isinstance(value, dict):
        normalized_dict = {
            key: normalize_json_numbers(item) for key, item in value.items()
        }
        if all(normalized_dict[key] is item for key, item in value.items()):
            return value
        return normalized_dict
    return value


def _is_point(value: object) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    x, y = value
    return _is_number(x) and _is_number(y)


def _is_point_3d(value: object) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return False
    x, y, z = value
    return _is_number(x) and _is_number(y) and _is_number(z)


def _is_atom_id_cycle(
    value: object,
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
    *,
    clipboard: bool = False,
) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    try:
        validate_id = _validated_clipboard_id if clipboard else _validated_id
        parsed_ids = [validate_id(atom_id) for atom_id in value]
    except ValueError:
        return False
    if len(parsed_ids) < 3 or len(set(parsed_ids)) != len(parsed_ids):
        return False
    if any(atom_id not in atom_ids for atom_id in parsed_ids):
        return False
    return all(
        _bond_pair_key(atom_id, parsed_ids[(index + 1) % len(parsed_ids)]) in bond_pairs
        for index, atom_id in enumerate(parsed_ids)
    )


def _ring_points_match_atom_positions(
    points: object,
    ring_atom_ids: object,
    atom_positions: Mapping[int, tuple[int | float | Decimal, int | float | Decimal]],
    *,
    clipboard: bool = False,
) -> bool:
    if not isinstance(points, (list, tuple)) or not isinstance(
        ring_atom_ids, (list, tuple)
    ):
        return False
    validate_id = _validated_clipboard_id if clipboard else _validated_id
    try:
        parsed_ids = [validate_id(atom_id) for atom_id in ring_atom_ids]
    except ValueError:
        return False
    if len(points) != len(parsed_ids):
        return False
    for point, atom_id in zip(points, parsed_ids, strict=True):
        if not _is_point(point):
            return False
        expected = atom_positions.get(atom_id)
        if expected is None:
            return False
        x, y = point
        if not _coordinate_matches(x, expected[0]):
            return False
        if not _coordinate_matches(y, expected[1]):
            return False
    return True


def _coordinate_matches(value: object, expected: int | float | Decimal) -> bool:
    if not _is_number(value):
        return False
    return (
        abs(Decimal(str(value)) - Decimal(str(expected))) <= POINT_COORDINATE_TOLERANCE
    )


def is_hex_color(value: object) -> bool:
    """Public form of the document hex-color rule (``#rgb`` / ``#rrggbb``)."""
    return _is_hex_color(value)


def is_document_number(value: object) -> bool:
    """Return whether ``value`` is a finite, JSON-safe Chemvas number."""
    return _is_number(value)


def _is_hex_color(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("#"):
        return False
    digits = value[1:]
    if len(digits) not in (3, 6):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in digits)


__all__ = [
    "MAX_SAFE_NUMBER",
    "MAX_SAFE_NUMBER_DECIMAL",
    "POINT_COORDINATE_TOLERANCE",
    "is_document_number",
    "is_hex_color",
    "model_bond_pairs",
    "normalize_json_numbers",
    "ring_atom_ids_form_cycle",
]
