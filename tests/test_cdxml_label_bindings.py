"""Strict CDXML label-binding sidecar validation.

Qt-free and synthetic only: the bindings below are explicit test inputs. They
do not state the meaning of any real figure's ``Ar`` or ``H\u1d43`` label.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chemvas.domain.json_io import strict_json_loads
from chemvas.features.export import cdxml_label_bindings as sidecar_module
from chemvas.features.export.cdxml_label_bindings import (
    CDXML_LABEL_BINDINGS_FORMAT,
    CDXML_LABEL_BINDINGS_VERSION,
    CdxmlLabelBindingEntry,
    CdxmlLabelBindings,
    parse_cdxml_label_bindings,
)

SOURCE_SHA256 = hashlib.sha256(b"synthetic source document").hexdigest()
OTHER_SHA256 = hashlib.sha256(b"another synthetic document").hexdigest()
H_A = "H\u1d43"
_DROP = object()


def _entry(
    atom_id: object = 1,
    label: object = "Ar",
    meaning: object = "generic_aryl",
    **fields: object,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "atom_id": atom_id,
        "expected_label": label,
        "meaning": meaning,
        **fields,
    }
    return {key: value for key, value in entry.items() if value is not _DROP}


def _payload(*bindings: dict[str, object], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "format": CDXML_LABEL_BINDINGS_FORMAT,
        "version": CDXML_LABEL_BINDINGS_VERSION,
        "source_sha256": SOURCE_SHA256,
        "bindings": list(bindings) or [_entry()],
    }
    payload.update(overrides)
    return payload


def _parse_text(text: str, *, source_sha256: str = SOURCE_SHA256) -> CdxmlLabelBindings:
    raw = text.encode("utf-8")
    return parse_cdxml_label_bindings(
        strict_json_loads(raw),
        sidecar_sha256=hashlib.sha256(raw).hexdigest(),
        source_sha256=source_sha256,
    )


def _parse(payload: object) -> CdxmlLabelBindings:
    return _parse_text(json.dumps(payload, ensure_ascii=False))


def test_each_meaning_is_kept_exactly_and_in_order() -> None:
    entries = [
        _entry(4, "Ar", "aryl_fragment", fragment="Ph"),
        _entry(1, "Ar", "generic_aryl"),
        _entry(2, H_A, "element", element="H"),
        _entry(3, "Ar", "element", element="Ar"),
    ]
    text = json.dumps(_payload(*entries), ensure_ascii=False)

    parsed = _parse_text(text)

    assert parsed.source_sha256 == SOURCE_SHA256
    assert parsed.sidecar_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert parsed.entries == (
        CdxmlLabelBindingEntry(4, "Ar", "aryl_fragment", fragment="Ph"),
        CdxmlLabelBindingEntry(1, "Ar", "generic_aryl"),
        CdxmlLabelBindingEntry(2, H_A, "element", element="H"),
        CdxmlLabelBindingEntry(3, "Ar", "element", element="Ar"),
    )
    # The identifier label is not normalized (NFKC would turn it into "Ha").
    assert [ord(char) for char in parsed.entries[2].expected_label] == [0x48, 0x1D43]
    assert parsed.report() == {
        "sidecar_sha256": parsed.sidecar_sha256,
        "source_sha256": SOURCE_SHA256,
        "bindings": entries,
    }


@pytest.mark.parametrize(
    "text",
    [
        '{"format": "chemvas-cdxml-label-bindings", "format": "x"}',
        '{"bindings": [{"atom_id": 1, "atom_id": 2}]}',
        '{"version": NaN}',
        '{"version": 1} {"version": 1}',
    ],
    ids=["duplicate-top-level-key", "duplicate-binding-key", "nan", "trailing-data"],
)
def test_non_strict_json_never_reaches_the_validator(text: str) -> None:
    with pytest.raises(ValueError):
        strict_json_loads(text.encode("utf-8"))


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ([], "must be a JSON object"),
        (_payload(extra=True), r"unknown keys \['extra'\]"),
        ({"format": CDXML_LABEL_BINDINGS_FORMAT, "version": 1}, "missing keys"),
        (_payload(format="chemvas-label-bindings"), "format must be"),
        (_payload(version=2), r"missing keys \['documentary_contacts'\]"),
        (_payload(version="1"), "version must be the integer 1"),
        (_payload(version=True), "version must be the integer 1"),
        (_payload(source_sha256=SOURCE_SHA256.upper()), "64 lowercase hexadecimal"),
        (_payload(source_sha256=SOURCE_SHA256[:63]), "64 lowercase hexadecimal"),
        (_payload(source_sha256=OTHER_SHA256), "different document"),
        (_payload(bindings=[]), "non-empty JSON array"),
        (_payload(bindings={"1": "generic_aryl"}), "non-empty JSON array"),
        (_payload(bindings=["generic_aryl"]), r"bindings\[0\] must be a JSON object"),
        (_payload(_entry(meaning="argon")), "meaning must be one of"),
        (_payload(_entry(meaning="isotope")), "meaning must be one of"),
        (_payload(_entry(meaning=_DROP)), "meaning must be one of"),
        (_payload(_entry(meaning=["generic_aryl"])), "meaning must be one of"),
        (_payload(_entry(color="#ff0000")), r"unknown keys \['color'\]"),
        (_payload(_entry(fragment="Ph")), r"unknown keys \['fragment'\]"),
        (_payload(_entry(element="Ar")), r"unknown keys \['element'\]"),
        (_payload(_entry(meaning="element")), r"missing keys \['element'\]"),
        (_payload(_entry(meaning="aryl_fragment")), r"missing keys \['fragment'\]"),
        (_payload(_entry(label=_DROP)), r"missing keys \['expected_label'\]"),
        (_payload(_entry(atom_id="1")), "atom_id must be a non-negative integer"),
        (_payload(_entry(atom_id=1.0)), "atom_id must be a non-negative integer"),
        (_payload(_entry(atom_id=True)), "atom_id must be a non-negative integer"),
        (_payload(_entry(atom_id=-1)), "atom_id must be a non-negative integer"),
        (_payload(_entry(label=1)), "expected_label must be a non-empty"),
        (_payload(_entry(label="")), "expected_label must be a non-empty"),
        (
            _payload(_entry(meaning="element", element=18)),
            "element must be a non-empty",
        ),
        (
            _payload(_entry(meaning="aryl_fragment", fragment=["Ph"])),
            "fragment must be a non-empty",
        ),
        (
            _payload(_entry(), _entry(meaning="element", element="Ar")),
            "repeats atom_id 1",
        ),
    ],
)
def test_malformed_sidecars_are_refused(payload: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _parse(payload)


def test_binding_count_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sidecar_module, "MAX_CDXML_LABEL_BINDINGS", 2)

    with pytest.raises(ValueError, match="more than 2 bindings"):
        _parse(_payload(*(_entry(atom_id=index) for index in range(3))))


@pytest.mark.parametrize("digest", [None, "", "0" * 63, "G" * 64])
def test_caller_must_supply_exact_digests(digest: object) -> None:
    payload = strict_json_loads(json.dumps(_payload()))
    with pytest.raises(ValueError, match="source document digest"):
        parse_cdxml_label_bindings(
            payload, sidecar_sha256="0" * 64, source_sha256=digest
        )
    with pytest.raises(ValueError, match="sidecar digest"):
        parse_cdxml_label_bindings(
            payload, sidecar_sha256=digest, source_sha256=SOURCE_SHA256
        )


def test_module_import_is_qt_and_rdkit_free() -> None:
    env = os.environ.copy()
    app_root = Path(__file__).resolve().parents[1] / "app"
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(app_root), env.get("PYTHONPATH")) if value
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import chemvas.features.export.cdxml_label_bindings; "
                "assert not any(name == 'PyQt6' or name.startswith('PyQt6.') "
                "for name in sys.modules); "
                "assert not any(name == 'rdkit' or name.startswith('rdkit.') "
                "for name in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("field", ["author_note", "contact_id"])
@pytest.mark.parametrize("illegal", ["\x00", "\x0b", "\ufffe", "\uffff", "\ud800"])
def test_v2_metadata_illegal_xml_refused(field, illegal) -> None:
    payload = _payload(
        _entry(
            2,
            "Ar",
            "aryl_label",
            author_note=illegal if field == "author_note" else "note",
        ),
        version=2,
        documentary_contacts=[
            dict(
                bond_id=0,
                a=1,
                b=2,
                native_order=1,
                native_style="dotted",
                classification="ts_contact",
                contact_id=illegal if field == "contact_id" else "id",
            )
        ],
    )
    with pytest.raises(ValueError, match="illegal in XML 1.0"):
        _parse_text(json.dumps(payload, ensure_ascii=True))


def test_v2_valid_metadata_exact_preservation() -> None:
    value = ' \t\n\r한글 α 😀 & < > " '
    payload = _payload(
        _entry(2, "Ar", "aryl_label", author_note=value),
        version=2,
        documentary_contacts=[
            dict(
                bond_id=0,
                a=1,
                b=2,
                native_order=1,
                native_style="dotted",
                classification="ts_contact",
                contact_id=value,
            )
        ],
    )
    parsed = _parse(payload)
    assert parsed.entries[0].author_note == value
    assert parsed.documentary_contacts[0].contact_id == value
