"""Typed CDXML atom-label meanings and the field each one carries (Qt-free).

This is the one statement of which meanings exist and which value fields each
needs. The label-bindings sidecar parser refuses keys outside it, the CDXML
exporter refuses bindings that contradict it, and the figure export service
hands the fields across between them. Whether a meaning fits a drawn label is
still the exporter's decision.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

# Every optional value field a label binding can carry.
LABEL_BINDING_FIELD_NAMES: Final[tuple[str, ...]] = (
    "element",
    "fragment",
    "author_note",
)

# Each meaning names the fields it needs; every other field must be absent.
LABEL_BINDING_MEANING_FIELDS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "element": ("element",),
        "generic_aryl": (),
        "aryl_fragment": ("fragment",),
        "aryl_label": ("author_note",),
    }
)

# Sidecar version 1 predates ``aryl_label`` (ADR 0038).
SIDECAR_V1_LABEL_MEANINGS: Final[frozenset[str]] = frozenset(
    {"element", "generic_aryl", "aryl_fragment"}
)

__all__ = [
    "LABEL_BINDING_FIELD_NAMES",
    "LABEL_BINDING_MEANING_FIELDS",
    "SIDECAR_V1_LABEL_MEANINGS",
]
