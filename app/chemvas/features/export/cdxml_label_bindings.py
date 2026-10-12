"""Strict sidecar of explicit CDXML atom-label meanings (Qt-free).

A ``.chemvas`` document stores a drawn label such as ``Ar`` or ``H\u1d43`` only
as text, so it cannot say whether ``Ar`` is argon or an aryl group. A caller
who knows the meaning states it in a separate JSON sidecar that is bound to
the exact bytes of one source document:

    {
      "format": "chemvas-cdxml-label-bindings",
      "version": 1,
      "source_sha256": "<SHA-256 of the exact .chemvas bytes>",
      "bindings": [
        {"atom_id": 1, "expected_label": "Ar", "meaning": "generic_aryl"}
      ]
    }

Version 2 adds ``documentary_contacts`` and the ``aryl_label`` binding meaning;
see ADR 0038.

This module only checks the sidecar's own shape and its source binding. It
never infers a meaning, never edits the document and never decides chemistry:
the CDXML exporter still accepts or refuses each typed meaning, and the figure
export service checks each atom id and exact label against the document that
is actually exported.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.domain.json_io import strict_json_loads

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

CDXML_LABEL_BINDINGS_FORMAT = "chemvas-cdxml-label-bindings"
CDXML_LABEL_BINDINGS_VERSION = 1
CDXML_LABEL_BINDINGS_VERSION_V2 = 2
MAX_CDXML_LABEL_BINDINGS_BYTES = 1024 * 1024
MAX_CDXML_LABEL_BINDINGS = 10_000
MAX_CDXML_DOCUMENTARY_CONTACTS = 10_000

# XML 1.0 metadata must stay valid without importing the Qt exporter.
_XML_ILLEGAL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _validate_metadata_xml_text(value: str, where: str) -> None:
    if _XML_ILLEGAL_RE.search(value):
        raise ValueError(f"{where}: text contains characters illegal in XML 1.0")


# Each meaning names the one extra field it needs. The exporter's
# CdxmlLabelBinding accepts exactly these meanings and fields and re-checks
# them; this table only lets the sidecar refuse an unknown key early.
CDXML_LABEL_BINDING_MEANINGS: Mapping[str, tuple[str, ...]] = {
    "element": ("element",),
    "generic_aryl": (),
    "aryl_fragment": ("fragment",),
}

_V2_BINDING_MEANINGS: Mapping[str, tuple[str, ...]] = {
    **CDXML_LABEL_BINDING_MEANINGS,
    "aryl_label": ("author_note",),
}

_FORMAT = CDXML_LABEL_BINDINGS_FORMAT
_VERSION = CDXML_LABEL_BINDINGS_VERSION
_TOP_LEVEL_KEYS_V1 = frozenset({"format", "version", "source_sha256", "bindings"})
_TOP_LEVEL_KEYS_V2 = frozenset(
    {"format", "version", "source_sha256", "bindings", "documentary_contacts"}
)
_COMMON_BINDING_KEYS = ("atom_id", "expected_label", "meaning")
_CONTACT_KEYS = frozenset(
    {
        "bond_id",
        "a",
        "b",
        "native_order",
        "native_style",
        "classification",
    }
)
_CONTACT_OPTIONAL_KEYS = frozenset({"contact_id"})
_TS_CONTACT_CLASS = "ts_contact"
_NATIVE_DOCUMENTARY_STYLE = "dotted"
_NATIVE_DOCUMENTARY_ORDER = 1
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class CdxmlDocumentaryContact:
    """One explicit documentary permission for one native dotted contact."""

    bond_id: int
    a: int
    b: int
    native_order: int
    native_style: str
    classification: str
    contact_id: str | None = None

    def report(self) -> dict[str, object]:
        entry: dict[str, object] = {
            "bond_id": self.bond_id,
            "a": self.a,
            "b": self.b,
            "native_order": self.native_order,
            "native_style": self.native_style,
            "classification": self.classification,
        }
        if self.contact_id is not None:
            entry["contact_id"] = self.contact_id
        return entry


@dataclass(frozen=True)
class CdxmlLabelBindingEntry:
    """One explicit meaning for one atom label, exactly as the sidecar states it."""

    atom_id: int
    expected_label: str
    meaning: str
    element: str | None = None
    fragment: str | None = None
    author_note: str | None = None

    def report(self) -> dict[str, object]:
        entry: dict[str, object] = {
            "atom_id": self.atom_id,
            "expected_label": self.expected_label,
            "meaning": self.meaning,
        }
        if self.meaning == "aryl_label":
            entry["author_note"] = self.author_note
        else:
            for field_name in CDXML_LABEL_BINDING_MEANINGS[self.meaning]:
                entry[field_name] = getattr(self, field_name)
        return entry


@dataclass(frozen=True)
class CdxmlLabelBindings:
    """A validated sidecar, already bound to one exact source document digest."""

    source_sha256: str
    sidecar_sha256: str
    entries: tuple[CdxmlLabelBindingEntry, ...]
    version: int = CDXML_LABEL_BINDINGS_VERSION
    documentary_contacts: tuple[CdxmlDocumentaryContact, ...] = ()

    def report(self) -> dict[str, object]:
        report: dict[str, object] = {
            "sidecar_sha256": self.sidecar_sha256,
            "source_sha256": self.source_sha256,
            "bindings": [entry.report() for entry in self.entries],
        }
        if self.version == CDXML_LABEL_BINDINGS_VERSION_V2:
            report["version"] = self.version
            report["documentary_contacts"] = [
                contact.report() for contact in self.documentary_contacts
            ]
        return report


def read_cdxml_label_bindings(
    path: Path, source_sha256: str | None
) -> CdxmlLabelBindings:
    """Read one bounded, strict sidecar against exact saved document bytes."""
    if source_sha256 is None:
        raise ValueError("label bindings: the source document digest is not available")
    with path.open("rb") as stream:
        raw = stream.read(MAX_CDXML_LABEL_BINDINGS_BYTES + 1)
    if len(raw) > MAX_CDXML_LABEL_BINDINGS_BYTES:
        raise ValueError(
            "label bindings sidecar exceeds the "
            f"{MAX_CDXML_LABEL_BINDINGS_BYTES}-byte limit"
        )
    try:
        payload = strict_json_loads(raw)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError(
            "label bindings sidecar is not strict JSON "
            "(duplicate keys, NaN/Infinity and trailing data are refused)"
        ) from exc
    return parse_cdxml_label_bindings(
        payload,
        sidecar_sha256=hashlib.sha256(raw).hexdigest(),
        source_sha256=source_sha256,
    )


def parse_cdxml_label_bindings(
    payload: object,
    *,
    sidecar_sha256: str,
    source_sha256: str,
) -> CdxmlLabelBindings:
    """Validate a strictly decoded sidecar against the exact source digest.

    ``payload`` must come from ``strict_json_loads`` (duplicate keys, NaN and
    trailing data are already refused there). ``source_sha256`` must be the
    digest of the same bytes the caller parses and exports, so a document
    changed after the sidecar was written is refused rather than re-read.
    """
    if not _is_sha256_hex(source_sha256):
        raise ValueError("label bindings: the source document digest is not available")
    if not _is_sha256_hex(sidecar_sha256):
        raise ValueError("label bindings: the sidecar digest is not available")
    if type(payload) is not dict:
        raise ValueError("label bindings: the sidecar must be a JSON object")
    sidecar_format = payload.get("format")
    if type(sidecar_format) is not str or sidecar_format != _FORMAT:
        raise ValueError(f"label bindings: format must be {_FORMAT!r}")
    version = payload.get("version")
    if type(version) is not int:
        raise ValueError(f"label bindings: version must be the integer {_VERSION}")
    if version == _VERSION:
        _check_keys(payload, required=_TOP_LEVEL_KEYS_V1, where="the sidecar")
        return _parse_v1(
            payload, sidecar_sha256=sidecar_sha256, source_sha256=source_sha256
        )
    if version == CDXML_LABEL_BINDINGS_VERSION_V2:
        _check_keys(payload, required=_TOP_LEVEL_KEYS_V2, where="the sidecar")
        return _parse_v2(
            payload, sidecar_sha256=sidecar_sha256, source_sha256=source_sha256
        )
    raise ValueError(f"label bindings: version must be the integer {_VERSION}")


def _parse_v1(
    payload: dict[str, object],
    *,
    sidecar_sha256: str,
    source_sha256: str,
) -> CdxmlLabelBindings:
    bound_sha256 = payload["source_sha256"]
    if type(bound_sha256) is not str or not _is_sha256_hex(bound_sha256):
        raise ValueError(
            "label bindings: source_sha256 must be 64 lowercase hexadecimal digits"
        )
    if bound_sha256 != source_sha256:
        raise ValueError(
            "label bindings: source_sha256 does not match the exact bytes of the "
            "input document; the sidecar was written for a different document"
        )
    raw_entries = payload["bindings"]
    if type(raw_entries) is not list or not raw_entries:
        raise ValueError("label bindings: bindings must be a non-empty JSON array")
    if len(raw_entries) > MAX_CDXML_LABEL_BINDINGS:
        raise ValueError(
            f"label bindings: more than {MAX_CDXML_LABEL_BINDINGS} bindings"
        )
    entries: list[CdxmlLabelBindingEntry] = []
    seen: set[int] = set()
    for index, raw_entry in enumerate(raw_entries):
        entry = _parse_entry(raw_entry, index, meanings=CDXML_LABEL_BINDING_MEANINGS)
        if entry.atom_id in seen:
            raise ValueError(
                f"label bindings: bindings[{index}] repeats atom_id {entry.atom_id}"
            )
        seen.add(entry.atom_id)
        entries.append(entry)
    return CdxmlLabelBindings(
        source_sha256=source_sha256,
        sidecar_sha256=sidecar_sha256,
        entries=tuple(entries),
    )


def _parse_v2(
    payload: dict[str, object],
    *,
    sidecar_sha256: str,
    source_sha256: str,
) -> CdxmlLabelBindings:
    bound_sha256 = payload["source_sha256"]
    if type(bound_sha256) is not str or not _is_sha256_hex(bound_sha256):
        raise ValueError(
            "label bindings: source_sha256 must be 64 lowercase hexadecimal digits"
        )
    if bound_sha256 != source_sha256:
        raise ValueError(
            "label bindings: source_sha256 does not match the exact bytes of the "
            "input document; the sidecar was written for a different document"
        )
    raw_entries = payload["bindings"]
    if type(raw_entries) is not list or not raw_entries:
        raise ValueError("label bindings: bindings must be a non-empty JSON array")
    if len(raw_entries) > MAX_CDXML_LABEL_BINDINGS:
        raise ValueError(
            f"label bindings: more than {MAX_CDXML_LABEL_BINDINGS} bindings"
        )
    entries: list[CdxmlLabelBindingEntry] = []
    seen_atoms: set[int] = set()
    for index, raw_entry in enumerate(raw_entries):
        entry = _parse_entry(raw_entry, index, meanings=_V2_BINDING_MEANINGS)
        if entry.meaning == "aryl_label" and entry.expected_label != "Ar":
            raise ValueError(
                f"label bindings: bindings[{index}].expected_label must be 'Ar' "
                f"for meaning 'aryl_label', got {entry.expected_label!r}"
            )
        if entry.atom_id in seen_atoms:
            raise ValueError(
                f"label bindings: bindings[{index}] repeats atom_id {entry.atom_id}"
            )
        seen_atoms.add(entry.atom_id)
        entries.append(entry)
    raw_contacts = payload["documentary_contacts"]
    if type(raw_contacts) is not list or not raw_contacts:
        raise ValueError(
            "label bindings: documentary_contacts must be a non-empty JSON array"
        )
    if len(raw_contacts) > MAX_CDXML_DOCUMENTARY_CONTACTS:
        raise ValueError(
            f"label bindings: more than {MAX_CDXML_DOCUMENTARY_CONTACTS} "
            "documentary contacts"
        )
    contacts: list[CdxmlDocumentaryContact] = []
    seen_bonds: set[int] = set()
    for index, raw_contact in enumerate(raw_contacts):
        contact = _parse_contact(raw_contact, index)
        if contact.bond_id in seen_bonds:
            raise ValueError(
                f"label bindings: documentary_contacts[{index}] repeats "
                f"bond_id {contact.bond_id}"
            )
        seen_bonds.add(contact.bond_id)
        contacts.append(contact)
    return CdxmlLabelBindings(
        source_sha256=source_sha256,
        sidecar_sha256=sidecar_sha256,
        entries=tuple(entries),
        version=CDXML_LABEL_BINDINGS_VERSION_V2,
        documentary_contacts=tuple(contacts),
    )


def _parse_entry(
    raw_entry: object,
    index: int,
    *,
    meanings: Mapping[str, tuple[str, ...]],
) -> CdxmlLabelBindingEntry:
    where = f"bindings[{index}]"
    if type(raw_entry) is not dict:
        raise ValueError(f"label bindings: {where} must be a JSON object")
    meaning = raw_entry.get("meaning")
    if type(meaning) is not str or meaning not in meanings:
        raise ValueError(
            f"label bindings: {where}.meaning must be one of "
            f"{sorted(meanings)}, got {meaning!r}"
        )
    meaning_fields = meanings[meaning]
    _check_keys(
        raw_entry,
        required=frozenset((*_COMMON_BINDING_KEYS, *meaning_fields)),
        where=f"{where} ({meaning})",
    )
    atom_id = raw_entry["atom_id"]
    if type(atom_id) is not int or atom_id < 0:
        raise ValueError(
            f"label bindings: {where}.atom_id must be a non-negative integer, "
            f"got {atom_id!r}"
        )
    expected_label = raw_entry["expected_label"]
    if type(expected_label) is not str or not expected_label:
        raise ValueError(
            f"label bindings: {where}.expected_label must be a non-empty string"
        )
    values: dict[str, str] = {}
    for field_name in meaning_fields:
        value = raw_entry[field_name]
        if type(value) is not str or not value:
            raise ValueError(
                f"label bindings: {where}.{field_name} must be a non-empty string"
            )
        if field_name == "author_note":
            _validate_metadata_xml_text(value, f"label bindings: {where}.{field_name}")
        values[field_name] = value
    return CdxmlLabelBindingEntry(
        atom_id=atom_id,
        expected_label=expected_label,
        meaning=meaning,
        element=values.get("element"),
        fragment=values.get("fragment"),
        author_note=values.get("author_note"),
    )


def _parse_contact(raw_contact: object, index: int) -> CdxmlDocumentaryContact:
    where = f"documentary_contacts[{index}]"
    if type(raw_contact) is not dict:
        raise ValueError(f"label bindings: {where} must be a JSON object")
    allowed = _CONTACT_KEYS | _CONTACT_OPTIONAL_KEYS
    unknown = sorted(set(raw_contact) - allowed)
    if unknown:
        raise ValueError(f"label bindings: {where} has unknown keys {unknown}")
    missing = sorted(_CONTACT_KEYS - set(raw_contact))
    if missing:
        raise ValueError(f"label bindings: {where} is missing keys {missing}")
    bond_id = raw_contact["bond_id"]
    if type(bond_id) is not int or bond_id < 0:
        raise ValueError(
            f"label bindings: {where}.bond_id must be a non-negative integer, "
            f"got {bond_id!r}"
        )
    a = raw_contact["a"]
    b = raw_contact["b"]
    if type(a) is not int or a < 0 or type(b) is not int or b < 0:
        raise ValueError(
            f"label bindings: {where}.a and .b must be non-negative integers"
        )
    if a == b:
        raise ValueError(f"label bindings: {where} must name distinct endpoints")
    native_order = raw_contact["native_order"]
    if type(native_order) is not int or native_order != 1:
        raise ValueError(f"label bindings: {where}.native_order must be the integer 1")
    native_style = raw_contact["native_style"]
    if type(native_style) is not str or native_style != "dotted":
        raise ValueError(
            f"label bindings: {where}.native_style must be 'dotted', "
            f"got {native_style!r}"
        )
    classification = raw_contact["classification"]
    if type(classification) is not str or classification != _TS_CONTACT_CLASS:
        raise ValueError(
            f"label bindings: {where}.classification must be "
            f"{_TS_CONTACT_CLASS!r}, got {classification!r}"
        )
    contact_id = raw_contact.get("contact_id")
    if contact_id is not None:
        if type(contact_id) is not str or not contact_id:
            raise ValueError(
                f"label bindings: {where}.contact_id must be a non-empty string"
            )
    if contact_id is not None:
        _validate_metadata_xml_text(contact_id, f"label bindings: {where}.contact_id")
    return CdxmlDocumentaryContact(
        bond_id=bond_id,
        a=a,
        b=b,
        native_order=native_order,
        native_style=native_style,
        classification=classification,
        contact_id=contact_id,
    )


def _check_keys(
    record: dict[str, object], *, required: frozenset[str], where: str
) -> None:
    unknown = sorted(set(record) - required)
    if unknown:
        raise ValueError(f"label bindings: {where} has unknown keys {unknown}")
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"label bindings: {where} is missing keys {missing}")


def _is_sha256_hex(value: object) -> bool:
    return type(value) is str and _SHA256_HEX.fullmatch(value) is not None


def _reject_non_int_field(where: str, field: str, value: object) -> int:
    if isinstance(value, bool) or type(value) is not int:
        raise ValueError(
            f"label bindings: {where}.{field} must be a non-negative integer, "
            f"got {value!r}"
        )
    if value < 0:
        raise ValueError(
            f"label bindings: {where}.{field} must be a non-negative integer, "
            f"got {value!r}"
        )
    return value


def authorize_documentary_contact_for_export(
    contact: object,
    *,
    where: str = "documentary contact",
) -> CdxmlDocumentaryContact:
    """Runtime authorization for one contact record at the export boundary.

    Frozen dataclass instances and parser provenance are not trusted: callers
    may construct ``CdxmlDocumentaryContact`` directly. The exporter must call
    this before dereferencing any contact field against the live document.
    """
    if type(contact) is not CdxmlDocumentaryContact:
        raise ValueError(f"{where} must be a CdxmlDocumentaryContact instance")
    bond_id = _reject_non_int_field(where, "bond_id", contact.bond_id)
    a = _reject_non_int_field(where, "a", contact.a)
    b = _reject_non_int_field(where, "b", contact.b)
    if a == b:
        raise ValueError(f"{where} must name distinct endpoints")
    native_order = _reject_non_int_field(where, "native_order", contact.native_order)
    if native_order != _NATIVE_DOCUMENTARY_ORDER:
        raise ValueError(
            f"{where}.native_order must be the integer {_NATIVE_DOCUMENTARY_ORDER}"
        )
    native_style = contact.native_style
    if type(native_style) is not str or native_style != _NATIVE_DOCUMENTARY_STYLE:
        raise ValueError(
            f"{where}.native_style must be {_NATIVE_DOCUMENTARY_STYLE!r}, "
            f"got {native_style!r}"
        )
    classification = contact.classification
    if type(classification) is not str or classification != _TS_CONTACT_CLASS:
        raise ValueError(
            f"{where}.classification must be {_TS_CONTACT_CLASS!r}, "
            f"got {classification!r}"
        )
    contact_id = contact.contact_id
    if contact_id is not None and (type(contact_id) is not str or not contact_id):
        raise ValueError(f"{where}.contact_id must be a non-empty string")
    return CdxmlDocumentaryContact(
        bond_id=bond_id,
        a=a,
        b=b,
        native_order=native_order,
        native_style=native_style,
        classification=classification,
        contact_id=contact_id,
    )


__all__ = [
    "CDXML_LABEL_BINDINGS_FORMAT",
    "CDXML_LABEL_BINDINGS_VERSION",
    "CDXML_LABEL_BINDINGS_VERSION_V2",
    "CDXML_LABEL_BINDING_MEANINGS",
    "MAX_CDXML_DOCUMENTARY_CONTACTS",
    "MAX_CDXML_LABEL_BINDINGS",
    "MAX_CDXML_LABEL_BINDINGS_BYTES",
    "CdxmlDocumentaryContact",
    "CdxmlLabelBindingEntry",
    "CdxmlLabelBindings",
    "authorize_documentary_contact_for_export",
    "parse_cdxml_label_bindings",
    "read_cdxml_label_bindings",
]
