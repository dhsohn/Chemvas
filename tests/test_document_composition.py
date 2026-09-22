from __future__ import annotations

import pytest

from chemvas.domain.document import MAX_ARROW_LABEL_CHARS
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


@pytest.mark.parametrize("element", [" N", "N ", "\tN"])
def test_composition_normalizes_padded_element_labels(element) -> None:
    composition = _composition()
    composition["atoms"][0]["element"] = element

    assert compose_document_state(composition)["model"]["atoms"][0]["element"] == "N"


@pytest.mark.parametrize("kind", ["arrow", "equilibrium", "line", "arc_90_left"])
def test_composition_rejects_control_on_non_curved_arrows(kind) -> None:
    composition = _composition()
    composition["arrows"] = [
        {"kind": kind, "start": [0, 0], "end": [20, 0], "control": [10, 10]}
    ]

    with pytest.raises(ValueError, match="arrow 0 control.*curved"):
        compose_document_state(composition)


def test_composition_rejects_canvas_font_size_above_supported_limit() -> None:
    composition = _composition()
    composition["settings"] = {"text_font_size": 97}

    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        compose_document_state(composition)


@pytest.mark.parametrize(
    "bond_length_px",
    [
        None,
        [20.0],
        {"px": 20.0},
        "20",
        True,
        pytest.param(10**400, id="int-beyond-float-range"),
    ],
)
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


@pytest.mark.parametrize(
    "labels",
    [
        None,
        [],
        {},
        {"left": "condition"},
        {"above": ""},
        {"below": "  "},
        {"above": 1},
        {"above": "x" * (MAX_ARROW_LABEL_CHARS + 1)},
    ],
)
def test_composition_identifies_invalid_arrow_labels(labels: object) -> None:
    composition = _composition()
    composition["arrows"] = [
        {"kind": "arrow", "start": [0.0, 0.0], "end": [20.0, 0.0]},
        {"kind": "arrow", "start": [40.0, 0.0], "end": [60.0, 0.0], "labels": labels},
    ]

    with pytest.raises(ValueError, match=r"arrow 1 labels"):
        compose_document_state(composition)


def test_composition_preserves_one_sided_arrow_label() -> None:
    composition = _composition()
    composition["arrows"] = [
        {
            "kind": "arrow",
            "start": [0.0, 0.0],
            "end": [20.0, 0.0],
            "labels": {"above": "THF"},
        },
    ]

    state = compose_document_state(composition)
    assert state["arrows"][0]["labels"] == {"above": "THF"}


@pytest.mark.parametrize(
    "collection,item",
    [
        ("notes", {"text": "rotated", "x": 0, "y": 0, "rotation": 35}),
        (
            "shapes",
            {
                "shape_kind": "rect",
                "left": 0,
                "top": 0,
                "right": 10,
                "bottom": 10,
                "stroke_style": "solid",
                "z": 4,
            },
        ),
        ("images", {"source": "synthetic.png", "x": 0, "y": 0, "z": -12}),
    ],
)
def test_transform_composition_requires_v2_preserving_v1(collection, item):
    from io import BytesIO

    from PIL import Image

    image = BytesIO()
    Image.new("RGB", (2, 2), "white").save(image, format="PNG")
    request = {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [],
        "bonds": [],
        collection: [item],
    }
    with pytest.raises(ValueError, match="requires composition version 2"):
        compose_document_state(request, image_source_reader=lambda _: image.getvalue())
    request["version"] = 2
    state = compose_document_state(
        request, image_source_reader=lambda _: image.getvalue()
    )
    field = "rotation" if collection == "notes" else "z"
    assert state[collection][0][field] == item[field]
    request["version"] = 1
    request[collection] = [{k: v for k, v in item.items() if k != field}]
    legacy = compose_document_state(
        request, image_source_reader=lambda _: image.getvalue()
    )
    assert field not in legacy[collection][0]
