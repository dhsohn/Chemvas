from __future__ import annotations

import pytest
from chemvas.features.document_composition import compose_document_state, service


def _composition() -> dict[str, object]:
    return {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [{"id": 0, "element": "O", "x": 0.0, "y": 0.0}],
        "bonds": [],
    }


def test_composition_uses_live_canvas_defaults() -> None:
    state = compose_document_state(_composition())

    settings = state["settings"]
    assert settings["bond_length_px"] == 20.0
    assert settings["arrow_line_width"] == 1.5
    assert settings["arrow_head_scale"] == 0.3
    assert settings["orbital_phase_enabled"] is False
    assert settings["text_font_family"] == "Arial"
    assert settings["text_font_size"] == 12
    assert settings["text_font_weight"] == 400
    assert settings["text_italic"] is False
    assert settings["sheet_size"] == "A4"
    assert settings["sheet_orientation"] == "landscape"


def test_composition_rejects_canvas_font_size_above_supported_limit() -> None:
    composition = _composition()
    composition["settings"] = {"text_font_size": 97}

    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        compose_document_state(composition)


@pytest.mark.parametrize("bond_length_px", [None, [20.0], {"px": 20.0}, "20"])
def test_composition_rejects_non_numeric_settings_value(
    bond_length_px: object,
) -> None:
    composition = _composition()
    composition["settings"] = {"bond_length_px": bond_length_px}

    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        compose_document_state(composition)


def test_composition_fails_if_electronic_marks_do_not_match_annotations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition = _composition()
    atoms = composition["atoms"]
    assert isinstance(atoms, list)
    atoms[0]["formal_charge"] = -1
    monkeypatch.setattr(service, "annotation_mark_kinds", lambda _annotation: ())

    with pytest.raises(ValueError, match="charge/radical"):
        compose_document_state(composition)
