"""Which native CDXML record edits leave stored stereo descriptors valid.

ChemDraw stores computed stereo results in the document: node ``AS`` (atom CIP
descriptor) and bond ``BS`` (bond CIP descriptor), plus ``CIP`` copies on both.
Chemvas never recomputes them. CIP ranking explores the whole connected
structure, so any change to constitution or to the drawn configuration can
change a descriptor anywhere in the fragment. Only the presentation fields
below cannot, and a record change confined to them keeps every descriptor.
Fields not listed here invalidate, so a newly added record field stays
conservative until it is classified.

``BondOrdering`` and ``Geometry`` describe one node's own coordination and are
handled by the writer on the nodes whose bonds or label change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

ATOM_STEREO_DESCRIPTORS = ("AS", "CIP")
BOND_STEREO_DESCRIPTORS = ("BS", "CIP")

# Colour is ink; ``explicit_label`` only shows or hides a carbon's symbol.
_ATOM_PRESENTATION_FIELDS = frozenset({"color", "explicit_label"})
_BOND_PRESENTATION_FIELDS = frozenset({"color"})
# Native ``DoublePosition`` only chooses the side the second line is drawn on.
DOUBLE_POSITION_STYLES = frozenset({"double", "double_center", "double_outer"})


def _changed_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> set[str]:
    return {
        key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
    }


def atom_edit_keeps_stereo(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """True when an atom record changed only in presentation fields."""
    return _changed_fields(before, after) <= _ATOM_PRESENTATION_FIELDS


def bond_edit_keeps_stereo(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """True when a bond record changed only in presentation fields.

    A style change between double-bond line positions is presentation as long
    as the order and the ``a``/``b`` direction stay the same.
    """
    changed = _changed_fields(before, after) - _BOND_PRESENTATION_FIELDS
    if "style" in changed and {before.get("style"), after.get("style")} <= (
        DOUBLE_POSITION_STYLES
    ):
        changed.discard("style")
    return not changed
