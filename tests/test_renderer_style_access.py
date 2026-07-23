from types import SimpleNamespace
from unittest import mock

from chemvas.ui.renderer_style_access import (
    atom_color_for,
    atom_font_for,
    atom_label_offset_px_for,
    bold_bond_pen_for,
    bold_bond_width_for,
    bond_color_for,
    bond_length_pt_for,
    bond_length_px_for,
    bond_line_width_for,
    bond_pen_for,
    bond_spacing_px_for,
    dotted_bond_pen_for,
    font_family_for,
    font_size_pt_for,
    hash_spacing_px_for,
    orbital_alpha_for,
    orbital_negative_color_for,
    orbital_positive_color_for,
    renderer_bold_bond_width_for,
    renderer_bond_line_width_for,
    renderer_bond_spacing_for,
    renderer_for,
    renderer_hash_spacing_for,
    renderer_style_for,
    ring_fill_brush_for,
    set_bond_length_for,
)


def test_renderer_style_accessors_return_renderer_style_values() -> None:
    style = SimpleNamespace(
        atom_color="#111111",
        atom_label_offset_px=2.5,
        bold_bond_width=4.0,
        bond_color="#222222",
        bond_length_pt=18.0,
        bond_length_px=24.0,
        bond_line_width=1.5,
        bond_spacing_px=3.0,
        font_family="Arial",
        font_size_pt=12,
        hash_spacing_px=5.0,
        orbital_alpha=0.45,
        orbital_negative_color="#333333",
        orbital_positive_color="#444444",
    )
    renderer = SimpleNamespace(
        style=style,
        bond_pen=mock.Mock(return_value="bond-pen"),
        bold_bond_pen=mock.Mock(return_value="bold-pen"),
        dotted_bond_pen=mock.Mock(return_value="dotted-pen"),
        atom_font=mock.Mock(return_value="atom-font"),
        ring_fill_brush=mock.Mock(return_value="ring-brush"),
        bond_line_width=mock.Mock(return_value=1.25),
        bold_bond_width=mock.Mock(return_value=4.5),
        bond_spacing=mock.Mock(return_value=2.25),
        hash_spacing=mock.Mock(return_value=3.25),
        set_bond_length=mock.Mock(),
    )
    canvas = SimpleNamespace(renderer=renderer)

    assert renderer_for(canvas) is renderer
    assert renderer_style_for(canvas) is style
    assert atom_color_for(canvas) == "#111111"
    assert atom_font_for(canvas) == "atom-font"
    assert atom_label_offset_px_for(canvas) == 2.5
    assert bold_bond_pen_for(canvas) == "bold-pen"
    assert bold_bond_width_for(canvas) == 4.0
    assert bond_color_for(canvas) == "#222222"
    assert bond_length_pt_for(canvas) == 18.0
    assert bond_length_px_for(canvas) == 24.0
    assert bond_line_width_for(canvas) == 1.5
    assert bond_pen_for(canvas) == "bond-pen"
    assert bond_spacing_px_for(canvas) == 3.0
    assert dotted_bond_pen_for(canvas) == "dotted-pen"
    assert font_family_for(canvas) == "Arial"
    assert font_size_pt_for(canvas) == 12
    assert hash_spacing_px_for(canvas) == 5.0
    assert orbital_alpha_for(canvas) == 0.45
    assert orbital_negative_color_for(canvas) == "#333333"
    assert orbital_positive_color_for(canvas) == "#444444"
    assert renderer_bold_bond_width_for(canvas) == 4.5
    assert renderer_bond_line_width_for(canvas) == 1.25
    assert renderer_bond_spacing_for(canvas) == 2.25
    assert renderer_hash_spacing_for(canvas) == 3.25
    assert ring_fill_brush_for(canvas) == "ring-brush"

    set_bond_length_for(canvas, 32.0)

    renderer.set_bond_length.assert_called_once_with(32.0)
