"""CDXML export: editable ChemDraw-compatible XML from the scene model.

Reads the actual SceneRenderContext model and scene items to produce native
CDXML fragments, nodes, bonds, graphics and text.  Receives the shared
ExportPlan for uniform coordinate/font/stroke scaling.

Only constructs with a substantiated native CDXML mapping are emitted.
Everything else raises CdxmlUnsupportedObjectError before any file is written.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import TYPE_CHECKING

from chemvas.domain.atom_aliases import ATOM_ALIAS_DEFINITIONS
from chemvas.domain.document import (
    Arrow,
    Bond,
    MoleculeModel,
    Shape,
    connected_atom_components,
)
from chemvas.features.rendering import arrow_path_commands
from chemvas.ui.annotations.shape_geometry import shape_outline, shape_stroke_width
from chemvas.ui.export.export_scope import (
    EXPORT_EXCLUDED_KINDS,
    export_item_closure,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PyQt6.QtGui import (
        QFont,
        QTextBlock,
        QTextDocument,
        QTextFragment,
        QTextLayout,
        QTransform,
    )
    from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem

    from chemvas.domain.document.groups import SceneGroup
    from chemvas.features.export import ExportPlan
    from chemvas.ui.scene.scene_render_context import SceneRenderContext

GroupsProvider = Mapping[int, "SceneGroup"]


# ── Element-to-atomic-number mapping (pure elements only) ──────────────

_ELEMENT_TO_Z: dict[str, int] = {}
_z = 0
for _sym in (
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni "
    "Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe "
    "Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg "
    "Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg "
    "Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og"
).split():
    _z += 1
    _ELEMENT_TO_Z[_sym] = _z
del _z, _sym


# ── Supported bond styles → CDXML Display ─────────────────────────────

_BOND_DISPLAY: dict[str, str] = {
    "single": "Solid",
    "double_center": "Solid",
    "triple": "Solid",
}

_BOND_ORDER_SUPPORT = frozenset({1, 2, 3})

_SUPPORTED_BOND_STYLES = frozenset(_BOND_DISPLAY)

# ── Supported arrow/line kinds ─────────────────────────────────────────

_SUPPORTED_LINE_KINDS = frozenset({"line"})
_SUPPORTED_ARROW_KINDS = frozenset({"arrow"})

# ── CDXML face bitmask ─────────────────────────────────────────────────

_FACE_BOLD = 1

# ── XML 1.0 illegal character pattern ─────────────────────────────────

_XML_ILLEGAL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


class CdxmlUnsupportedObjectError(ValueError):
    """An object or style cannot be faithfully serialized to CDXML."""

    def __init__(self, object_kind: str, object_id: str, reason: str) -> None:
        self.object_kind = object_kind
        self.object_id = object_id
        self.reason = reason
        super().__init__(
            f"CDXML export does not support {object_kind} {object_id}: "
            f"{reason}. Use SVG or PDF export instead."
        )


# ── ID allocator ───────────────────────────────────────────────────────


class _IdAllocator:
    def __init__(self) -> None:
        self._next = 1

    def next(self) -> int:
        v = self._next
        self._next += 1
        return v


# ── Color table ────────────────────────────────────────────────────────


def _color_rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r / 255.0, g / 255.0, b / 255.0


class _ColorTable:
    def __init__(self) -> None:
        self._entries: list[tuple[float, float, float]] = []
        self._index: dict[tuple[float, float, float], int] = {}

    def index_for(self, hex_color: str) -> int:
        rgb = _color_rgb(hex_color)
        if rgb in self._index:
            return self._index[rgb]
        pos = len(self._entries)
        self._entries.append(rgb)
        self._index[rgb] = pos
        return pos

    def reference(self, hex_color: str) -> int:
        return self.index_for(hex_color) + 2

    def to_element(self) -> ET.Element:
        el = ET.SubElement(ET.Element("_"), "colortable")
        for r, g, b in self._entries:
            c = ET.SubElement(el, "color")
            c.set("r", f"{r:.6g}")
            c.set("g", f"{g:.6g}")
            c.set("b", f"{b:.6g}")
        return el

    def __len__(self) -> int:
        return len(self._entries)


# ── Font table ─────────────────────────────────────────────────────────


class _FontTable:
    def __init__(self) -> None:
        self._entries: list[str] = []
        self._index: dict[str, int] = {}

    def id_for(self, family: str) -> int:
        if family in self._index:
            return self._index[family]
        font_id = len(self._entries)
        self._entries.append(family)
        self._index[family] = font_id
        return font_id

    def to_element(self) -> ET.Element:
        el = ET.SubElement(ET.Element("_"), "fonttable")
        for font_id, name in enumerate(self._entries):
            f = ET.SubElement(el, "font")
            f.set("id", str(font_id))
            f.set("charset", "utf-8")
            f.set("name", name)
        return el

    def __len__(self) -> int:
        return len(self._entries)


# ── Preflight checks ──────────────────────────────────────────────────


def _check_perspective_inactive(
    context: SceneRenderContext,
) -> None:
    coords_3d = context.state.atom_coords_3d_state.atom_coords_3d
    if not coords_3d:
        return
    model = context.model
    for atom_id, pt3 in coords_3d.items():
        if atom_id in model.atoms and not math.isclose(pt3[2], 0.0, abs_tol=1e-9):
            raise CdxmlUnsupportedObjectError(
                "perspective",
                f"atom {atom_id}",
                "perspective rendering changes visual geometry; "
                "disable perspective or flatten 3D coordinates first",
            )


_VALID_STYLE_ORDER: dict[str, int] = {
    "single": 1,
    "double_center": 2,
    "triple": 3,
}


def _check_bond_style(bond: Bond, bond_id: int) -> None:
    if bond.style not in _SUPPORTED_BOND_STYLES:
        raise CdxmlUnsupportedObjectError(
            "bond",
            str(bond_id),
            f"style '{bond.style}' has no proved CDXML mapping",
        )
    if bond.order not in _BOND_ORDER_SUPPORT:
        raise CdxmlUnsupportedObjectError(
            "bond",
            str(bond_id),
            f"order {bond.order} is not supported",
        )
    expected_order = _VALID_STYLE_ORDER.get(bond.style)
    if expected_order is not None and bond.order != expected_order:
        raise CdxmlUnsupportedObjectError(
            "bond",
            str(bond_id),
            f"style '{bond.style}' requires order {expected_order}, "
            f"got order {bond.order}",
        )


def _check_element_label(element: str, atom_id: int) -> int:
    if element in ATOM_ALIAS_DEFINITIONS:
        raise CdxmlUnsupportedObjectError(
            "atom",
            str(atom_id),
            f"label '{element}' is an atom alias (abbreviation), not a pure element",
        )
    z = _ELEMENT_TO_Z.get(element)
    if z is None:
        raise CdxmlUnsupportedObjectError(
            "atom",
            str(atom_id),
            f"label '{element}' is not a pure element symbol",
        )
    return z


def _check_atom_annotation(
    atom_id: int,
    annotation: dict[str, int] | None,
) -> None:
    if not annotation:
        return
    radical = annotation.get("radical_electrons", 0)
    if radical != 0:
        raise CdxmlUnsupportedObjectError(
            "atom",
            str(atom_id),
            f"radical_electrons={radical} has no proved CDXML radical mapping",
        )


def _check_arrow(record: Arrow, index: int) -> None:
    if record.labels:
        raise CdxmlUnsupportedObjectError(
            "arrow",
            str(index),
            "arrow labels are not yet emitted in CDXML export",
        )
    kind = record.kind
    if kind in _SUPPORTED_LINE_KINDS:
        if record.mirrored:
            raise CdxmlUnsupportedObjectError(
                "arrow",
                str(index),
                "mirrored property is not supported for lines in CDXML export",
            )
        return
    if kind in _SUPPORTED_ARROW_KINDS:
        if record.control is not None:
            raise CdxmlUnsupportedObjectError(
                "arrow",
                str(index),
                "curved arrows have no proved CurvePoints encoding",
            )
        if record.double:
            raise CdxmlUnsupportedObjectError(
                "arrow",
                str(index),
                "double arrow shafts are not supported",
            )
        if record.mirrored:
            raise CdxmlUnsupportedObjectError(
                "arrow",
                str(index),
                "mirrored property is not supported for arrows in CDXML export",
            )
        return
    raise CdxmlUnsupportedObjectError(
        "arrow",
        str(index),
        f"kind '{kind}' has no proved CDXML mapping",
    )


def _check_shape(
    shape: Shape,
    index: int,
    *,
    stroke_color: str = "#000000",
) -> None:
    kind = shape.shape_kind
    if kind not in ("rect", "circle"):
        raise CdxmlUnsupportedObjectError(
            "shape",
            str(index),
            f"shape_kind '{kind}' has no proved CDXML mapping",
        )
    if shape.fill_alpha is not None and shape.fill_alpha < 1.0:
        if shape.fill is not None:
            raise CdxmlUnsupportedObjectError(
                "shape",
                str(index),
                "translucent fill has no proved CDXML encoding",
            )
    stroke = shape.stroke_style
    if stroke == "none" and shape.fill is not None:
        pass
    elif stroke == "solid":
        if shape.fill is not None and shape.fill != stroke_color:
            raise CdxmlUnsupportedObjectError(
                "shape",
                str(index),
                "shape has different stroke and fill colours; "
                "CDXML supports one color attribute per graphic",
            )
    else:
        raise CdxmlUnsupportedObjectError(
            "shape",
            str(index),
            f"stroke_style '{stroke}' has no proved CDXML mapping",
        )


def _check_transform_no_rotation(
    transform: QTransform,
    object_kind: str,
    object_id: str,
) -> None:
    m11 = transform.m11()
    m12 = transform.m12()
    m21 = transform.m21()
    m22 = transform.m22()
    if not math.isclose(m12, 0.0, abs_tol=1e-6):
        raise CdxmlUnsupportedObjectError(
            object_kind,
            object_id,
            "rotated transform (m12 != 0) has no proved RotationAngle encoding",
        )
    if not math.isclose(m21, 0.0, abs_tol=1e-6):
        raise CdxmlUnsupportedObjectError(
            object_kind,
            object_id,
            "rotated transform (m21 != 0) has no proved RotationAngle encoding",
        )
    if not (m11 > 0 and math.isclose(m11, m22, rel_tol=1e-6)):
        raise CdxmlUnsupportedObjectError(
            object_kind,
            object_id,
            "non-uniform or negative scale transform is not supported",
        )


def _check_note_formatting(
    context: SceneRenderContext,
    item: object,
    index: int,
) -> None:
    from PyQt6.QtWidgets import QGraphicsTextItem

    if not isinstance(item, QGraphicsTextItem):
        raise CdxmlUnsupportedObjectError("note", str(index), "note is not a text item")

    transform = item.sceneTransform()
    _check_transform_no_rotation(transform, "note", str(index))

    document = item.document()
    if document is None:
        return

    from PyQt6.QtGui import QFont

    default_font = document.defaultFont()
    if default_font is not None:
        if default_font.capitalization() != QFont.Capitalization.MixedCase:
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                f"default font capitalization "
                f"{default_font.capitalization().name} is not supported in CDXML",
            )
        if not math.isclose(default_font.wordSpacing(), 0.0, abs_tol=1e-9):
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                "default font word spacing is not supported in CDXML",
            )
        df_stretch = default_font.stretch()
        if df_stretch != 0 and df_stretch != 100:
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                f"default font stretch {df_stretch} is not supported in CDXML",
            )

    block = document.begin()
    while block.isValid():
        _check_note_block(block, document, index)
        block = block.next()


def _check_note_block(
    block: QTextBlock,
    document: QTextDocument,
    index: int,
) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QTextCharFormat, QTextFormat

    if block.textList() is not None:
        raise CdxmlUnsupportedObjectError(
            "note", str(index), "list formatting is not supported"
        )
    frame = document.rootFrame()
    if frame is not None and frame.childFrames():
        raise CdxmlUnsupportedObjectError(
            "note", str(index), "table/frame formatting is not supported"
        )
    bf = block.blockFormat()
    has_block_alignment = bf.hasProperty(QTextFormat.Property.BlockAlignment)
    if has_block_alignment:
        effective_alignment = bf.alignment()
    else:
        effective_alignment = document.defaultTextOption().alignment()
    if effective_alignment & (
        Qt.AlignmentFlag.AlignRight
        | Qt.AlignmentFlag.AlignHCenter
        | Qt.AlignmentFlag.AlignJustify
    ):
        raise CdxmlUnsupportedObjectError(
            "note",
            str(index),
            "non-left text alignment is not supported in CDXML",
        )

    default_font = document.defaultFont()

    frag_it = block.begin()
    while not frag_it.atEnd():
        fragment = frag_it.fragment()
        fmt = fragment.charFormat()
        font = fmt.font()
        if default_font is not None:
            font = font.resolve(default_font)
        if font.italic():
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                "italic text has no proved CDXML face bit",
            )
        weight = font.weight()
        if weight != QFont.Weight.Normal and weight != QFont.Weight.Bold:
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                f"font weight {int(weight)} is not supported; "
                "only Normal (400) and Bold (700) are mapped",
            )
        if font.underline():
            raise CdxmlUnsupportedObjectError(
                "note", str(index), "underline text is not supported"
            )
        if font.overline():
            raise CdxmlUnsupportedObjectError(
                "note", str(index), "overline text is not supported"
            )
        if font.strikeOut():
            raise CdxmlUnsupportedObjectError(
                "note", str(index), "strikeout text is not supported"
            )
        va = fmt.verticalAlignment()
        if va in (
            QTextCharFormat.VerticalAlignment.AlignSubScript,
            QTextCharFormat.VerticalAlignment.AlignSuperScript,
        ):
            raise CdxmlUnsupportedObjectError(
                "note", str(index), "sub/superscript in notes is not supported"
            )
        bg = fmt.background()
        if bg.style() != Qt.BrushStyle.NoBrush and bg.color().alpha() > 0:
            raise CdxmlUnsupportedObjectError(
                "note", str(index), "text background highlight is not supported"
            )
        spacing = fmt.fontLetterSpacing()
        if spacing != 0.0 and spacing != 100.0:
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                "custom letter spacing is not supported in CDXML",
            )
        if fmt.textOutline().style() != Qt.PenStyle.NoPen:
            raise CdxmlUnsupportedObjectError(
                "note", str(index), "text outline is not supported in CDXML"
            )
        if fmt.isImageFormat():
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                "embedded images in text are not supported in CDXML",
            )
        capitalization = font.capitalization()
        if capitalization != QFont.Capitalization.MixedCase:
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                f"font capitalization {capitalization.name} is not supported in CDXML",
            )
        if not math.isclose(font.wordSpacing(), 0.0, abs_tol=1e-9):
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                "custom word spacing is not supported in CDXML",
            )
        stretch = font.stretch()
        if stretch != 0 and stretch != 100:
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                f"font stretch {stretch} is not supported in CDXML",
            )
        underline_style = fmt.underlineStyle()
        if underline_style not in (
            QTextCharFormat.UnderlineStyle.NoUnderline,
            QTextCharFormat.UnderlineStyle.SingleUnderline,
        ):
            raise CdxmlUnsupportedObjectError(
                "note",
                str(index),
                f"underline style {underline_style.name} is not supported in CDXML",
            )
        frag_it += 1


def _check_note_box(
    context: SceneRenderContext,
    item: object,
    index: int,
) -> None:
    settings = context.state.text_style_state
    if settings.note_box_enabled or settings.note_border_enabled:
        raise CdxmlUnsupportedObjectError(
            "note_box",
            str(index),
            "note box background/border is not emitted in CDXML; "
            "disable note boxes and borders before exporting",
        )


# ── Uniform scale ──────────────────────────────────────────────────────


def _uniform_scale(plan: ExportPlan) -> float:
    return plan.out_w_pt / plan.source_w


def _scale_coord(
    value: float,
    origin: float,
    scale: float,
) -> float:
    return (value - origin) * scale


# ── Coordinate helpers ─────────────────────────────────────────────────


def _pt_attr(x: float, y: float) -> str:
    return f"{x:.12g} {y:.12g}"


def _pt3_attr(x: float, y: float) -> str:
    return f"{x:.12g} {y:.12g} 0"


def _bbox_attr(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"{x1:.12g} {y1:.12g} {x2:.12g} {y2:.12g}"


# ── XML text validation ──────────────────────────────────────────────


def _validate_xml_text(
    text: str,
    object_kind: str,
    object_id: str,
) -> str:
    if _XML_ILLEGAL_RE.search(text):
        raise CdxmlUnsupportedObjectError(
            object_kind,
            object_id,
            "text contains characters illegal in XML 1.0",
        )
    return text


# ── Role preflight ───────────────────────────────────────────────────


def _preflight_roles(
    export_items: list[QGraphicsItem],
) -> None:
    for item in export_items:
        if not item.isVisible():
            continue
        role = item.data(0)
        if role is None or role in EXPORT_EXCLUDED_KINDS:
            continue
        if role == "arrow_label":
            raise CdxmlUnsupportedObjectError(
                "arrow_label",
                str(item.data(3) or "?"),
                "arrow labels are not yet emitted in CDXML export",
            )
        if role == "mark":
            raise CdxmlUnsupportedObjectError(
                "mark",
                str(item.data(3) or "?"),
                "scene marks (including charge marks) have no proved "
                "CDXML mapping; use native atom Charge annotation instead",
            )
        if role in ("atom", "bond", "shape", "note", "note_box"):
            continue
        if role in _SUPPORTED_LINE_KINDS or role in _SUPPORTED_ARROW_KINDS:
            continue
        if role == "arrow":
            continue
        if role in ("line", "line_dashed", "line_wavy", "line_bold"):
            if role != "line":
                raise CdxmlUnsupportedObjectError(
                    "line",
                    str(item.data(3) or "?"),
                    f"line kind '{role}' has no proved CDXML mapping",
                )
            continue
        raise CdxmlUnsupportedObjectError(
            str(role),
            str(item.data(1) or item.data(3) or "?"),
            f"object role '{role}' has no proved CDXML mapping",
        )


# ── Fragment interleaving check ─────────────────────────────────────


def _check_item_fragment_interleave(
    export_items: list[QGraphicsItem],
    frag_ranges: list[tuple[int, int, int]],
    frag_items: dict[int, list[QGraphicsItem]],
    scene_pos: dict[int, int],
    export_set: set[QGraphicsItem],
) -> None:
    non_frag_roles = frozenset({"note", "arrow", "line", "shape"})
    for item in export_items:
        role = item.data(0)
        if role not in non_frag_roles or not item.isVisible():
            continue
        item_rank = scene_pos.get(id(item), -1)
        item_bounds = item.sceneBoundingRect()
        for frag_min, frag_max, comp_idx in frag_ranges:
            if frag_min < item_rank < frag_max:
                for frag_item in frag_items.get(comp_idx, []):
                    if frag_item in export_set and item_bounds.intersects(
                        frag_item.sceneBoundingRect()
                    ):
                        raise CdxmlUnsupportedObjectError(
                            str(role),
                            str(item.data(3) or "?"),
                            "item interleaves with a fragment's z-order "
                            "(between its bonds and atoms); CDXML cannot "
                            "represent this stacking",
                        )


def _check_fragment_pair_interleave(
    frag_ranges: list[tuple[int, int, int]],
    frag_items: dict[int, list[QGraphicsItem]],
) -> None:
    for i, (min_i, max_i, comp_i) in enumerate(frag_ranges):
        for min_j, max_j, comp_j in frag_ranges[i + 1 :]:
            if min_i < max_j and min_j < max_i:
                for it_i in frag_items.get(comp_i, []):
                    bi = it_i.sceneBoundingRect()
                    for it_j in frag_items.get(comp_j, []):
                        if bi.intersects(it_j.sceneBoundingRect()):
                            raise CdxmlUnsupportedObjectError(
                                "fragment",
                                str(comp_i),
                                "two fragments interleave in z-order and "
                                "overlap spatially; CDXML cannot represent "
                                "this stacking",
                            )


def _check_fragment_interleaving(
    context: SceneRenderContext,
    export_items: list[QGraphicsItem],
    atom_ids_in_export: set[int],
) -> None:
    from PyQt6.QtCore import Qt as QtCore_Qt

    model = context.model
    bond_pairs = [
        (bond.a, bond.b)
        for bond in model.bonds
        if bond is not None
        and bond.a in atom_ids_in_export
        and bond.b in atom_ids_in_export
    ]
    components = connected_atom_components(atom_ids_in_export, bond_pairs)
    atom_to_comp: dict[int, int] = {}
    for comp_idx, comp in enumerate(components):
        for aid in comp:
            atom_to_comp[aid] = comp_idx

    frag_items: dict[int, list[QGraphicsItem]] = {}
    for item in context.scene.items():
        role = item.data(0)
        if role == "atom":
            aid = item.data(1)
            if isinstance(aid, int) and aid in atom_to_comp:
                frag_items.setdefault(atom_to_comp[aid], []).append(item)
        elif role == "bond":
            bid = item.data(1)
            if isinstance(bid, int) and 0 <= bid < len(model.bonds):
                bond = model.bonds[bid]
                if bond is not None and bond.a in atom_to_comp:
                    frag_items.setdefault(atom_to_comp[bond.a], []).append(item)

    if not frag_items:
        return

    scene_order = list(context.scene.items(QtCore_Qt.SortOrder.AscendingOrder))
    scene_pos = {id(it): i for i, it in enumerate(scene_order)}

    frag_ranges: list[tuple[int, int, int]] = []
    for comp_idx, items_list in frag_items.items():
        ranks = [scene_pos.get(id(it), 0) for it in items_list]
        if ranks:
            frag_ranges.append((min(ranks), max(ranks), comp_idx))

    export_set = set(export_items)
    _check_item_fragment_interleave(
        export_items, frag_ranges, frag_items, scene_pos, export_set
    )
    _check_fragment_pair_interleave(frag_ranges, frag_items)


# ── Main preflight ───────────────────────────────────────────────────


def preflight_cdxml(
    context: SceneRenderContext,
    items: Sequence[QGraphicsItem],
    plan: ExportPlan,
    *,
    background: str = "white",
    groups: Mapping[int, SceneGroup] | None = None,
) -> None:
    """Validate every visible item can be faithfully serialized.

    Raises CdxmlUnsupportedObjectError for the first unsupported construct.
    Must be called before any file I/O.
    """
    if background not in ("white", "transparent"):
        raise CdxmlUnsupportedObjectError(
            "background",
            background,
            "only 'white' and 'transparent' backgrounds are supported",
        )

    _check_perspective_inactive(context)

    model = context.model
    export_items = export_item_closure(list(items))
    export_set = set(export_items)

    atom_ids_in_export: set[int] = set()
    exported_record_ids: set[int] = set()
    for item in export_items:
        role = item.data(0)
        if role == "atom":
            if not item.isVisible():
                continue
            aid = item.data(1)
            if isinstance(aid, int):
                atom_ids_in_export.add(aid)
        rec_id = item.data(3)
        if isinstance(rec_id, int):
            exported_record_ids.add(rec_id)

    bond_color = context.renderer.bond_pen().color().name()

    for atom_id, atom in model.atoms.items():
        if atom_id not in atom_ids_in_export:
            continue
        _check_element_label(atom.element, atom_id)
        annotation = model.atom_annotation_for(atom_id)
        _check_atom_annotation(atom_id, annotation)

    for bond_id, bond in enumerate(model.bonds):
        if bond is None:
            continue
        if bond.a not in atom_ids_in_export and bond.b not in atom_ids_in_export:
            continue
        if bond.a in atom_ids_in_export and bond.b in atom_ids_in_export:
            _check_bond_style(bond, bond_id)
        else:
            raise CdxmlUnsupportedObjectError(
                "bond",
                str(bond_id),
                "selection cuts through a bond; export the whole molecule or "
                "deselect atoms on both sides",
            )

    for item in export_items:
        role = item.data(0)
        if role == "bond":
            bond_id_val = item.data(1)
            if isinstance(bond_id_val, int) and 0 <= bond_id_val < len(model.bonds):
                bond = model.bonds[bond_id_val]
                if bond is not None:
                    if (
                        bond.a not in atom_ids_in_export
                        or bond.b not in atom_ids_in_export
                    ):
                        raise CdxmlUnsupportedObjectError(
                            "bond",
                            str(bond_id_val),
                            "bond endpoint atoms are not in the export set; "
                            "include both endpoint atoms or remove the bond",
                        )

    for idx, arrow_item in enumerate(context.state.arrow_items()):
        if arrow_item is not None and arrow_item in export_set:
            record = context.arrows.record(arrow_item)
            _check_arrow(record, idx)

    for idx, rec_id in enumerate(context.state.shape_state.order):
        rec = context.state.shape_state.records.get(rec_id)
        shape_item = context.state.scene_items_state.shape_items.get(rec_id)
        if rec is not None and shape_item is not None and shape_item in export_set:
            _check_shape(rec, idx, stroke_color=bond_color)

    for idx, note_item in enumerate(context.state.note_items()):
        if note_item is not None and note_item in export_set:
            _check_note_formatting(context, note_item, idx)
            _check_note_box(context, note_item, idx)

    _preflight_roles(export_items)

    _check_fragment_interleaving(context, export_items, atom_ids_in_export)

    if groups:
        for group_id, group in groups.items():
            if group.atom_ids & atom_ids_in_export:
                raise CdxmlUnsupportedObjectError(
                    "group",
                    str(group_id),
                    "group emission is not yet implemented in CDXML export",
                )
            if group.item_ids and set(group.item_ids) & exported_record_ids:
                raise CdxmlUnsupportedObjectError(
                    "group",
                    str(group_id),
                    "group with item members is not yet implemented in CDXML export",
                )


# ── Fragment serialization ───────────────────────────────────────────


def _serialize_fragments(
    components: Sequence[Sequence[int]],
    model: MoleculeModel,
    ids: _IdAllocator,
    colors: _ColorTable,
    fonts: _FontTable,
    s: float,
    ox: float,
    oy: float,
    context: SceneRenderContext,
    scene_rank: dict[int, int],
) -> list[tuple[int, ET.Element]]:
    atom_cdxml_ids: dict[int, int] = {}

    atom_rank_map: dict[int, int] = {}
    for item in context.scene.items():
        if item.data(0) == "atom":
            aid = item.data(1)
            if isinstance(aid, int):
                atom_rank_map[aid] = scene_rank.get(id(item), 0)

    result: list[tuple[int, ET.Element]] = []

    for component in components:
        frag_cdxml_id = ids.next()
        frag = ET.Element("fragment")
        frag.set("id", str(frag_cdxml_id))

        frag_rank = max(atom_rank_map.get(aid, 0) for aid in component)

        for atom_id in sorted(component):
            atom = model.atoms[atom_id]
            node_id = ids.next()
            atom_cdxml_ids[atom_id] = node_id

            ax = _scale_coord(atom.x, ox, s)
            ay = _scale_coord(atom.y, oy, s)

            n = ET.SubElement(frag, "n")
            n.set("id", str(node_id))
            n.set("p", _pt_attr(ax, ay))

            z = _ELEMENT_TO_Z[atom.element]
            if z != 6:
                n.set("Element", str(z))

            annotation = model.atom_annotation_for(atom_id)
            charge = 0
            if annotation:
                charge = annotation.get("formal_charge", 0)
            if charge != 0:
                n.set("Charge", str(charge))

            if atom.color != "#000000":
                n.set("color", str(colors.reference(atom.color)))

            show_label = atom.element != "C" or atom.explicit_label
            if show_label:
                _add_atom_label(
                    n,
                    ids,
                    fonts,
                    colors,
                    s,
                    ox,
                    oy,
                    context,
                    atom_id,
                )

        for _, bond in enumerate(model.bonds):
            if bond is None:
                continue
            if bond.a not in set(component) or bond.b not in set(component):
                continue
            b_el = ET.SubElement(frag, "b")
            b_el.set("id", str(ids.next()))
            b_el.set("B", str(atom_cdxml_ids[bond.a]))
            b_el.set("E", str(atom_cdxml_ids[bond.b]))

            if bond.order != 1:
                b_el.set("Order", str(bond.order))

            display = _BOND_DISPLAY.get(bond.style, "Solid")
            if display != "Solid":
                b_el.set("Display", display)

            if bond.order == 2 and bond.style == "double_center":
                b_el.set("DoublePosition", "Center")

            if bond.color != "#000000":
                b_el.set("color", str(colors.reference(bond.color)))

        result.append((frag_rank, frag))

    return result


# ── Main serialization ───────────────────────────────────────────────


def serialize_cdxml(
    context: SceneRenderContext,
    items: Sequence[QGraphicsItem],
    plan: ExportPlan,
    *,
    background: str = "white",
    groups: Mapping[int, SceneGroup] | None = None,
) -> bytes:
    """Serialize the export items to a CDXML byte string.

    The caller must have run preflight_cdxml first.
    """
    if background not in ("white", "transparent"):
        raise CdxmlUnsupportedObjectError(
            "background",
            background,
            "only 'white' and 'transparent' backgrounds are supported",
        )

    from PyQt6.QtCore import Qt as QtCore_Qt

    s = _uniform_scale(plan)
    ox, oy = plan.source_x, plan.source_y

    ids = _IdAllocator()
    colors = _ColorTable()
    fonts = _FontTable()

    model = context.model
    export_items = export_item_closure(list(items))
    export_set = set(export_items)

    scene_rank: dict[int, int] = {}
    for rank, scene_item in enumerate(
        context.scene.items(QtCore_Qt.SortOrder.AscendingOrder)
    ):
        scene_rank[id(scene_item)] = rank

    atom_ids_in_export: set[int] = set()
    for item in export_items:
        if item.data(0) == "atom":
            if not item.isVisible():
                continue
            aid = item.data(1)
            if isinstance(aid, int):
                atom_ids_in_export.add(aid)

    bond_pairs = []
    for bond in model.bonds:
        if (
            bond is not None
            and bond.a in atom_ids_in_export
            and bond.b in atom_ids_in_export
        ):
            bond_pairs.append((bond.a, bond.b))
    components = connected_atom_components(atom_ids_in_export, bond_pairs)

    renderer = context.renderer
    style = renderer.style
    settings = context.state.tool_settings_state
    line_width_scaled = renderer.bond_line_width() * s
    bold_width_scaled = renderer.bold_bond_width() * s
    hash_spacing_scaled = renderer.hash_spacing() * s
    bond_length_scaled = style.bond_length_px * s
    bond_spacing_scaled = renderer.bond_spacing() * s
    arrow_lw_scaled = settings.arrow_line_width * s
    shape_sw_scaled = shape_stroke_width(style.bond_line_width) * s

    page_width = plan.out_w_pt

    root = ET.Element("CDXML")
    root.set("BondLength", f"{bond_length_scaled:.12g}")
    root.set("BoldWidth", f"{bold_width_scaled:.12g}")
    root.set("LineWidth", f"{line_width_scaled:.12g}")
    root.set("HashSpacing", f"{hash_spacing_scaled:.12g}")
    root.set(
        "BondSpacing",
        f"{bond_spacing_scaled / bond_length_scaled * 100:.12g}",
    )
    root.set("InterpretChemically", "yes")
    root.set("FractionalWidths", "yes")
    root.set("CreationProgram", "Chemvas")

    if background == "white":
        root.set("bgcolor", "2")

    colors.index_for("#ffffff")
    colors.index_for("#000000")

    z_elements: list[tuple[int, ET.Element]] = []

    for frag_rank, frag_el in _serialize_fragments(
        components,
        model,
        ids,
        colors,
        fonts,
        s,
        ox,
        oy,
        context,
        scene_rank,
    ):
        z_elements.append((frag_rank, frag_el))

    bond_color_hex = context.renderer.bond_pen().color().name()

    for _idx, arrow_item in enumerate(context.state.arrow_items()):
        if arrow_item is None or arrow_item not in export_set:
            continue
        if not arrow_item.isVisible():
            continue
        record = context.arrows.record(arrow_item)
        el = _emit_arrow_or_line(
            record,
            ids,
            colors,
            s,
            ox,
            oy,
            arrow_lw_scaled,
            context,
            bond_color_hex=bond_color_hex,
        )
        z_elements.append((scene_rank.get(id(arrow_item), 0), el))

    for rec_id in context.state.shape_state.order:
        rec = context.state.shape_state.records.get(rec_id)
        shape_item = context.state.scene_items_state.shape_items.get(rec_id)
        if rec is None or shape_item is None or shape_item not in export_set:
            continue
        if not shape_item.isVisible():
            continue
        el = _emit_shape(
            rec,
            ids,
            colors,
            s,
            ox,
            oy,
            shape_sw_scaled,
            bond_color_hex=bond_color_hex,
        )
        z_elements.append((scene_rank.get(id(shape_item), 0), el))

    for note_item in context.state.note_items():
        if note_item is None or note_item not in export_set:
            continue
        if not note_item.isVisible():
            continue
        t_elements = _emit_note(
            note_item,
            context,
            ids,
            fonts,
            colors,
            s,
            ox,
            oy,
        )
        note_rank = scene_rank.get(id(note_item), 0)
        for t_el in t_elements:
            z_elements.append((note_rank, t_el))

    z_elements.sort(key=lambda x: x[0])

    color_el = colors.to_element()
    font_el = fonts.to_element()

    if len(colors) > 0:
        root.insert(0, color_el)
    if len(fonts) > 0:
        root.insert(1 if len(colors) > 0 else 0, font_el)

    page = ET.SubElement(root, "page")
    page.set("id", str(ids.next()))
    page.set("Width", f"{page_width:.12g}")
    page.set("Height", f"{plan.out_h_pt:.12g}")
    page.set("BoundingBox", _bbox_attr(0, 0, page_width, plan.out_h_pt))

    if background == "white":
        page.set("bgcolor", "2")

    if not z_elements:
        raise CdxmlUnsupportedObjectError(
            "page",
            "1",
            "export would produce an empty page with no content",
        )

    z_counter = 1
    for _, el in z_elements:
        el.set("Z", str(z_counter))
        z_counter += 1
        page.append(el)

    _indent_preserving_text(root)
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes


def _indent_preserving_text(root: ET.Element, level: int = 0) -> None:
    indent = "\n" + "  " * level
    child_indent = "\n" + "  " * (level + 1)
    if root.tag in ("t", "s"):
        return
    children = list(root)
    if children:
        if root.text is None or not root.text.strip():
            root.text = child_indent
        for i, child in enumerate(children):
            _indent_preserving_text(child, level + 1)
            if child.tail is None or not child.tail.strip():
                child.tail = child_indent if i < len(children) - 1 else indent
    if not children and root.text is None:
        root.text = None


# ── Atom label emission ────────────────────────────────────────────────


def _add_atom_label(
    n: ET.Element,
    ids: _IdAllocator,
    fonts: _FontTable,
    colors: _ColorTable,
    scale: float,
    ox: float,
    oy: float,
    context: SceneRenderContext,
    atom_id: int,
) -> None:
    from PyQt6.QtGui import QFontInfo

    renderer = context.renderer
    atom_font = renderer.atom_font()
    item_scale, scene_baseline_y, scene_label_x = _find_atom_item_info(
        context,
        atom_id,
    )
    pixel_size = _font_pixel_size(atom_font)
    label_size = pixel_size * item_scale * scale

    family = QFontInfo(atom_font).family()
    font_id = fonts.id_for(family)

    color_ref = "3"
    atom_obj = context.model.atoms.get(atom_id)
    if atom_obj is None:
        raise CdxmlUnsupportedObjectError(
            "atom", str(atom_id), "atom not found in model"
        )
    if atom_obj.color != "#000000":
        color_ref = str(colors.reference(atom_obj.color))

    face = _FACE_BOLD if atom_font.bold() else 0

    if scene_label_x is None or scene_baseline_y is None:
        raise CdxmlUnsupportedObjectError(
            "atom",
            str(atom_id),
            "atom label baseline could not be determined from scene item; "
            "the label owner or layout record is missing",
        )
    ax = _scale_coord(scene_label_x, ox, scale)
    ay = _scale_coord(scene_baseline_y, oy, scale)

    t = ET.SubElement(n, "t")
    t.set("id", str(ids.next()))
    t.set("p", _pt_attr(ax, ay))
    t.set("Justification", "Left")
    t.set("InterpretChemically", "no")
    t.set("CaptionLineHeight", "1")

    s_el = ET.SubElement(t, "s")
    s_el.set("font", str(font_id))
    s_el.set("size", f"{label_size:.12g}")
    s_el.set("color", color_ref)
    if face:
        s_el.set("face", str(face))
    s_el.text = _validate_xml_text(
        atom_obj.element,
        "atom",
        str(atom_id),
    )


def _find_atom_item_info(
    context: SceneRenderContext,
    atom_id: int,
) -> tuple[float, float | None, float | None]:
    from PyQt6.QtWidgets import QGraphicsTextItem

    item = context.state.atom_graphics_state.atom_items.get(atom_id)
    if item is None:
        return 1.0, None, None
    if not item.isVisible():
        raise CdxmlUnsupportedObjectError(
            "atom",
            str(atom_id),
            "hidden atom label item cannot be faithfully exported",
        )
    transform = item.sceneTransform()
    _check_transform_no_rotation(transform, "atom", str(atom_id))
    x_s = transform.m11()
    if x_s <= 0:
        return 1.0, None, None
    if not isinstance(item, QGraphicsTextItem):
        return x_s, None, None
    document = item.document()
    if document is None:
        return x_s, None, None
    block = document.begin()
    if not block.isValid():
        return x_s, None, None
    layout = block.layout()
    if layout is None or layout.lineCount() == 0:
        return x_s, None, None
    line = layout.lineAt(0)
    local_x = layout.position().x() + line.x()
    local_baseline_y = layout.position().y() + line.y() + line.ascent()
    scene_label_x = (
        transform.m11() * local_x + transform.m21() * local_baseline_y + transform.dx()
    )
    scene_baseline_y = (
        transform.m12() * local_x + transform.m22() * local_baseline_y + transform.dy()
    )
    return x_s, scene_baseline_y, scene_label_x


def _font_pixel_size(font: object) -> float:
    from PyQt6.QtGui import QFont, QRawFont

    if not isinstance(font, QFont):
        raise CdxmlUnsupportedObjectError("font", "unknown", "expected QFont instance")
    raw = QRawFont.fromFont(font)
    ps = raw.pixelSize()
    if ps > 0:
        return float(ps)
    raise CdxmlUnsupportedObjectError(
        "font",
        font.family(),
        "raw font pixel size is not available; cannot determine label size",
    )


def _check_glyph_font_consistency(
    font: object,
    primary_family: str,
    text: str,
    object_kind: str,
    object_id: str,
) -> None:
    from PyQt6.QtGui import QFont, QTextLayout

    if not isinstance(font, QFont):
        return
    layout = QTextLayout(text, font)
    layout.beginLayout()
    line = layout.createLine()
    if line.isValid():
        line.setLineWidth(1e6)
    layout.endLayout()
    for run in layout.glyphRuns():
        raw = run.rawFont()
        run_family = raw.familyName()
        if run_family and run_family != primary_family:
            raise CdxmlUnsupportedObjectError(
                object_kind,
                object_id,
                f"text requires glyph fallback font '{run_family}' "
                f"instead of primary font '{primary_family}'; "
                "mixed/fallback fonts cannot be faithfully represented",
            )
        for glyph_index in run.glyphIndexes():
            if glyph_index == 0:
                raise CdxmlUnsupportedObjectError(
                    object_kind,
                    object_id,
                    "text contains glyphs that map to index 0 (.notdef); "
                    f"font '{run_family or primary_family}' is missing "
                    "required glyph outlines and would render as tofu",
                )


# ── Arrow / line emission ─────────────────────────────────────────────


def _emit_arrow_or_line(
    record: Arrow,
    ids: _IdAllocator,
    colors: _ColorTable,
    s: float,
    ox: float,
    oy: float,
    arrow_lw_scaled: float,
    context: SceneRenderContext,
    *,
    bond_color_hex: str = "#000000",
) -> ET.Element:
    kind = record.kind

    sx = _scale_coord(record.start[0], ox, s)
    sy = _scale_coord(record.start[1], oy, s)
    ex = _scale_coord(record.end[0], ox, s)
    ey = _scale_coord(record.end[1], oy, s)

    if kind == "line":
        g = ET.Element("graphic")
        g.set("id", str(ids.next()))
        g.set("GraphicType", "Line")
        g.set("ArrowType", "NoHead")
        g.set("LineType", "Solid")
        g.set("BoundingBox", _bbox_attr(sx, sy, ex, ey))
        g.set("LineWidth", f"{arrow_lw_scaled:.12g}")
        effective_color = record.color or bond_color_hex
        if effective_color != "#000000":
            g.set("color", str(colors.reference(effective_color)))
        return g

    renderer = context.renderer
    settings = context.state.tool_settings_state
    commands = arrow_path_commands(
        start=record.start,
        end=record.end,
        kind="arrow",
        bond_length=renderer.style.bond_length_px,
        bond_spacing=renderer.bond_spacing(),
        wave_spacing=0.0,
        line_width=settings.arrow_line_width,
        head_scale=settings.arrow_head_scale,
    )

    for cmd, _args in commands:
        if cmd not in ("M", "L"):
            raise CdxmlUnsupportedObjectError(
                "arrow",
                str(record.kind),
                f"arrow path contains unsupported command '{cmd}'; "
                "only M and L commands can be exported",
            )

    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    current: tuple[float, float] = (0.0, 0.0)
    for cmd, args in commands:
        if cmd == "M":
            current = (args[0], args[1])
        elif cmd == "L":
            segments.append((current, (args[0], args[1])))
            current = (args[0], args[1])

    group = ET.Element("group")
    group.set("id", str(ids.next()))

    for seg_start, seg_end in segments:
        seg_sx = _scale_coord(seg_start[0], ox, s)
        seg_sy = _scale_coord(seg_start[1], oy, s)
        seg_ex = _scale_coord(seg_end[0], ox, s)
        seg_ey = _scale_coord(seg_end[1], oy, s)

        g = ET.SubElement(group, "graphic")
        g.set("id", str(ids.next()))
        g.set("GraphicType", "Line")
        g.set("ArrowType", "NoHead")
        g.set("LineType", "Solid")
        g.set("BoundingBox", _bbox_attr(seg_sx, seg_sy, seg_ex, seg_ey))
        g.set("LineWidth", f"{arrow_lw_scaled:.12g}")

    effective_color = record.color or bond_color_hex
    if effective_color != "#000000":
        color_ref = str(colors.reference(effective_color))
        for child in group:
            child.set("color", color_ref)

    return group


# ── Shape emission ─────────────────────────────────────────────────────


def _emit_shape(
    shape: Shape,
    ids: _IdAllocator,
    colors: _ColorTable,
    s: float,
    ox: float,
    oy: float,
    stroke_width_scaled: float,
    *,
    bond_color_hex: str = "#000000",
) -> ET.Element:
    left = _scale_coord(shape.left, ox, s)
    top = _scale_coord(shape.top, oy, s)
    right = _scale_coord(shape.right, ox, s)
    bottom = _scale_coord(shape.bottom, oy, s)

    _kind, geo_x, geo_y, geo_w, geo_h, _ = shape_outline(
        left,
        top,
        right - left,
        bottom - top,
        shape.shape_kind,
    )

    g = ET.Element("graphic")
    g.set("id", str(ids.next()))

    if shape.shape_kind == "circle":
        g.set("GraphicType", "Oval")
        cx = geo_x + geo_w / 2
        cy = geo_y + geo_h / 2
        r = geo_w / 2
        g.set("Center3D", _pt3_attr(cx, cy))
        g.set("MajorAxisEnd3D", _pt3_attr(cx + r, cy))
        g.set("MinorAxisEnd3D", _pt3_attr(cx, cy + r))
        g.set("BoundingBox", _bbox_attr(cx + r, cy, cx, cy))

        if shape.fill is not None:
            g.set("OvalType", "Circle Filled")
        else:
            g.set("OvalType", "Circle")

    elif shape.shape_kind == "rect":
        g.set("GraphicType", "Rectangle")
        g.set(
            "BoundingBox",
            _bbox_attr(geo_x + geo_w, geo_y + geo_h, geo_x, geo_y),
        )
        g.set(
            "Center3D",
            _pt3_attr(geo_x + geo_w / 2, geo_y + geo_h / 2),
        )
        g.set(
            "MajorAxisEnd3D",
            _pt3_attr(geo_x + geo_w, geo_y + geo_h / 2),
        )
        g.set(
            "MinorAxisEnd3D",
            _pt3_attr(geo_x + geo_w / 2, geo_y + geo_h),
        )

        if shape.fill is not None:
            g.set("RectangleType", "Filled")
        else:
            g.set("RectangleType", "Plain")

    if shape.fill is not None:
        g.set("color", str(colors.reference(shape.fill)))
    elif shape.stroke_style != "none" and bond_color_hex != "#000000":
        g.set("color", str(colors.reference(bond_color_hex)))

    if shape.stroke_style == "none":
        g.set("LineWidth", "0")
    else:
        g.set("LineWidth", f"{stroke_width_scaled:.12g}")

    return g


# ── Note / text emission ──────────────────────────────────────────────


def _emit_note(
    item: object,
    context: SceneRenderContext,
    ids: _IdAllocator,
    fonts: _FontTable,
    colors: _ColorTable,
    s: float,
    ox: float,
    oy: float,
) -> list[ET.Element]:
    from PyQt6.QtWidgets import QGraphicsTextItem

    if not isinstance(item, QGraphicsTextItem):
        return []

    document = item.document()
    if document is None:
        return []

    item.boundingRect()

    item_transform = item.sceneTransform()
    item_scale = math.hypot(item_transform.m11(), item_transform.m12())
    if item_scale <= 0:
        item_scale = 1.0

    result: list[ET.Element] = []

    block = document.begin()
    while block.isValid():
        layout = block.layout()
        if layout is None:
            block = block.next()
            continue

        block_text = block.text()
        block_utf16 = block_text.encode("utf-16-le")
        default_font = document.defaultFont()

        for li in range(layout.lineCount()):
            line = layout.lineAt(li)
            if line.textLength() <= 0:
                continue

            line_x = layout.position().x() + line.position().x()
            line_baseline_y = layout.position().y() + line.y() + line.ascent()

            scene_line_x = (
                item_transform.m11() * line_x
                + item_transform.m21() * line_baseline_y
                + item_transform.dx()
            )
            scene_line_y = (
                item_transform.m12() * line_x
                + item_transform.m22() * line_baseline_y
                + item_transform.dy()
            )

            cdxml_x = _scale_coord(scene_line_x, ox, s)
            cdxml_y = _scale_coord(scene_line_y, oy, s)

            t_el = ET.Element("t")
            t_el.set("id", str(ids.next()))
            t_el.set("p", _pt_attr(cdxml_x, cdxml_y))
            t_el.set("Justification", "Left")
            t_el.set("InterpretChemically", "no")
            t_el.set("CaptionLineHeight", "1")

            line_start = line.textStart()
            line_end = line_start + line.textLength()

            frag_it = block.begin()
            while not frag_it.atEnd():
                fragment = frag_it.fragment()
                frag_start = fragment.position() - block.position()
                frag_end = frag_start + fragment.length()

                overlap_start = max(frag_start, line_start)
                overlap_end = min(frag_end, line_end)

                if overlap_start < overlap_end:
                    text = block_utf16[overlap_start * 2 : overlap_end * 2].decode(
                        "utf-16-le"
                    )

                    if text:
                        _emit_note_run(
                            t_el,
                            text,
                            fragment,
                            layout,
                            default_font,
                            item,
                            item_scale,
                            s,
                            fonts,
                            colors,
                        )

                frag_it += 1

            if len(t_el) > 0:
                result.append(t_el)

        block = block.next()

    return result


def _emit_note_run(
    t_el: ET.Element,
    text: str,
    fragment: QTextFragment,
    layout: QTextLayout,
    default_font: QFont,
    item: QGraphicsTextItem,
    item_scale: float,
    s: float,
    fonts: _FontTable,
    colors: _ColorTable,
) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFontInfo

    fmt = fragment.charFormat()
    frag_font = fmt.font().resolve(default_font)

    pixel_size = _font_pixel_size(frag_font)

    frag_size = pixel_size * item_scale * s
    family = QFontInfo(frag_font).family()
    _check_glyph_font_consistency(
        frag_font,
        family,
        text,
        "note",
        str(item.data(3) or "?"),
    )
    font_id = fonts.id_for(family)

    brush = fmt.foreground()
    if brush.style() == Qt.BrushStyle.NoBrush:
        frag_color = item.defaultTextColor()
    else:
        frag_color = brush.color()

    if frag_color.alpha() < 255:
        raise CdxmlUnsupportedObjectError(
            "note",
            str(item.data(3) or "?"),
            "translucent text colour cannot be represented in CDXML",
        )

    color_hex = frag_color.name()
    color_ref = str(colors.reference(color_hex)) if color_hex != "#000000" else "3"

    face = _FACE_BOLD if frag_font.bold() else 0

    s_el = ET.SubElement(t_el, "s")
    s_el.set("font", str(font_id))
    s_el.set("size", f"{frag_size:.12g}")
    s_el.set("color", color_ref)
    if face:
        s_el.set("face", str(face))
    s_el.text = _validate_xml_text(text, "note", str(item.data(3) or "?"))


# ── Public API ─────────────────────────────────────────────────────────

__all__ = [
    "CdxmlUnsupportedObjectError",
    "GroupsProvider",
    "preflight_cdxml",
    "serialize_cdxml",
]
