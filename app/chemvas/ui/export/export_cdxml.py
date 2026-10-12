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
from copy import deepcopy
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

from chemvas.domain.atom_aliases import ATOM_ALIAS_DEFINITIONS
from chemvas.domain.document import (
    Arrow,
    Bond,
    MoleculeModel,
    Shape,
    connected_atom_components,
)
from chemvas.features.annotations import (
    BRACKET_SYMBOLS,
    bracket_path_commands,
    bracket_stroke_width,
    bracket_symbol_layout,
)
from chemvas.features.export import (
    CaptionGeometry,
    CdxmlDocumentaryContact,
    CdxmlTextLayoutReference,
    authorize_documentary_contact_for_export,
    reflow_cdxml_captions,
)
from chemvas.features.rendering import arrow_path_commands
from chemvas.ui.annotations.shape_geometry import shape_outline, shape_stroke_width
from chemvas.ui.export.export_scope import (
    EXPORT_EXCLUDED_KINDS,
    export_item_closure,
    item_export_bounds,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import (
        QFont,
        QTextBlock,
        QTextDocument,
        QTextFragment,
        QTextLayout,
        QTransform,
    )
    from PyQt6.QtWidgets import (
        QGraphicsItem,
        QGraphicsLineItem,
        QGraphicsPathItem,
        QGraphicsTextItem,
    )

    from chemvas.domain.document.groups import SceneGroup
    from chemvas.domain.document.ts_brackets import TSBracket
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


# ── Atom label semantics ───────────────────────────────────────────────
#
# A drawn atom label is exported with chemistry only when its meaning is
# typed. Pure element symbols are typed by the periodic table. The
# abbreviations in ``_VERIFIED_FRAGMENTS`` have a fixed graph that is checked
# below at import time. Anything else - including the raw label ``Ar``, which
# may mean argon or an aryl group, and hydrogens drawn with an identifier
# such as ``H\u1d43`` - needs an explicit caller-supplied ``CdxmlLabelBinding``.
# Without one the export refuses; the label text, its colour, its neighbours
# and any legend are never used to guess the meaning.

# Element symbols that are also common drawn group labels.
_AMBIGUOUS_ELEMENT_LABELS = frozenset({"Ar"})

# Superscript lowercase letters accepted as a hydrogen identifier (H\u1d43,
# H\u1d47, ...). Digits, signs and other marks are excluded so an identifier
# can never be read as an isotope or a charge.
_IDENTIFIER_SUPERSCRIPT_LETTERS = frozenset(
    "\u1d43\u1d47\u1d9c\u1d48\u1d49\u1da0\u1d4d\u02b0\u2071\u02b2\u1d4f\u02e1\u1d50"
    "\u207f\u1d52\u1d56\u02b3\u02e2\u1d57\u1d58\u1d5b\u02b7\u02e3\u02b8\u1dbb"
)


def _is_identifier_hydrogen(label: str) -> bool:
    return (
        len(label) >= 2
        and label[0] == "H"
        and all(char in _IDENTIFIER_SUPERSCRIPT_LETTERS for char in label[1:])
    )


@dataclass(frozen=True)
class _FragmentDefinition:
    """Internal graph of a contracted group label.

    ``atoms`` holds ``(atomic number, attached hydrogens)``. Atom 0 is the
    only atom bonded to the external connection point. ``bonds`` holds
    ``(first index, second index, order)``. ``layout`` places each atom in
    bond-length units: ``along`` points from the outside neighbour through
    the label position, ``side`` is perpendicular to it; atom 0 sits at the
    label position and the connection point at the neighbour position.
    """

    atoms: tuple[tuple[int, int], ...]
    bonds: tuple[tuple[int, int, int], ...]
    layout: tuple[tuple[float, float], ...]
    aryl: bool = False


def _phenyl_layout() -> tuple[tuple[float, float], ...]:
    # Regular hexagon with circumradius 1 centred one bond length beyond the
    # ipso carbon, which is vertex 0.
    return tuple(
        (
            1.0 + math.cos(math.radians(180.0 + 60.0 * index)),
            math.sin(math.radians(180.0 + 60.0 * index)),
        )
        for index in range(6)
    )


def _para_fluorophenyl_layout() -> tuple[tuple[float, float], ...]:
    ring = _phenyl_layout()
    center = (1.0, 0.0)
    c3_x, c3_y = ring[3]
    dx, dy = c3_x - center[0], c3_y - center[1]
    length = math.hypot(dx, dy)
    if length <= 0.0 or not math.isfinite(length):
        raise RuntimeError("4-F-Ph layout is degenerate")
    ux, uy = dx / length, dy / length
    return (*ring, (c3_x + ux, c3_y + uy))


_VERIFIED_FRAGMENTS: Mapping[str, _FragmentDefinition] = {
    # CH3-
    "Me": _FragmentDefinition(atoms=((6, 3),), bonds=(), layout=((0.0, 0.0),)),
    # C6H5- (Kekule ring, ipso carbon first)
    "Ph": _FragmentDefinition(
        atoms=((6, 0), (6, 1), (6, 1), (6, 1), (6, 1), (6, 1)),
        bonds=((0, 1, 2), (1, 2, 1), (2, 3, 2), (3, 4, 1), (4, 5, 2), (5, 0, 1)),
        layout=_phenyl_layout(),
        aryl=True,
    ),
    # (CH3)3C-
    "tBu": _FragmentDefinition(
        atoms=((6, 0), (6, 3), (6, 3), (6, 3)),
        bonds=((0, 1, 1), (0, 2, 1), (0, 3, 1)),
        layout=((0.0, 0.0), (0.0, -1.0), (1.0, 0.0), (0.0, 1.0)),
    ),
}

_CARBON_VALENCE = 4


def _check_fragment_definitions() -> None:
    """Every internal carbon must have exactly four bonds or hydrogens."""
    for name, definition in _VERIFIED_FRAGMENTS.items():
        if name not in ATOM_ALIAS_DEFINITIONS:
            raise RuntimeError(f"fragment '{name}' is not a registered atom alias")
        if len(definition.layout) != len(definition.atoms):
            raise RuntimeError(f"fragment '{name}' layout does not match its atoms")
        bond_sums = [0] * len(definition.atoms)
        bond_sums[0] += 1  # the single external attachment
        for first, second, order in definition.bonds:
            if first == second or order not in (1, 2, 3):
                raise RuntimeError(f"fragment '{name}' has an invalid bond")
            bond_sums[first] += order
            bond_sums[second] += order
        for index, (atomic_number, hydrogens) in enumerate(definition.atoms):
            if atomic_number != 6 or bond_sums[index] + hydrogens != _CARBON_VALENCE:
                raise RuntimeError(
                    f"fragment '{name}' atom {index} does not satisfy carbon valence"
                )


_check_fragment_definitions()

# Explicit ``aryl_fragment`` identifiers only; not unbound atom aliases.
_BOUND_ARYL_FRAGMENTS: Mapping[str, _FragmentDefinition] = {
    "Ph": _VERIFIED_FRAGMENTS["Ph"],
    "4-F-Ph": _FragmentDefinition(
        atoms=((6, 0), (6, 1), (6, 1), (6, 0), (6, 1), (6, 1), (9, 0)),
        bonds=(
            (0, 1, 2),
            (1, 2, 1),
            (2, 3, 2),
            (3, 4, 1),
            (4, 5, 2),
            (5, 0, 1),
            (3, 6, 1),
        ),
        layout=_para_fluorophenyl_layout(),
        aryl=True,
    ),
}

_FLUORINE_VALENCE = 1


def _is_definition_int(value: object) -> bool:
    return type(value) is int


def _check_bound_aryl_definitions() -> None:
    """Validate bound-only aryl graphs at import time."""
    for name, definition in _BOUND_ARYL_FRAGMENTS.items():
        if not definition.aryl:
            raise RuntimeError(f"bound aryl '{name}' is not marked aryl")
        if not definition.atoms:
            raise RuntimeError(f"bound aryl '{name}' has no atoms")
        if len(definition.layout) != len(definition.atoms):
            raise RuntimeError(f"bound aryl '{name}' layout does not match its atoms")
        origin_along, origin_side = definition.layout[0]
        if not math.isclose(origin_along, 0.0, abs_tol=1e-9) or not math.isclose(
            origin_side, 0.0, abs_tol=1e-9
        ):
            raise RuntimeError(
                f"bound aryl '{name}' ipso layout origin is not at (0, 0)"
            )
        for along, side in definition.layout:
            if not all(math.isfinite(value) for value in (along, side)):
                raise RuntimeError(f"bound aryl '{name}' layout is not finite")
        ipso_atomic_number, ipso_hydrogens = definition.atoms[0]
        if not _is_definition_int(ipso_atomic_number) or ipso_atomic_number != 6:
            raise RuntimeError(f"bound aryl '{name}' ipso atom must be carbon")
        if not _is_definition_int(ipso_hydrogens) or ipso_hydrogens < 0:
            raise RuntimeError(f"bound aryl '{name}' ipso hydrogens are invalid")
        atom_count = len(definition.atoms)
        bond_sums = [0] * atom_count
        bond_sums[0] += 1  # the single external attachment at ipso carbon 0
        for first, second, order in definition.bonds:
            if not _is_definition_int(order) or order not in (1, 2, 3):
                raise RuntimeError(f"bound aryl '{name}' has an invalid bond order")
            if not _is_definition_int(first) or not _is_definition_int(second):
                raise RuntimeError(f"bound aryl '{name}' has invalid bond endpoints")
            if first < 0 or first >= atom_count or second < 0 or second >= atom_count:
                raise RuntimeError(f"bound aryl '{name}' bond endpoint out of range")
            if first == second:
                raise RuntimeError(f"bound aryl '{name}' has an invalid bond")
            bond_sums[first] += order
            bond_sums[second] += order
        for index, (atomic_number, hydrogens) in enumerate(definition.atoms):
            if not _is_definition_int(atomic_number) or not _is_definition_int(
                hydrogens
            ):
                raise RuntimeError(
                    f"bound aryl '{name}' atom {index} has invalid counts"
                )
            if hydrogens < 0:
                raise RuntimeError(
                    f"bound aryl '{name}' atom {index} has negative hydrogens"
                )
            if atomic_number == 6:
                if bond_sums[index] + hydrogens != _CARBON_VALENCE:
                    raise RuntimeError(
                        f"bound aryl '{name}' carbon {index} does not satisfy valence"
                    )
            elif atomic_number == 9:
                if bond_sums[index] + hydrogens != _FLUORINE_VALENCE:
                    raise RuntimeError(
                        f"bound aryl '{name}' fluorine does not satisfy valence"
                    )
            else:
                raise RuntimeError(
                    f"bound aryl '{name}' atom {index} has unsupported element"
                )


_check_bound_aryl_definitions()


def _bound_aryl_definition(name: str) -> _FragmentDefinition | None:
    if type(name) is not str:
        return None
    return _BOUND_ARYL_FRAGMENTS.get(name)


def _nickname_fragment_definition(name: str) -> _FragmentDefinition:
    if name in _VERIFIED_FRAGMENTS:
        return _VERIFIED_FRAGMENTS[name]
    definition = _bound_aryl_definition(name)
    if definition is None:
        raise KeyError(name)
    return definition


@dataclass(frozen=True)
class CdxmlLabelBinding:
    """Caller-supplied typed meaning for one drawn atom label.

    Bindings are passed to ``preflight_cdxml``/``serialize_cdxml`` by atom id.
    They are not stored in or read from the ``.chemvas`` document, and the
    exporter never creates one by itself. Only these meanings exist:

    - ``element_identity(symbol)``: the label is that element. Accepted when
      the label equals the symbol (``Ar`` as argon) or, for hydrogen, when it
      is ``H`` followed by superscript lowercase identifier letters.
    - ``generic_aryl()``: the label ``Ar`` is an unspecified aryl group.
    - ``aryl_fragment(name)``: applies only when the drawn label is exactly
      ``Ar``. It names the verified bound aryl fragment ``name`` (``Ph`` or
      ``4-F-Ph`` today). Identifiers are not read from legends. A literal
      ``4-F-Ph`` atom label always refuses; only ``Ar`` plus this binding can
      select ``4-F-Ph``.
    """

    meaning: str
    element: str | None = None
    fragment: str | None = None
    author_note: str | None = None

    @classmethod
    def element_identity(cls, symbol: str) -> CdxmlLabelBinding:
        return cls("element", element=symbol)

    @classmethod
    def generic_aryl(cls) -> CdxmlLabelBinding:
        return cls("generic_aryl")

    @classmethod
    def aryl_fragment(cls, name: str) -> CdxmlLabelBinding:
        return cls("aryl_fragment", fragment=name)

    @classmethod
    def aryl_label(cls, author_note: str) -> CdxmlLabelBinding:
        return cls("aryl_label", author_note=author_note)


LabelBindings = Mapping[int, CdxmlLabelBinding]
DocumentaryContacts = tuple[CdxmlDocumentaryContact, ...]


@dataclass(frozen=True)
class _LabelPlan:
    """How one exported atom becomes a CDXML node."""

    atomic_number: int | None = None
    fragment: str | None = None
    generic_nickname: str | None = None
    neighbor_id: int | None = None
    check_glyphs: bool = False
    documentary_aryl_note: str | None = None


_CHEMVAS_OBJECTTAG_PREFIX = "Chemvas."


# ── Supported bond encodings ───────────────────────────────────────────
#
# The renderer reads a bond's order before its style: ring templates (and
# structures placed by earlier versions) store order-2 and order-3 bonds with
# the generic "single" style, and those are drawn exactly like "double" and
# "triple".

_BOND_ORDER_SUPPORT = frozenset({1, 2, 3})

_SUPPORTED_BOND_STYLES = frozenset(
    {
        "single",
        "double",
        "double_center",
        "double_outer",
        "triple",
        "wedge",
        "hash",
        "dotted",
        "bold_in",
        "bold_out",
    }
)

# Required order for every supported style except the generic "single".
_STYLE_ORDER: dict[str, int] = {
    "double": 2,
    "double_center": 2,
    "double_outer": 2,
    "triple": 3,
    "wedge": 1,
    "hash": 1,
    "dotted": 1,
    "bold_in": 1,
    "bold_out": 1,
}

# Chemvas draws both stereo styles narrow at ``bond.a``, the end the MOL
# writer also treats as the stereocentre. The CDXML
# ``*Begin`` displays put the narrow end at the ``B`` node.
_STEREO_DISPLAY: dict[str, str] = {
    "wedge": "WedgeBegin",
    "hash": "WedgedHashBegin",
}

# Placeholder DoublePosition, resolved from the drawn lines of the bond.
_DOUBLE_SIDE = "side"

# ── Supported arrow/line kinds ─────────────────────────────────────────

_SUPPORTED_LINE_KINDS = frozenset({"line", "line_dashed", "line_bold"})
# CDXML LineType for each supported line kind. LineType has no dash length
# or gap property, so a consumer draws ``Dashed`` in its own dash pattern;
# what is kept is that the line is dashed, at its endpoints, width and colour.
_LINE_TYPE_FOR_KIND = {"line": "Solid", "line_dashed": "Dashed", "line_bold": "Solid"}
_SUPPORTED_ARROW_KINDS = frozenset({"arrow"})
# TS bracket kinds whose drawn strokes are straight M/L polylines. The curved
# kinds (parentheses, braces) use cubic segments and stay refused.
_SQUARE_BRACKET_KINDS = frozenset({"square_pair", "square_left"})

# ── CDXML face bitmask ─────────────────────────────────────────────────

_FACE_BOLD = 1
_FACE_SUBSCRIPT = 32
_FACE_SUPERSCRIPT = 64
_NATIVE_SCRIPT_SCALE = 0.75

# ── XML 1.0 illegal character pattern ─────────────────────────────────

_XML_ILLEGAL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


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
            c.set("r", f"{r:.17g}")
            c.set("g", f"{g:.17g}")
            c.set("b", f"{b:.17g}")
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


def _bond_encoding(bond: Bond, bond_id: int) -> tuple[str | None, str | None]:
    """Return the bond's CDXML ``Display`` and ``DoublePosition``, or refuse.

    A ``_DOUBLE_SIDE`` position still has to be read from the scene.
    """
    if bond.style in {"dotted", "bold_in", "bold_out"} and (
        type(bond.order) is not int or bond.order != 1
    ):
        raise CdxmlUnsupportedObjectError(
            "bond",
            str(bond_id),
            f"style {bond.style!r} requires order 1 as an exact integer, got {bond.order!r}",
        )
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
    expected_order = _STYLE_ORDER.get(bond.style)
    if expected_order is not None and bond.order != expected_order:
        raise CdxmlUnsupportedObjectError(
            "bond",
            str(bond_id),
            f"style '{bond.style}' requires order {expected_order}, "
            f"got order {bond.order}",
        )
    if bond.order == 2:
        return None, "Center" if bond.style == "double_center" else _DOUBLE_SIDE
    if bond.style in {"bold_in", "bold_out"}:
        return "Bold", None
    return "Dash" if bond.style == "dotted" else _STEREO_DISPLAY.get(bond.style), None


def _resolved_bond_encoding(
    context: SceneRenderContext,
    bond: Bond,
    bond_id: int,
) -> tuple[str | None, str | None]:
    display, position = _bond_encoding(bond, bond_id)
    if bond.style in _STEREO_DISPLAY:
        _check_rendered_stereo_direction(context, bond, bond_id)
    if position == _DOUBLE_SIDE:
        position = _rendered_double_position(context, bond, bond_id)
    return display, position


# ── Rendered bond geometry ────────────────────────────────────────────


def _bond_axis(
    model: MoleculeModel,
    bond: Bond,
    bond_id: int,
) -> tuple[float, float, float, float]:
    a = model.atoms[bond.a]
    b = model.atoms[bond.b]
    length = math.hypot(b.x - a.x, b.y - a.y)
    if length <= 1e-9:
        raise CdxmlUnsupportedObjectError(
            "bond", str(bond_id), "a zero-length bond has no drawable direction"
        )
    return a.x, a.y, (b.x - a.x) / length, (b.y - a.y) / length


def _axis_coords(
    axis: tuple[float, float, float, float],
    x: float,
    y: float,
) -> tuple[float, float]:
    """Distance along the bond from ``a`` and signed page-normal displacement.

    Scene and CDXML y both grow downward. The saved native witness names
    positive (-dy, dx) displacement Left; no screen-handedness guess is used.
    """
    ax, ay, ux, uy = axis
    return (x - ax) * ux + (y - ay) * uy, ux * (y - ay) - uy * (x - ax)


def _scene_line(item: QGraphicsLineItem) -> tuple[float, float, float, float]:
    line = item.line()
    p1 = item.mapToScene(line.p1())
    p2 = item.mapToScene(line.p2())
    return p1.x(), p1.y(), p2.x(), p2.y()


def _rendered_double_position(
    context: SceneRenderContext,
    bond: Bond,
    bond_id: int,
) -> str:
    """CDXML side of a side-placed double's second line, as actually drawn.

    The renderer keeps one line on the bond axis and offsets the other toward
    the ring centre or the substituents. CDX defines ``Right``/``Left`` as
    seen looking from the begin atom to the end atom.
    """
    from PyQt6.QtWidgets import QGraphicsLineItem

    items = context.state.bond_graphics_state.bond_items.get(bond_id) or []
    if len(items) != 2 or not all(
        isinstance(item, QGraphicsLineItem) for item in items
    ):
        raise CdxmlUnsupportedObjectError(
            "bond", str(bond_id), "the drawn double bond lines could not be read"
        )
    axis = _bond_axis(context.model, bond, bond_id)
    offsets: list[float] = []
    for item in items:
        x1, y1, x2, y2 = _scene_line(item)
        offsets.append(_axis_coords(axis, (x1 + x2) / 2, (y1 + y2) / 2)[1])
    on_axis, beside = sorted(offsets, key=abs)
    if abs(beside) <= 1e-6 or abs(on_axis) > abs(beside) * 0.25:
        raise CdxmlUnsupportedObjectError(
            "bond",
            str(bond_id),
            "the drawn double bond is not one axis line with one side line",
        )
    # Native SaveAs/SVG witness: positive page-y normal is CDXML Left.
    return "Left" if beside > 0 else "Right"


def _check_rendered_stereo_direction(
    context: SceneRenderContext,
    bond: Bond,
    bond_id: int,
) -> None:
    """Refuse unless the drawn wedge or hash is narrow at ``bond.a``.

    Compares the drawn width nearest each endpoint: the wedge's apex against
    its base, or the first hash stroke against the last.
    """
    from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPolygonItem

    axis = _bond_axis(context.model, bond, bond_id)
    # (distance along the bond, drawn width) for each cross-section
    sections: list[tuple[float, float]] = []
    for item in context.state.bond_graphics_state.bond_items.get(bond_id) or []:
        if bond.style == "wedge" and isinstance(item, QGraphicsPolygonItem):
            polygon = item.mapToScene(item.polygon())
            for index in range(len(polygon)):
                point = polygon[index]
                along, offset = _axis_coords(axis, point.x(), point.y())
                sections.append((along, abs(offset)))
        elif bond.style == "hash" and isinstance(item, QGraphicsLineItem):
            x1, y1, x2, y2 = _scene_line(item)
            along, _ = _axis_coords(axis, (x1 + x2) / 2, (y1 + y2) / 2)
            sections.append((along, math.hypot(x2 - x1, y2 - y1)))
        else:
            sections.clear()
            break
    if len(sections) >= 2:
        narrow = min(sections, key=lambda section: section[0])[1]
        wide = max(sections, key=lambda section: section[0])[1]
        if narrow < wide:
            return
    raise CdxmlUnsupportedObjectError(
        "bond",
        str(bond_id),
        f"the drawn {bond.style} bond could not be shown to be narrow at its "
        "stored start atom",
    )


def _refuse_atom(atom_id: int | str, reason: str) -> CdxmlUnsupportedObjectError:
    return CdxmlUnsupportedObjectError("atom", str(atom_id), reason)


def _resolve_label_plan(
    model: MoleculeModel,
    atom_id: int,
    label_bindings: LabelBindings | None,
) -> _LabelPlan:
    """Return the typed meaning of an atom label, or refuse."""
    label = model.atoms[atom_id].element
    binding = label_bindings.get(atom_id) if label_bindings else None
    if binding is not None:
        return _bound_label_plan(model, atom_id, label, binding, label_bindings)
    if label in _VERIFIED_FRAGMENTS:
        return _LabelPlan(
            fragment=label,
            neighbor_id=_group_label_attachment(model, atom_id, label, label_bindings),
        )
    if label in ATOM_ALIAS_DEFINITIONS:
        raise _refuse_atom(
            atom_id,
            f"label '{label}' is an atom alias (abbreviation) without a verified "
            "CDXML fragment definition, not a pure element",
        )
    if label in _AMBIGUOUS_ELEMENT_LABELS:
        raise _refuse_atom(
            atom_id,
            f"label '{label}' is ambiguous (the element or a drawn group) and the "
            "document carries no typed meaning for it; the exporter does not "
            "guess from text, colour, neighbours or legends",
        )
    if _is_identifier_hydrogen(label):
        raise _refuse_atom(
            atom_id,
            f"label '{label}' reads as a hydrogen with an identifier, but no typed "
            "element-identity binding was supplied for it; blocked until that "
            "meaning is supplied",
        )
    z = _ELEMENT_TO_Z.get(label)
    if z is None:
        raise _refuse_atom(atom_id, f"label '{label}' is not a pure element symbol")
    return _LabelPlan(atomic_number=z)


def _bound_label_plan(
    model: MoleculeModel,
    atom_id: int,
    label: str,
    binding: object,
    label_bindings: LabelBindings | None = None,
) -> _LabelPlan:
    if not isinstance(binding, CdxmlLabelBinding):
        raise _refuse_atom(atom_id, "label binding must be a CdxmlLabelBinding")
    _check_binding_fields(atom_id, binding)
    if label in ATOM_ALIAS_DEFINITIONS:
        raise _refuse_atom(
            atom_id,
            f"label '{label}' is an atom alias; a label binding cannot override "
            "the alias registry",
        )
    if binding.meaning == "element":
        symbol = binding.element
        z = _ELEMENT_TO_Z.get(symbol) if isinstance(symbol, str) else None
        if z is None:
            raise _refuse_atom(
                atom_id, f"bound element '{symbol}' is not a pure element symbol"
            )
        if label == symbol:
            return _LabelPlan(atomic_number=z)
        if symbol == "H" and _is_identifier_hydrogen(label):
            return _LabelPlan(atomic_number=z, check_glyphs=True)
        raise _refuse_atom(
            atom_id, f"label '{label}' does not match bound element '{symbol}'"
        )
    if binding.meaning in ("generic_aryl", "aryl_fragment"):
        if label not in _AMBIGUOUS_ELEMENT_LABELS:
            raise _refuse_atom(
                atom_id,
                f"an aryl binding applies only to the label 'Ar', not '{label}'",
            )
        if binding.meaning == "generic_aryl":
            neighbor_id = _check_generic_aryl_connections(model, atom_id)
            return _LabelPlan(generic_nickname="ARY", neighbor_id=neighbor_id)
        fragment = binding.fragment
        definition = _bound_aryl_definition(fragment) if type(fragment) is str else None
        if fragment is None or definition is None or not definition.aryl:
            raise _refuse_atom(
                atom_id,
                f"bound fragment {fragment!r} has no verified aryl fragment definition",
            )
        return _LabelPlan(
            fragment=fragment,
            neighbor_id=_group_label_attachment(model, atom_id, label, label_bindings),
        )
    if binding.meaning == "aryl_label":
        if label != "Ar":
            raise _refuse_atom(
                atom_id,
                f"an aryl_label binding applies only to the label 'Ar', not '{label}'",
            )
        note = binding.author_note
        if type(note) is not str or not note:
            raise _refuse_atom(
                atom_id,
                "aryl_label binding needs a non-empty author_note string",
            )
        _validate_xml_text(note, "atom", str(atom_id))
        annotation = model.atom_annotation_for(atom_id) or {}
        if annotation.get("formal_charge", 0) != 0:
            raise _refuse_atom(
                atom_id,
                "aryl_label export refuses atoms with a formal charge annotation",
            )
        if annotation.get("radical_electrons", 0) != 0:
            raise _refuse_atom(
                atom_id,
                "aryl_label export refuses atoms with a radical annotation",
            )
        return _LabelPlan(documentary_aryl_note=note)
    raise _refuse_atom(atom_id, f"unknown label binding meaning {binding.meaning!r}")


# Each binding meaning names the one field it needs; the other must be absent.
_BINDING_FIELDS: Mapping[str, tuple[str, ...]] = {
    "element": ("element",),
    "generic_aryl": (),
    "aryl_fragment": ("fragment",),
    "aryl_label": ("author_note",),
}


def _check_binding_fields(atom_id: int, binding: CdxmlLabelBinding) -> None:
    """Refuse a binding whose fields contradict or do not fit its meaning.

    A binding is the caller's explicit statement of meaning, so a field that
    the meaning does not use, a missing field, or a value that is not exactly
    a ``str`` is refused rather than dropped or converted.
    """
    meaning = binding.meaning
    if type(meaning) is not str or meaning not in _BINDING_FIELDS:
        raise _refuse_atom(atom_id, f"unknown label binding meaning {meaning!r}")
    required = _BINDING_FIELDS[meaning]
    for field_name in ("element", "fragment", "author_note"):
        value = getattr(binding, field_name)
        if field_name not in required:
            if value is not None:
                raise _refuse_atom(
                    atom_id,
                    f"label binding '{meaning}' takes no {field_name} field "
                    f"(got {value!r}); conflicting or extra fields are refused",
                )
        elif type(value) is not str:
            raise _refuse_atom(
                atom_id,
                f"label binding '{meaning}' needs its {field_name} field as a str, "
                f"got {type(value).__name__} {value!r}",
            )
        elif not value:
            raise _refuse_atom(
                atom_id,
                f"label binding '{meaning}' needs a non-empty {field_name} string",
            )


def _require_supported_element_neighbor(
    model: MoleculeModel,
    neighbor_id: int,
    group_atom_id: int,
    group_label: str,
    label_bindings: LabelBindings | None,
) -> None:
    """Refuse unless ``neighbor_id`` is an unbound supported element export."""
    neighbor = model.atoms.get(neighbor_id)
    if neighbor is None or neighbor_id == group_atom_id:
        raise _refuse_atom(
            group_atom_id,
            f"group label '{group_label}' has no drawable attachment direction",
        )
    if label_bindings and neighbor_id in label_bindings:
        raise _refuse_atom(
            group_atom_id,
            f"group label '{group_label}' is attached through a stereo bond to "
            f"atom {neighbor_id}, which carries a typed label binding; only an "
            "unbound supported element symbol at bond.a is accepted for this batch",
        )
    plan = _resolve_label_plan(model, neighbor_id, None)
    if plan.atomic_number is None:
        raise _refuse_atom(
            group_atom_id,
            f"group label '{group_label}' is attached through a stereo bond "
            f"to atom {neighbor_id}, which does not export as a pure element",
        )


_BOUND_4F_PH_FRAGMENT = "4-F-Ph"


def _is_bound_para_fluorophenyl_aryl(
    atom_id: int,
    label: str,
    label_bindings: LabelBindings | None,
) -> bool:
    """True only for drawn ``Ar`` with ``aryl_fragment('4-F-Ph')`` on ``atom_id``."""
    if label != "Ar" or label_bindings is None:
        return False
    binding = label_bindings.get(atom_id)
    if not isinstance(binding, CdxmlLabelBinding):
        return False
    if binding.meaning != "aryl_fragment" or binding.fragment != _BOUND_4F_PH_FRAGMENT:
        return False
    definition = _bound_aryl_definition(_BOUND_4F_PH_FRAGMENT)
    return definition is not None and definition.aryl


def _check_generic_aryl_connections(model: MoleculeModel, atom_id: int) -> int | None:
    """Validate the explicit generic aryl binding and its shared attachment.

    The visible Ar nickname contains the documented ARY query, never argon.
    The source node remains the endpoint of each outer bond.
    """
    attached = [
        (bond_id, bond)
        for bond_id, bond in enumerate(model.bonds)
        if bond is not None and atom_id in (bond.a, bond.b)
    ]
    if len(attached) > 2:
        raise _refuse_atom(atom_id, "generic aryl supports at most two connections")
    annotation = model.atom_annotation_for(atom_id) or {}
    if any(annotation.get(key, 0) for key in ("formal_charge", "radical_electrons")):
        raise _refuse_atom(
            atom_id, "group label 'Ar' has a charge or radical annotation"
        )
    for bond_id, bond in attached:
        if (
            type(bond.order) is not int
            or bond.order != 1
            or bond.style not in {"single", "wedge", "hash", "dotted"}
        ):
            raise _refuse_atom(
                atom_id,
                f"group label 'Ar' is attached by bond {bond_id} with order "
                f"{bond.order} and style '{bond.style}'; only exact integer order 1 "
                "single, wedge, hash or dotted connections are supported",
            )
        _bond_axis(model, bond, bond_id)
    if not attached:
        return None
    bond = attached[0][1]
    return bond.b if bond.a == atom_id else bond.a


def _group_label_attachment(
    model: MoleculeModel,
    atom_id: int,
    label: str,
    label_bindings: LabelBindings | None = None,
) -> int:
    """The neighbour of a contracted group label, or refuse.

    A group label stands for a fixed set of electrons and one connection
    point, so it needs exactly one attachment bond and no charge or radical
    annotation. The connection point is never guessed.

    Unbound ``Ph`` and bound ``Ar`` with ``aryl_fragment('4-F-Ph')`` may attach
    through one order-1 wedge or hash bond only at the wide end (``bond.b``);
    the narrow stereocentre at ``bond.a`` must be an unbound supported pure
    element (no typed label binding on ``bond.a``). Other fixed ``Ar`` fragments,
    ``Me`` and ``tBu`` still require a plain single bond. Generic aryl uses
    _check_generic_aryl_connections instead; it is a query, not a fixed fragment.
    """
    attached = [
        (bond_id, bond)
        for bond_id, bond in enumerate(model.bonds)
        if bond is not None and atom_id in (bond.a, bond.b)
    ]
    if len(attached) != 1:
        raise _refuse_atom(
            atom_id,
            f"group label '{label}' needs exactly one attachment bond, found "
            f"{len(attached)}; multiple or missing attachments have no verified "
            "connection points",
        )
    bond_id, bond = attached[0]
    annotation = model.atom_annotation_for(atom_id) or {}
    if any(annotation.get(key, 0) for key in ("formal_charge", "radical_electrons")):
        raise _refuse_atom(
            atom_id,
            f"group label '{label}' has a charge or radical annotation, which "
            "conflicts with the fixed electron count of the group",
        )

    if label == "Ph" and bond.style in _STEREO_DISPLAY and bond.order == 1:
        if atom_id != bond.b:
            raise _refuse_atom(
                atom_id,
                f"group label 'Ph' on bond {bond_id} must sit at the wide end "
                f"(bond.b); the narrow stereocentre stays at bond.a",
            )
        atom, neighbor = model.atoms[atom_id], model.atoms.get(bond.a)
        if (
            neighbor is None
            or math.hypot(atom.x - neighbor.x, atom.y - neighbor.y) <= 1e-9
        ):
            raise _refuse_atom(
                atom_id,
                f"group label '{label}' has no drawable attachment direction",
            )
        _require_supported_element_neighbor(
            model, bond.a, atom_id, label, label_bindings
        )
        return bond.a

    if (
        label == "Ar"
        and bond.style in _STEREO_DISPLAY
        and bond.order == 1
        and _is_bound_para_fluorophenyl_aryl(atom_id, label, label_bindings)
    ):
        if atom_id != bond.b:
            raise _refuse_atom(
                atom_id,
                f"group label 'Ar' on bond {bond_id} must sit at the wide end "
                f"(bond.b); the narrow stereocentre stays at bond.a",
            )
        atom, neighbor = model.atoms[atom_id], model.atoms.get(bond.a)
        if (
            neighbor is None
            or math.hypot(atom.x - neighbor.x, atom.y - neighbor.y) <= 1e-9
        ):
            raise _refuse_atom(
                atom_id,
                f"group label '{label}' has no drawable attachment direction",
            )
        _require_supported_element_neighbor(
            model, bond.a, atom_id, label, label_bindings
        )
        return bond.a

    if bond.order != 1 or bond.style != "single":
        raise _refuse_atom(
            atom_id,
            f"group label '{label}' is attached by bond {bond_id} with order "
            f"{bond.order} and style '{bond.style}'; only an ordinary single "
            "attachment bond is supported (no double, triple, wedge or hash)",
        )
    neighbor_id = bond.b if bond.a == atom_id else bond.a
    atom, neighbor = model.atoms[atom_id], model.atoms.get(neighbor_id)
    if (
        neighbor is None
        or neighbor_id == atom_id
        or math.hypot(atom.x - neighbor.x, atom.y - neighbor.y) <= 1e-9
    ):
        raise _refuse_atom(
            atom_id,
            f"group label '{label}' has no drawable attachment direction",
        )
    return neighbor_id


def _check_label_bindings(
    model: MoleculeModel,
    label_bindings: LabelBindings | None,
) -> None:
    for atom_id in label_bindings or {}:
        if atom_id not in model.atoms:
            raise _refuse_atom(
                atom_id,
                "label binding refers to an atom that is not in the document",
            )


def _check_atom_label_glyphs(
    context: SceneRenderContext,
    atom_id: int,
    label: str,
) -> None:
    from PyQt6.QtGui import QFontInfo

    atom_font = context.renderer.atom_font()
    _check_glyph_font_consistency(
        atom_font, QFontInfo(atom_font).family(), label, "atom", str(atom_id)
    )


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


def _check_atoms(
    context: SceneRenderContext,
    model: MoleculeModel,
    atom_ids_in_export: set[int],
    label_bindings: LabelBindings | None,
) -> None:
    """Preflight every exported atom's label meaning, annotation and glyphs."""
    _check_label_bindings(model, label_bindings)
    for atom_id, atom in model.atoms.items():
        if atom_id not in atom_ids_in_export:
            continue
        label_plan = _resolve_label_plan(model, atom_id, label_bindings)
        annotation = model.atom_annotation_for(atom_id)
        _check_atom_annotation(atom_id, annotation)
        if label_plan.check_glyphs:
            _check_atom_label_glyphs(context, atom_id, atom.element)


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


def _note_rotation_angle(transform: QTransform, object_id: str) -> int:
    values = (transform.m11(), transform.m12(), transform.m21(), transform.m22())
    x_length = math.hypot(values[0], values[1])
    y_length = math.hypot(values[2], values[3])
    dot = values[0] * values[2] + values[1] * values[3]
    determinant = values[0] * values[3] - values[1] * values[2]
    if (
        not transform.isAffine()
        or not all(math.isfinite(value) for value in values)
        or x_length <= 0
        or determinant <= 0
        or not math.isclose(x_length, y_length, rel_tol=1e-6)
        or not math.isclose(dot / (x_length * y_length), 0.0, abs_tol=1e-6)
    ):
        raise CdxmlUnsupportedObjectError(
            "note",
            object_id,
            "non-conformal or projective transform is not supported",
        )
    return round(math.degrees(math.atan2(transform.m12(), transform.m11())) * 65536)


def _check_note_formatting(
    context: SceneRenderContext,
    item: object,
    index: int,
) -> None:
    from PyQt6.QtWidgets import QGraphicsTextItem

    if not isinstance(item, QGraphicsTextItem):
        raise CdxmlUnsupportedObjectError("note", str(index), "note is not a text item")

    transform = item.sceneTransform()
    _note_rotation_angle(transform, str(index))

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
        if va not in (
            QTextCharFormat.VerticalAlignment.AlignNormal,
            QTextCharFormat.VerticalAlignment.AlignSubScript,
            QTextCharFormat.VerticalAlignment.AlignSuperScript,
        ):
            raise CdxmlUnsupportedObjectError(
                "note", str(index), "text vertical alignment is not supported"
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


def _ring_fill_paints(item: QGraphicsItem) -> bool:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QAbstractGraphicsShapeItem

    if not isinstance(item, QAbstractGraphicsShapeItem):
        return True
    if item.effectiveOpacity() <= 0.0:
        return False
    pen, brush = item.pen(), item.brush()
    has_stroke = pen.style() != Qt.PenStyle.NoPen and pen.color().alpha() > 0
    has_fill = brush.style() != Qt.BrushStyle.NoBrush and brush.color().alpha() > 0
    return has_stroke or has_fill


def _text_ink_bounds(item: QGraphicsItem) -> QRectF:
    from PyQt6.QtWidgets import QGraphicsTextItem

    from chemvas.ui.canvas.graphics_items import AtomLabelItem, note_paint_scene_path

    if isinstance(item, AtomLabelItem):
        return item.export_scene_bounding_rect()
    if isinstance(item, QGraphicsTextItem):
        return note_paint_scene_path(item).boundingRect()
    return item_export_bounds(item)


def _painted_bounds(item: QGraphicsItem) -> QRectF:
    from PyQt6.QtGui import QPainterPath, QPainterPathStroker
    from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsTextItem

    if isinstance(item, QGraphicsTextItem):
        return _text_ink_bounds(item)
    if isinstance(item, QGraphicsLineItem):
        path = QPainterPath()
        path.moveTo(item.line().p1())
        path.lineTo(item.line().p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(item.pen().widthF())
        stroker.setCapStyle(item.pen().capStyle())
        stroker.setJoinStyle(item.pen().joinStyle())
        return item.sceneTransform().map(stroker.createStroke(path)).boundingRect()
    return item_export_bounds(item)


def _validated_attached_marks(
    context: SceneRenderContext,
    export_items: list[QGraphicsItem],
    chemical_atom_ids: frozenset[int] | set[int],
) -> dict[int, list[QGraphicsTextItem]]:
    from PyQt6.QtWidgets import QGraphicsTextItem

    by_atom: dict[int, list[QGraphicsTextItem]] = {}
    for item in export_items:
        if item.data(0) != "mark" or not item.isVisible():
            continue
        metadata = item.data(1)
        object_id = str(item.data(3) or "?")
        if not isinstance(metadata, dict) or metadata.get("kind") not in (
            "plus",
            "minus",
        ):
            raise CdxmlUnsupportedObjectError(
                "mark",
                object_id,
                "only atom-attached plus/minus text marks have a proved mapping",
            )
        owner = metadata.get("atom_id")
        if type(owner) is not int or owner not in chemical_atom_ids:
            raise CdxmlUnsupportedObjectError(
                "mark",
                object_id,
                "mark owner must be a chemical node in the export set",
            )
        expected = "+" if metadata["kind"] == "plus" else "-"
        if not isinstance(item, QGraphicsTextItem) or item.toPlainText() != expected:
            raise CdxmlUnsupportedObjectError(
                "mark", object_id, "mark does not paint its recorded plus/minus glyph"
            )
        transform = item.sceneTransform()
        values = (
            transform.m11(),
            transform.m12(),
            transform.m21(),
            transform.m22(),
            transform.dx(),
            transform.dy(),
        )
        if (
            not all(math.isfinite(value) for value in values)
            or _finite_rect(_text_ink_bounds(item)) is None
        ):
            raise CdxmlUnsupportedObjectError(
                "mark", object_id, "mark glyph geometry must be finite"
            )
        _check_note_formatting(context, item, int(item.data(3) or 0))
        by_atom.setdefault(owner, []).append(item)
    return by_atom


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
            continue  # Validated against its exported owner before role checks.
        if role == "ring":
            # Ring tools record each ring with a transparent fill by default;
            # that record paints nothing and its bonds carry the structure.
            if _ring_fill_paints(item):
                raise CdxmlUnsupportedObjectError(
                    "ring_fill",
                    str(item.data(3) or "?"),
                    "visible ring fills have no proved CDXML mapping",
                )
            continue
        if role in ("atom", "bond", "shape", "note", "note_box", "ts_bracket"):
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


# ── TS bracket contact geometry ─────────────────────────────────────
# A square TS bracket item paints the outline QPainterPathStroker builds from
# ``bracket_path_commands``: width ``bracket_stroke_width(bond_line_width)``,
# flat caps and mitre joins. Its segments are axis-aligned and each join is a
# right angle, so the painted area is exactly a union of axis-aligned
# rectangles (a join adds the half-width square the mitre fills). The
# fragment-interleave rule compares these rectangles, not the bracket's
# bounding rect, with each fragment item's bounding rect. A CDXML Line leaves
# its end caps to the consumer, so every free end is also lengthened by half
# the width (a square cap, the widest a consumer draws). Touching counts as
# contact. Whatever cannot be fixed exactly returns None and the bracket keeps
# the bounding-rect rule.

_Rect = tuple[float, float, float, float]  # left, top, right, bottom


def _polyline_stroke_rects(
    points: Sequence[tuple[float, float]], half: float, *, consumer_caps: bool
) -> list[_Rect] | None:
    last = len(points) - 2
    rects: list[_Rect] = []
    previous_vertical: bool | None = None
    for i, ((x1, y1), (x2, y2)) in enumerate(pairwise(points)):
        vertical = x1 == x2
        if vertical == (y1 == y2) or vertical == previous_vertical:
            # Zero-length, diagonal or not a right-angle join.
            return None
        previous_vertical = vertical
        start = half if i > 0 or consumer_caps else 0.0
        end = half if i < last or consumer_caps else 0.0
        a, b, c = (y1, y2, x1) if vertical else (x1, x2, y1)
        lo, hi = (a - start, b + end) if a < b else (b - end, a + start)
        if vertical:
            rects.append((c - half, lo, c + half, hi))
        else:
            rects.append((lo, c - half, hi, c + half))
    return rects or None


def _square_bracket_stroke_rects(
    commands: Sequence[tuple[str, tuple[float, ...]]],
    width: float,
    *,
    consumer_caps: bool,
) -> list[_Rect] | None:
    half = width / 2.0
    if not math.isfinite(half) or half <= 0.0:
        return None
    polylines: list[list[tuple[float, float]]] = []
    for cmd, args in commands:
        if cmd not in ("M", "L") or len(args) != 2:
            return None
        if not all(math.isfinite(v) for v in args):
            return None
        if cmd == "M":
            polylines.append([])
        elif not polylines:
            return None
        polylines[-1].append((args[0], args[1]))
    rects: list[_Rect] = []
    for points in polylines:
        piece = _polyline_stroke_rects(points, half, consumer_caps=consumer_caps)
        if piece is None:
            return None
        rects.extend(piece)
    return rects or None


def _uniform_scale_offset(transform: QTransform) -> tuple[float, float, float] | None:
    k = transform.m11()
    values = (
        k,
        transform.m12(),
        transform.m13(),
        transform.m21(),
        transform.m22(),
        transform.m23(),
        transform.m31(),
        transform.m32(),
        transform.m33(),
    )
    if not all(math.isfinite(v) for v in values):
        return None
    if values[1:4] != (0.0, 0.0, 0.0) or values[5] != 0.0 or values[8] != 1.0:
        return None
    if k <= 0.0 or values[4] != k:
        return None
    return k, values[6], values[7]


def _finite_rect(rect: QRectF) -> _Rect | None:
    values = (rect.left(), rect.top(), rect.right(), rect.bottom())
    if not all(math.isfinite(v) for v in values):
        return None
    if values[2] < values[0] or values[3] < values[1]:
        return None
    return values


def _closed_rects_touch(a: _Rect, b: _Rect) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _rects_span_matches(rects: Sequence[_Rect], bounds: _Rect) -> bool:
    span = (
        min(r[0] for r in rects),
        min(r[1] for r in rects),
        max(r[2] for r in rects),
        max(r[3] for r in rects),
    )
    tol = 1e-6 * max(1.0, *(abs(v) for v in bounds))
    return all(abs(p - q) <= tol for p, q in zip(span, bounds, strict=True))


def _ts_bracket_contact_rects(
    context: SceneRenderContext, item: QGraphicsItem
) -> list[_Rect] | None:
    from PyQt6.QtWidgets import QGraphicsPathItem

    rec_id = item.data(3)
    records = context.state.ts_bracket_state.records
    record = records.get(rec_id) if type(rec_id) is int else None
    if record is None or record.bracket_kind not in _SQUARE_BRACKET_KINDS:
        return None
    if not isinstance(item, QGraphicsPathItem):
        return None
    mapping = _uniform_scale_offset(item.sceneTransform())
    painted_bounds = _finite_rect(item.sceneBoundingRect())
    if mapping is None or painted_bounds is None:
        return None
    style = context.renderer.style
    commands = bracket_path_commands(
        _ts_bracket_bounds(record), record.bracket_kind, style.bond_length_px
    )
    width = bracket_stroke_width(style.bond_line_width)
    painted = _square_bracket_stroke_rects(commands, width, consumer_caps=False)
    reach = _square_bracket_stroke_rects(commands, width, consumer_caps=True)
    if painted is None or reach is None:
        return None
    k, dx, dy = mapping

    def to_scene(rects: list[_Rect]) -> list[_Rect]:
        return [
            (k * a + dx, k * b + dy, k * c + dx, k * d + dy) for a, b, c, d in rects
        ]

    # The rectangles must span exactly what the item paints in the scene.
    if not _rects_span_matches(to_scene(painted), painted_bounds):
        return None
    return to_scene(reach)


def _ts_bracket_reach(
    context: SceneRenderContext, export_items: list[QGraphicsItem]
) -> dict[int, list[_Rect]]:
    reach: dict[int, list[_Rect]] = {}
    for item in export_items:
        if item.data(0) == "ts_bracket" and item.isVisible():
            rects = _ts_bracket_contact_rects(context, item)
            if rects is not None:
                reach[id(item)] = rects
    return reach


def _item_touches(
    item_bounds: QRectF, reach: list[_Rect] | None, frag_bounds: QRectF
) -> bool:
    if reach is None:
        return item_bounds.intersects(frag_bounds)
    frag = _finite_rect(frag_bounds)
    return frag is None or any(_closed_rects_touch(r, frag) for r in reach)


# ── Fragment interleaving check ─────────────────────────────────────


def _atom_scene_rank_map(
    context: SceneRenderContext, scene_rank: Mapping[int, int]
) -> dict[int, int]:
    atom_rank_map: dict[int, int] = {}
    for item in context.scene.items():
        if item.data(0) == "atom":
            aid = item.data(1)
            if isinstance(aid, int):
                atom_rank_map[aid] = scene_rank.get(id(item), 0)

    return atom_rank_map


def _check_item_fragment_interleave(
    export_items: list[QGraphicsItem],
    frag_ranges: list[tuple[int, int, int]],
    frag_items: dict[int, list[QGraphicsItem]],
    scene_pos: dict[int, int],
    export_set: set[QGraphicsItem],
    bracket_reach: Mapping[int, list[_Rect]],
    frag_anchor_ranks: Mapping[int, int],
    *,
    documentary_caption_aryl_ids: frozenset[int] = frozenset(),
    documentary_bond_ids: frozenset[int] = frozenset(),
) -> None:
    non_frag_roles = frozenset(
        {"note", "arrow", "line", "line_dashed", "shape", "ts_bracket", "mark"}
    )
    for item in export_items:
        role = item.data(0)
        if not item.isVisible():
            continue
        if role == "atom":
            aid = item.data(1)
            if not isinstance(aid, int) or aid not in documentary_caption_aryl_ids:
                continue
            role_key = "aryl_label_caption"
        elif role == "bond" and item.data(1) in documentary_bond_ids:
            role_key = "documentary_contact"
        elif role not in non_frag_roles:
            continue
        else:
            role_key = str(role)
        item_rank = scene_pos.get(id(item), -1)
        item_bounds = (
            _text_ink_bounds(item)
            if role in {"mark", "note"}
            else item.sceneBoundingRect()
        )
        reach = bracket_reach.get(id(item))
        for frag_min, frag_max, comp_idx in frag_ranges:
            if frag_min < item_rank < frag_max:
                for frag_item in frag_items.get(comp_idx, []):
                    frag_bounds = (
                        _painted_bounds(frag_item)
                        if role in {"mark", "note"}
                        or frag_item.data(0) == "mark"
                        or reach is not None
                        else frag_item.sceneBoundingRect()
                    )
                    if (
                        frag_item is not item
                        and frag_item in export_set
                        and _item_touches(item_bounds, reach, frag_bounds)
                    ):
                        if reach is not None and (
                            scene_pos.get(id(frag_item), -1) < item_rank
                        ) == (frag_anchor_ranks[comp_idx] < item_rank):
                            # The contacting ink retains its side of the bracket
                            # when the fragment is placed at its top atom rank.
                            continue
                        raise CdxmlUnsupportedObjectError(
                            role_key,
                            str(item.data(3) or item.data(1) or "?"),
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
                    bi = _painted_bounds(it_i)
                    for it_j in frag_items.get(comp_j, []):
                        bj = _painted_bounds(it_j)
                        if bi.intersects(bj):
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
    *,
    documentary_bond_ids: frozenset[int] = frozenset(),
    documentary_caption_aryl_ids: frozenset[int] = frozenset(),
) -> None:
    from PyQt6.QtCore import Qt as QtCore_Qt

    model = context.model
    bond_pairs = _bond_pairs_for_export(model, atom_ids_in_export, documentary_bond_ids)
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
            if isinstance(bid, int) and bid in documentary_bond_ids:
                continue
            if isinstance(bid, int) and 0 <= bid < len(model.bonds):
                bond = model.bonds[bid]
                if bond is not None and bond.a in atom_to_comp:
                    frag_items.setdefault(atom_to_comp[bond.a], []).append(item)

    for item in export_items:
        if item.data(0) == "mark" and item.isVisible():
            owner = item.data(1).get("atom_id")
            if owner in atom_to_comp:
                frag_items.setdefault(atom_to_comp[owner], []).append(item)

    # A child objecttag paints with its node in the consumer. Its source rank
    # cannot be retained independently: refuse any overlapping fragment ink,
    # including when the source mark lies outside the fragment's rank range.
    for item in export_items:
        if item.data(0) != "mark" or not item.isVisible():
            continue
        owner = item.data(1).get("atom_id")
        mark_comp_idx = atom_to_comp.get(owner)
        if mark_comp_idx is None:
            continue
        ink = _text_ink_bounds(item)
        for fragment_item in frag_items.get(mark_comp_idx, []):
            if (
                fragment_item is not item
                and fragment_item in export_items
                and ink.intersects(_painted_bounds(fragment_item))
            ):
                raise CdxmlUnsupportedObjectError(
                    "mark",
                    str(item.data(3) or "?"),
                    "mark ink interleaves with fragment paint; child objecttag has no independently proved paint order",
                )

    if not frag_items:
        return

    scene_order = list(context.scene.items(QtCore_Qt.SortOrder.AscendingOrder))
    scene_pos = {id(it): i for i, it in enumerate(scene_order)}

    frag_ranges: list[tuple[int, int, int]] = []
    for comp_idx, items_list in frag_items.items():
        ranks = [scene_pos.get(id(it), 0) for it in items_list]
        if ranks:
            frag_ranges.append((min(ranks), max(ranks), comp_idx))

    atom_ranks = _atom_scene_rank_map(context, scene_pos)
    frag_anchor_ranks = {
        index: max(atom_ranks.get(aid, 0) for aid in component)
        for index, component in enumerate(components)
    }
    export_set = set(export_items)
    _check_item_fragment_interleave(
        export_items,
        frag_ranges,
        frag_items,
        scene_pos,
        export_set,
        _ts_bracket_reach(context, export_items),
        frag_anchor_ranks,
        documentary_bond_ids=documentary_bond_ids,
        documentary_caption_aryl_ids=documentary_caption_aryl_ids,
    )
    _check_fragment_pair_interleave(frag_ranges, frag_items)


def _chemvas_objecttag_name(suffix: str) -> str:
    if suffix.startswith(_CHEMVAS_OBJECTTAG_PREFIX):
        return suffix
    return f"{_CHEMVAS_OBJECTTAG_PREFIX}{suffix}"


def _add_chemvas_string_objecttag(
    parent: ET.Element,
    name: str,
    value: str,
) -> None:
    tag = ET.SubElement(parent, "objecttag")
    tag.set("Name", _chemvas_objecttag_name(name))
    tag.set("TagType", "String")
    tag.set("Persistent", "yes")
    tag.set("Tracking", "no")
    tag.set("Value", _validate_xml_text(value, "objecttag", name))


def _documentary_contact_value(contact: CdxmlDocumentaryContact) -> str:
    lines = [
        f"classification={contact.classification}",
        f"bond_id={contact.bond_id}",
        f"a={contact.a}",
        f"b={contact.b}",
        f"native_order={contact.native_order}",
        f"native_style={contact.native_style}",
        "chemical_meaning=unspecified",
    ]
    if contact.contact_id is not None:
        lines.append(f"contact_id={contact.contact_id}")
    return "\n".join(lines)


def _aryl_label_atom_ids(label_bindings: LabelBindings | None) -> set[int]:
    if not label_bindings:
        return set()
    return {
        atom_id
        for atom_id, binding in label_bindings.items()
        if binding.meaning == "aryl_label"
    }


def _documentary_caption_atom_ids(
    label_bindings: LabelBindings | None,
    atom_ids_in_export: set[int],
) -> frozenset[int]:
    if not label_bindings:
        return frozenset()
    return frozenset(
        atom_id
        for atom_id in _aryl_label_atom_ids(label_bindings)
        if atom_id in atom_ids_in_export
    )


def _check_documentary_aryl_caption_chemical_degree(
    model: MoleculeModel,
    caption_aryl_ids: frozenset[int],
    documentary_bond_ids: frozenset[int],
) -> None:
    for aryl_id in caption_aryl_ids:
        for bond_id, bond in enumerate(model.bonds):
            if bond is None:
                continue
            if bond_id in documentary_bond_ids:
                continue
            if aryl_id not in (bond.a, bond.b):
                continue
            raise CdxmlUnsupportedObjectError(
                "atom",
                str(aryl_id),
                "aryl_label export refuses any non-documentary bond on Ar; "
                "page captions cannot retain native <b> encoding or omit "
                "bonds that still exist in the document",
            )


@dataclass(frozen=True)
class _CdxmlCaptionExportLayout:
    caption_aryl_ids: frozenset[int]
    chemical_atom_ids: set[int]
    documentary_bond_ids: frozenset[int]
    authorized_contacts: tuple[CdxmlDocumentaryContact, ...]
    components: tuple[tuple[int, ...], ...]


def _cdxml_caption_export_layout(
    model: MoleculeModel,
    atom_ids_in_export: set[int],
    label_bindings: LabelBindings | None,
    documentary_contacts: DocumentaryContacts | None,
) -> _CdxmlCaptionExportLayout:
    documentary_bond_ids, authorized_contacts = _validated_documentary_plan(
        model,
        atom_ids_in_export,
        label_bindings,
        documentary_contacts,
    )
    caption_aryl_ids = _documentary_caption_atom_ids(
        label_bindings,
        atom_ids_in_export,
    )
    _check_documentary_aryl_caption_chemical_degree(
        model,
        caption_aryl_ids,
        documentary_bond_ids,
    )
    chemical_atom_ids = atom_ids_in_export - set(caption_aryl_ids)
    bond_pairs = _bond_pairs_for_export(
        model,
        chemical_atom_ids,
        documentary_bond_ids,
    )
    components = connected_atom_components(chemical_atom_ids, bond_pairs)
    return _CdxmlCaptionExportLayout(
        caption_aryl_ids=caption_aryl_ids,
        chemical_atom_ids=chemical_atom_ids,
        documentary_bond_ids=documentary_bond_ids,
        authorized_contacts=authorized_contacts,
        components=components,
    )


def _collect_aryl_label_caption_z_elements(
    context: SceneRenderContext,
    caption_aryl_ids: frozenset[int],
    label_bindings: LabelBindings,
    scene_rank: dict[int, int],
    ids: _IdAllocator,
    fonts: _FontTable,
    colors: _ColorTable,
    scale: float,
    ox: float,
    oy: float,
) -> list[tuple[int, ET.Element]]:
    z_elements: list[tuple[int, ET.Element]] = []
    for atom_id in sorted(caption_aryl_ids):
        binding = label_bindings.get(atom_id)
        if binding is None or binding.meaning != "aryl_label":
            continue
        note = binding.author_note
        if type(note) is not str or not note:
            raise CdxmlUnsupportedObjectError(
                "atom",
                str(atom_id),
                "aryl_label binding needs a non-empty author_note string",
            )
        caption_el = _emit_documentary_aryl_caption(
            context,
            atom_id,
            note,
            ids,
            fonts,
            colors,
            scale,
            ox,
            oy,
        )
        atom_item = context.state.atom_graphics_state.atom_items.get(atom_id)
        caption_rank = scene_rank.get(id(atom_item), 0) if atom_item is not None else 0
        z_elements.append((caption_rank, caption_el))
    return z_elements


def _collect_documentary_contact_z_elements(
    context: SceneRenderContext,
    model: MoleculeModel,
    documentary_bond_ids: frozenset[int],
    contact_by_bond: Mapping[int, CdxmlDocumentaryContact],
    scene_rank: dict[int, int],
    ids: _IdAllocator,
    colors: _ColorTable,
    scale: float,
    ox: float,
    oy: float,
    line_width_scaled: float,
    bond_color_hex: str,
) -> list[tuple[int, ET.Element]]:
    z_elements: list[tuple[int, ET.Element]] = []
    for bond_id in sorted(documentary_bond_ids):
        bond = model.bonds[bond_id]
        assert bond is not None
        contact = contact_by_bond[bond_id]
        graphic = _emit_documentary_contact_line(
            model,
            bond,
            contact,
            ids,
            colors,
            scale,
            ox,
            oy,
            line_width_scaled,
            bond_color_hex,
        )
        z_elements.append((_bond_scene_rank(context, bond_id, scene_rank), graphic))
    return z_elements


def _documentary_aryl_caption_metadata(atom_id: int) -> str:
    return "\n".join(
        [
            f"atom_id={atom_id}",
            "expected_label=Ar",
            "meaning=aryl_label",
            "unexpanded_aryl_label=yes",
            "chemical_atom_identity=none",
            "automatic_tracking=no",
        ]
    )


def _validated_documentary_plan(
    model: MoleculeModel,
    atom_ids_in_export: set[int],
    label_bindings: LabelBindings | None,
    documentary_contacts: DocumentaryContacts | None,
) -> tuple[frozenset[int], tuple[CdxmlDocumentaryContact, ...]]:
    if not documentary_contacts:
        return frozenset(), ()
    if type(documentary_contacts) not in (tuple, list):
        raise CdxmlUnsupportedObjectError(
            "documentary_contacts",
            "sidecar",
            "documentary_contacts must be a sequence of contact records",
        )
    aryl_ids = _aryl_label_atom_ids(label_bindings)
    if not aryl_ids:
        raise CdxmlUnsupportedObjectError(
            "documentary_contacts",
            "sidecar",
            "documentary_contacts require at least one aryl_label binding on Ar",
        )
    permitted: set[int] = set()
    authorized: list[CdxmlDocumentaryContact] = []
    for index, contact in enumerate(documentary_contacts):
        where = f"documentary_contacts[{index}]"
        try:
            contact = authorize_documentary_contact_for_export(contact, where=where)
        except ValueError as exc:
            raise CdxmlUnsupportedObjectError(
                "documentary_contacts",
                str(index),
                str(exc),
            ) from exc
        if contact.contact_id is not None:
            _validate_xml_text(
                contact.contact_id, "documentary_contact", str(contact.bond_id)
            )
        bond = model.bond_for_id(contact.bond_id)
        if bond is None:
            raise CdxmlUnsupportedObjectError(
                "documentary_contacts",
                str(contact.bond_id),
                f"bond_id {contact.bond_id} does not match a bond in the document",
            )
        if (bond.a, bond.b) != (contact.a, contact.b):
            raise CdxmlUnsupportedObjectError(
                "documentary_contacts",
                str(contact.bond_id),
                "documentary contact endpoints do not match the document bond",
            )
        if bond.order != contact.native_order or bond.style != contact.native_style:
            raise CdxmlUnsupportedObjectError(
                "bond",
                str(contact.bond_id),
                "documentary contact native_order or native_style does not match "
                "the document bond",
            )
        if bond.order != 1 or bond.style != "dotted":
            raise CdxmlUnsupportedObjectError(
                "bond",
                str(contact.bond_id),
                "documentary contact permission applies only to native order-1 "
                "dotted bonds",
            )
        if bond.a not in atom_ids_in_export or bond.b not in atom_ids_in_export:
            raise CdxmlUnsupportedObjectError(
                "documentary_contacts",
                str(contact.bond_id),
                "documentary contact bond endpoints are hidden or outside the "
                "export scope",
            )
        _bond_axis(model, bond, contact.bond_id)
        if contact.a in aryl_ids and contact.b in aryl_ids:
            raise CdxmlUnsupportedObjectError(
                "documentary_contacts",
                str(contact.bond_id),
                "documentary contact must name exactly one aryl_label Ar endpoint",
            )
        if contact.a in aryl_ids:
            partner_id = contact.b
        elif contact.b in aryl_ids:
            partner_id = contact.a
        else:
            raise CdxmlUnsupportedObjectError(
                "documentary_contacts",
                str(contact.bond_id),
                "documentary contact must name exactly one aryl_label Ar endpoint",
            )
        partner_plan = _resolve_label_plan(model, partner_id, label_bindings)
        if partner_plan.atomic_number is None:
            raise CdxmlUnsupportedObjectError(
                "documentary_contacts",
                str(contact.bond_id),
                "the non-aryl documentary contact endpoint must export as a "
                "supported elemental identity",
            )
        permitted.add(contact.bond_id)
        authorized.append(contact)

    if len({contact.bond_id for contact in authorized}) != len(authorized):
        raise CdxmlUnsupportedObjectError(
            "documentary_contacts",
            "sidecar",
            "documentary_contacts repeats a bond_id",
        )

    return frozenset(permitted), tuple(authorized)


def _bond_pairs_for_export(
    model: MoleculeModel,
    atom_ids_in_export: set[int],
    documentary_bond_ids: frozenset[int],
) -> list[tuple[int, int]]:
    bond_pairs: list[tuple[int, int]] = []
    for bond_id, bond in enumerate(model.bonds):
        if bond is None:
            continue
        if bond_id in documentary_bond_ids:
            continue
        if bond.a in atom_ids_in_export and bond.b in atom_ids_in_export:
            bond_pairs.append((bond.a, bond.b))
    return bond_pairs


def _bond_scene_rank(
    context: SceneRenderContext,
    bond_id: int,
    scene_rank: dict[int, int],
) -> int:
    ranks = [
        scene_rank.get(id(item), 0)
        for item in context.state.bond_graphics_state.bond_items.get(bond_id) or []
    ]
    if ranks:
        return max(ranks)
    bond = context.model.bonds[bond_id]
    assert bond is not None
    atom_ranks = []
    for atom_id in (bond.a, bond.b):
        for item in context.scene.items():
            if item.data(0) == "atom" and item.data(1) == atom_id:
                atom_ranks.append(scene_rank.get(id(item), 0))
    return max(atom_ranks) if atom_ranks else 0


def _emit_documentary_contact_line(
    model: MoleculeModel,
    bond: Bond,
    contact: CdxmlDocumentaryContact,
    ids: _IdAllocator,
    colors: _ColorTable,
    s: float,
    ox: float,
    oy: float,
    line_width_scaled: float,
    bond_color_hex: str,
) -> ET.Element:
    ax = _scale_coord(model.atoms[bond.a].x, ox, s)
    ay = _scale_coord(model.atoms[bond.a].y, oy, s)
    bx = _scale_coord(model.atoms[bond.b].x, ox, s)
    by = _scale_coord(model.atoms[bond.b].y, oy, s)
    g = _line_element(ids, ax, ay, bx, by, line_width_scaled, "Dashed")
    effective_color = bond.color if bond.color != "#000000" else bond_color_hex
    if effective_color != "#000000":
        g.set("color", str(colors.reference(effective_color)))
    _add_chemvas_string_objecttag(
        g,
        "DocumentaryContact",
        _documentary_contact_value(contact),
    )
    return g


# ── Main preflight ───────────────────────────────────────────────────


def preflight_cdxml(
    context: SceneRenderContext,
    items: Sequence[QGraphicsItem],
    plan: ExportPlan,
    *,
    background: str = "white",
    groups: Mapping[int, SceneGroup] | None = None,
    label_bindings: LabelBindings | None = None,
    documentary_contacts: DocumentaryContacts | None = None,
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

    _check_atoms(context, model, atom_ids_in_export, label_bindings)
    export_layout = _cdxml_caption_export_layout(
        model,
        atom_ids_in_export,
        label_bindings,
        documentary_contacts,
    )
    documentary_bond_ids = export_layout.documentary_bond_ids
    _validated_attached_marks(context, export_items, export_layout.chemical_atom_ids)
    chemical_atom_ids = export_layout.chemical_atom_ids
    caption_aryl_ids = export_layout.caption_aryl_ids

    for bond_id, bond in enumerate(model.bonds):
        if bond is None:
            continue
        if bond_id in documentary_bond_ids:
            continue
        if bond.a not in atom_ids_in_export and bond.b not in atom_ids_in_export:
            continue
        if bond.a in atom_ids_in_export and bond.b in atom_ids_in_export:
            _resolved_bond_encoding(context, bond, bond_id)
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

    _check_ts_brackets(context, export_items, export_set)

    _preflight_roles(export_items)

    _check_fragment_interleaving(
        context,
        export_items,
        chemical_atom_ids,
        documentary_bond_ids=documentary_bond_ids,
        documentary_caption_aryl_ids=caption_aryl_ids,
    )

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


# ── Z order ───────────────────────────────────────────────────────────
# ZOrder.htm: CDXML ``Z`` (INT16, back-to-front) is a property of Node, Bond,
# Text, Graphic, Curve, EmbeddedObject, Table, NamedAlternativeGroup,
# Spectrum, TLCPlate and Arrow. A missing Z counts as 0 and objects sharing 0
# are arranged among themselves randomly. Group, Fragment and Page do not
# list it. Of the elements written here, every ``n``, ``b``, ``t`` and
# ``graphic`` therefore gets its own explicit positive Z and no container
# gets one. Page objects keep their scene-rank order (a molecule stays one
# fragment at its top atom rank, guarded by the interleave checks) and each
# takes one contiguous Z block; inside a fragment the atoms and bonds follow
# their own scene paint order, a node before its contracted group and label.

_Z_TAGS = frozenset({"n", "b", "t", "graphic", "arrow"})
_Z_MAX = 32767  # INT16


def _fragment_item_ranks(
    context: SceneRenderContext, scene_rank: dict[int, int]
) -> dict[tuple[str, int], list[int]]:
    ranks: dict[tuple[str, int], list[int]] = {}
    for item in context.scene.items():
        role = item.data(0)
        key = item.data(1)
        if role in ("atom", "bond") and isinstance(key, int):
            ranks.setdefault((role, key), []).append(scene_rank.get(id(item), 0))
    return ranks


def _paint_range(
    item_ranks: dict[tuple[str, int], list[int]], role: str, object_id: int
) -> tuple[int, int]:
    ranks = item_ranks.get((role, object_id))
    if not ranks:
        raise CdxmlUnsupportedObjectError(
            role,
            str(object_id),
            "no scene item paints this object, so its z-order cannot be fixed",
        )
    return min(ranks), max(ranks)


def _fragment_z_leaves(
    frag: ET.Element, paint_ranges: dict[int, tuple[int, int]]
) -> list[ET.Element]:
    children = list(frag)
    order = sorted(
        range(len(children)),
        key=lambda index: (*paint_ranges[id(children[index])], index),
    )
    top = -1
    leaves: list[ET.Element] = []
    for index in order:
        child = children[index]
        low, high = paint_ranges[id(child)]
        if low < top:
            raise CdxmlUnsupportedObjectError(
                "fragment",
                str(frag.get("id")),
                "an atom or bond's scene items are split by another atom or "
                "bond in z-order; one CDXML object has one Z",
            )
        top = max(top, high)
        leaves.extend(el for el in child.iter() if el.tag in _Z_TAGS)
    return leaves


def _assign_z(
    page_objects: Sequence[ET.Element], paint_ranges: dict[int, tuple[int, int]]
) -> None:
    leaves: list[ET.Element] = []
    for el in page_objects:
        if el.tag == "fragment":
            leaves.extend(_fragment_z_leaves(el, paint_ranges))
        else:
            leaves.extend(d for d in el.iter() if d.tag in _Z_TAGS)
    if len(leaves) > _Z_MAX:
        raise CdxmlUnsupportedObjectError(
            "page",
            "1",
            f"{len(leaves)} drawable objects need Z values above the INT16 "
            f"limit {_Z_MAX}; CDXML cannot order them",
        )
    for z, leaf in enumerate(leaves, start=1):
        leaf.set("Z", str(z))


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
    label_bindings: LabelBindings | None = None,
    paint_ranges: dict[int, tuple[int, int]] | None = None,
    documentary_bond_ids: frozenset[int] = frozenset(),
    documentary_caption_aryl_ids: frozenset[int] = frozenset(),
    attached_marks: Mapping[int, list[QGraphicsTextItem]] | None = None,
) -> list[tuple[int, ET.Element]]:
    atom_cdxml_ids: dict[int, int] = {}
    item_ranks = _fragment_item_ranks(context, scene_rank)
    if paint_ranges is None:
        paint_ranges = {}

    atom_rank_map = _atom_scene_rank_map(context, scene_rank)

    result: list[tuple[int, ET.Element]] = []

    for component in components:
        frag_cdxml_id = ids.next()
        frag = ET.Element("fragment")
        frag.set("id", str(frag_cdxml_id))

        frag_rank = max(atom_rank_map.get(aid, 0) for aid in component)

        for atom_id in sorted(component):
            if atom_id in documentary_caption_aryl_ids:
                continue
            atom = model.atoms[atom_id]
            node_id = ids.next()
            atom_cdxml_ids[atom_id] = node_id

            ax = _scale_coord(atom.x, ox, s)
            ay = _scale_coord(atom.y, oy, s)

            n = ET.SubElement(frag, "n")
            n.set("id", str(node_id))
            n.set("p", _pt_attr(ax, ay))
            paint_ranges[id(n)] = _paint_range(item_ranks, "atom", atom_id)

            label_plan = _resolve_label_plan(model, atom_id, label_bindings)
            z = label_plan.atomic_number
            if z is None:
                n.set(
                    "NodeType",
                    "Nickname",
                )
            elif z is not None and z != 6:
                n.set("Element", str(z))

            annotation = model.atom_annotation_for(atom_id)
            charge = 0
            if annotation:
                charge = annotation.get("formal_charge", 0)
            if charge != 0:
                n.set("Charge", str(charge))

            if atom.color != "#000000":
                n.set("color", str(colors.reference(atom.color)))

            if label_plan.fragment is not None and label_plan.neighbor_id is not None:
                neighbor = model.atoms[label_plan.neighbor_id]
                _add_nickname_fragment(
                    n,
                    _nickname_fragment_definition(label_plan.fragment),
                    (ax, ay),
                    (_scale_coord(neighbor.x, ox, s), _scale_coord(neighbor.y, oy, s)),
                    ids,
                )

            show_label = z is None or atom.element != "C" or atom.explicit_label
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
                    # Native save/reopen proves these exact labels retain their
                    # typed graph. Identifier H labels and bound Ar fragments
                    # must not be interpreted from their visible spelling.
                    interpret_chemically=(
                        label_plan.generic_nickname is not None
                        or (
                            atom.element in {"P", "O", "H"}
                            and _ELEMENT_TO_Z[atom.element] == z
                        )
                        or (
                            atom.element in {"Me", "tBu"}
                            and label_plan.fragment == atom.element
                        )
                    ),
                )
                if label_plan.generic_nickname is not None:
                    neighbor_point = None
                    if label_plan.neighbor_id is not None:
                        neighbor = model.atoms[label_plan.neighbor_id]
                        neighbor_point = (
                            _scale_coord(neighbor.x, ox, s),
                            _scale_coord(neighbor.y, oy, s),
                        )
                    _add_generic_aryl_fragment(n, neighbor_point, ids)

            for mark_item in (attached_marks or {}).get(atom_id, []):
                texts = _emit_note(mark_item, context, ids, fonts, colors, s, ox, oy)
                for text in texts:
                    baseline_x, baseline_y = map(float, text.attrib["p"].split())
                    tag = ET.SubElement(
                        n,
                        "objecttag",
                        id=str(ids.next()),
                        Name="chemvasMark",
                        TagType="String",
                        Persistent="yes",
                        Value=mark_item.toPlainText(),
                        PositioningType="offset",
                        PositioningOffset=_pt_attr(baseline_x - ax, baseline_y - ay),
                    )
                    tag.append(text)

        component_ids = set(component)
        for bond_id, bond in enumerate(model.bonds):
            if bond is None:
                continue
            if bond_id in documentary_bond_ids:
                continue
            if bond.a not in component_ids or bond.b not in component_ids:
                continue
            display, position = _resolved_bond_encoding(context, bond, bond_id)
            b_el = ET.SubElement(frag, "b")
            b_el.set("id", str(ids.next()))
            paint_ranges[id(b_el)] = _paint_range(item_ranks, "bond", bond_id)
            b_el.set("B", str(atom_cdxml_ids[bond.a]))
            b_el.set("E", str(atom_cdxml_ids[bond.b]))

            if bond.order != 1 or bond.style in {"dotted", "bold_in", "bold_out"}:
                b_el.set("Order", str(bond.order))

            if display is not None:
                b_el.set("Display", display)
            if bond.style in {"bold_in", "bold_out"}:
                # The Qt strip collapses to a normal stroke at this threshold.
                width = context.renderer.bold_bond_width()
                base_width = context.renderer.bond_line_width()
                if width <= base_width + 1e-6:
                    width = base_width
                b_el.set("BoldWidth", f"{width * s:.12g}")

            if position is not None:
                b_el.set("DoublePosition", position)
                # Native saved-SVG controls use the actual B-E length for this
                # bond-local percentage, even with a different root BondLength.
                # Bind it to the same two scene centerlines used on screen.
                items = context.state.bond_graphics_state.bond_items[bond_id]
                axis = _bond_axis(model, bond, bond_id)
                offsets = []
                for item in items:
                    x1, y1, x2, y2 = _scene_line(item)
                    offsets.append(_axis_coords(axis, (x1 + x2) / 2, (y1 + y2) / 2)[1])
                a, b = model.atoms[bond.a], model.atoms[bond.b]
                distance = math.hypot(b.x - a.x, b.y - a.y)
                b_el.set(
                    "BondSpacing",
                    f"{abs(offsets[1] - offsets[0]) / distance * 100:.12g}",
                )

            if bond.color != "#000000":
                b_el.set("color", str(colors.reference(bond.color)))

        _add_charged_atom_definitions(frag, ids)
        result.append((frag_rank, frag))

    return result


# ── Main serialization ───────────────────────────────────────────────


def _emit_notes(
    context: SceneRenderContext,
    export_set: set[QGraphicsItem],
    ids: _IdAllocator,
    fonts: _FontTable,
    colors: _ColorTable,
    s: float,
    ox: float,
    oy: float,
    scene_rank: dict[int, int],
    layout_reference: CdxmlTextLayoutReference | None,
) -> tuple[list[tuple[int, ET.Element]], list[CaptionGeometry]]:
    captions: list[CaptionGeometry] = []
    z_elements: list[tuple[int, ET.Element]] = []
    for note_index, note_item in enumerate(context.state.note_items()):
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
        if layout_reference is not None and t_elements:
            ink = _text_ink_bounds(note_item)
            captions.append(
                CaptionGeometry(
                    note_index,
                    tuple(t_elements),
                    (
                        (ink.left() - ox) * s,
                        (ink.top() - oy) * s,
                        (ink.right() - ox) * s,
                        (ink.bottom() - oy) * s,
                    ),
                )
            )
        note_rank = scene_rank.get(id(note_item), 0)
        for t_el in t_elements:
            z_elements.append((note_rank, t_el))

    return z_elements, captions


def serialize_cdxml(
    context: SceneRenderContext,
    items: Sequence[QGraphicsItem],
    plan: ExportPlan,
    *,
    background: str = "white",
    groups: Mapping[int, SceneGroup] | None = None,
    label_bindings: LabelBindings | None = None,
    documentary_contacts: DocumentaryContacts | None = None,
    layout_reference: CdxmlTextLayoutReference | None = None,
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

    export_layout = _cdxml_caption_export_layout(
        model,
        atom_ids_in_export,
        label_bindings,
        documentary_contacts,
    )
    documentary_bond_ids = export_layout.documentary_bond_ids
    attached_marks = _validated_attached_marks(
        context, export_items, export_layout.chemical_atom_ids
    )
    components = export_layout.components
    _check_fragment_interleaving(
        context,
        export_items,
        export_layout.chemical_atom_ids,
        documentary_bond_ids=documentary_bond_ids,
        documentary_caption_aryl_ids=export_layout.caption_aryl_ids,
    )
    contact_by_bond = {
        contact.bond_id: contact for contact in export_layout.authorized_contacts
    }

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

    # Every element carries its scene rank and is sorted by it below, so the
    # order in which kinds are collected only decides the XML ids.
    z_elements: list[tuple[int, ET.Element]] = _serialize_ts_brackets(
        context, export_set, scene_rank, ids, colors, fonts, s, ox, oy
    )
    paint_ranges: dict[int, tuple[int, int]] = {}

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
        label_bindings,
        paint_ranges,
        documentary_bond_ids,
        documentary_caption_aryl_ids=export_layout.caption_aryl_ids,
        attached_marks=attached_marks,
    ):
        z_elements.append((frag_rank, frag_el))

    if label_bindings:
        z_elements.extend(
            _collect_aryl_label_caption_z_elements(
                context,
                export_layout.caption_aryl_ids,
                label_bindings,
                scene_rank,
                ids,
                fonts,
                colors,
                s,
                ox,
                oy,
            )
        )

    bond_color_hex = context.renderer.bond_pen().color().name()
    z_elements.extend(
        _collect_documentary_contact_z_elements(
            context,
            model,
            documentary_bond_ids,
            contact_by_bond,
            scene_rank,
            ids,
            colors,
            s,
            ox,
            oy,
            line_width_scaled,
            bond_color_hex,
        )
    )

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

    note_elements, captions = _emit_notes(
        context, export_set, ids, fonts, colors, s, ox, oy, scene_rank, layout_reference
    )
    z_elements.extend(note_elements)

    z_elements.sort(key=lambda x: x[0])
    _assign_z([el for _, el in z_elements], paint_ranges)

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

    for _, el in z_elements:
        page.append(el)

    _indent_preserving_text(root)
    if layout_reference is not None:
        reflow_cdxml_captions(
            captions,
            layout_reference,
            page_width=page_width,
            page_height=plan.out_h_pt,
            producer_xml=ET.tostring(root, encoding="utf-8", xml_declaration=True),
        )
    _indent_preserving_text(root)
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes


def _add_charged_atom_definitions(fragment: ET.Element, ids: _IdAllocator) -> None:
    """Keep visible labels/marks distinct from ChemDraw's parsed atom charge.

    ChemDraw reparses a plain P/O label and drops a conflicting Charge field.
    A defined fragment keeps that label while explicitly mapping every outer
    bond to its own internal connection point on the charged atom.
    """
    nodes = {node.attrib["id"]: node for node in fragment.findall("n")}
    for identity, node in nodes.items():
        label = node.find("t")
        charge = int(node.get("Charge", "0"))
        if not charge or label is None:
            continue
        atomic_number = node.get("Element", "6")
        symbol = next(k for k, v in _ELEMENT_TO_Z.items() if str(v) == atomic_number)
        del node.attrib["Charge"]
        node.attrib.pop("Element", None)
        node.set("NodeType", "Fragment")
        label.set("InterpretChemically", "yes")
        inner = ET.Element("fragment", id=str(ids.next()))
        node.insert(0, inner)
        atom = ET.SubElement(
            inner,
            "n",
            id=str(ids.next()),
            p=node.attrib["p"],
            Element=atomic_number,
            Charge=str(charge),
        )
        text = deepcopy(label)
        text.set("id", str(ids.next()))
        text.attrib.pop("Z", None)
        for run in list(text):
            text.remove(run)
        first = deepcopy(label.find("s"))
        assert first is not None
        first.text = symbol
        text.append(first)
        sign = deepcopy(first)
        sign.set("face", str(int(sign.get("face", "0")) | 64))
        sign.text = (str(abs(charge)) if abs(charge) != 1 else "") + (
            "+" if charge > 0 else "-"
        )
        text.append(sign)
        atom.append(text)
        bonds, points = [], []
        for bond in fragment.findall("b"):
            begin, end = bond.attrib["B"], bond.attrib["E"]
            if identity not in {begin, end}:
                continue
            neighbor = nodes[end if begin == identity else begin]
            bonds.append(bond.attrib["id"])
            connection = ET.SubElement(
                inner,
                "n",
                id=str(ids.next()),
                p=neighbor.attrib["p"],
                NodeType="ExternalConnectionPoint",
            )
            points.append(connection.attrib["id"])
            internal_bond = ET.SubElement(
                inner,
                "b",
                id=str(ids.next()),
                B=atom.attrib["id"],
                E=connection.attrib["id"],
            )
            if "Order" in bond.attrib:
                internal_bond.set("Order", bond.attrib["Order"])
        if len(points) > 1:
            node.set("BondOrdering", " ".join(bonds))
            inner.set("ConnectionOrder", " ".join(points))


def _add_generic_aryl_fragment(
    node: ET.Element,
    neighbor_point: tuple[float, float] | None,
    ids: _IdAllocator,
) -> None:
    """Keep Ar display separate from the native ARY query definition."""
    inner = ET.Element("fragment", id=str(ids.next()))
    node.insert(0, inner)
    query = ET.SubElement(
        inner,
        "n",
        id=str(ids.next()),
        p=node.attrib["p"],
        NodeType="GenericNickname",
        GenericNickname="ARY",
    )
    label = node.find("t")
    assert label is not None
    text = deepcopy(label)
    text.set("id", str(ids.next()))
    run = text.find("s")
    assert run is not None and len(text.findall("s")) == 1
    run.text = "ARY"
    query.append(text)
    if neighbor_point is not None:
        connection = ET.SubElement(
            inner,
            "n",
            id=str(ids.next()),
            p=_pt_attr(*neighbor_point),
            NodeType="ExternalConnectionPoint",
        )
        ET.SubElement(
            inner,
            "b",
            id=str(ids.next()),
            B=query.attrib["id"],
            E=connection.attrib["id"],
        )


def _add_nickname_fragment(
    n: ET.Element,
    definition: _FragmentDefinition,
    label_point: tuple[float, float],
    neighbor_point: tuple[float, float],
    ids: _IdAllocator,
) -> None:
    """Emit the contracted group's own atoms and its connection point.

    The connection point sits on the outside neighbour, so the outside bond
    and the internal attachment bond share one direction and one length.
    """
    px, py = label_point
    qx, qy = neighbor_point
    length = math.hypot(px - qx, py - qy)
    ux, uy = (px - qx) / length, (py - qy) / length
    vx, vy = -uy, ux

    inner = ET.SubElement(n, "fragment")
    inner.set("id", str(ids.next()))
    inner_ids: list[int] = []
    for (atomic_number, hydrogens), (along, side) in zip(
        definition.atoms, definition.layout, strict=True
    ):
        node_id = ids.next()
        inner_ids.append(node_id)
        node = ET.SubElement(inner, "n")
        node.set("id", str(node_id))
        node.set(
            "p",
            _pt_attr(
                px + length * (along * ux + side * vx),
                py + length * (along * uy + side * vy),
            ),
        )
        if atomic_number != 6:
            node.set("Element", str(atomic_number))
        node.set("NumHydrogens", str(hydrogens))
    connection_id = ids.next()
    connection = ET.SubElement(inner, "n")
    connection.set("id", str(connection_id))
    connection.set("p", _pt_attr(qx, qy))
    connection.set("NodeType", "ExternalConnectionPoint")
    for first, second, order in (*definition.bonds, (0, -1, 1)):
        bond = ET.SubElement(inner, "b")
        bond.set("id", str(ids.next()))
        bond.set("B", str(inner_ids[first]))
        bond.set("E", str(connection_id if second == -1 else inner_ids[second]))
        if order != 1:
            bond.set("Order", str(order))


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


def _font_size_attr(points: float) -> str:
    """Encode the nearest native twentieth-point size, never biased truncation."""
    if not math.isfinite(points) or points <= 0:
        raise CdxmlUnsupportedObjectError("font", "size", "invalid font size")
    twentieths = math.floor(points * 20.0 + 0.5)
    if twentieths <= 0 or twentieths > 65535:
        raise CdxmlUnsupportedObjectError(
            "font", "size", "font size is outside native twentieth-point precision"
        )
    return f"{twentieths / 20:.12g}"


def _emit_documentary_aryl_caption(
    context: SceneRenderContext,
    atom_id: int,
    author_note: str,
    ids: _IdAllocator,
    fonts: _FontTable,
    colors: _ColorTable,
    scale: float,
    ox: float,
    oy: float,
) -> ET.Element:
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

    t = ET.Element("t")
    t.set("id", str(ids.next()))
    t.set("p", _pt_attr(ax, ay))
    t.set("Justification", "Left")
    t.set("InterpretChemically", "no")
    t.set("CaptionLineHeight", "1")

    s_el = ET.SubElement(t, "s")
    s_el.set("font", str(font_id))
    s_el.set("size", _font_size_attr(label_size))
    s_el.set("color", color_ref)
    if face:
        s_el.set("face", str(face))
    s_el.text = _validate_xml_text(
        atom_obj.element,
        "atom",
        str(atom_id),
    )

    _add_chemvas_string_objecttag(t, "ArylLabelAuthorNote", author_note)
    _add_chemvas_string_objecttag(
        t,
        "ArylLabelCaption",
        _documentary_aryl_caption_metadata(atom_id),
    )
    return t


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
    *,
    interpret_chemically: bool = False,
) -> None:
    from PyQt6.QtGui import QFontInfo

    from chemvas.ui.canvas.graphics_items import AtomLabelItem

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
    item = context.state.atom_graphics_state.atom_items.get(atom_id)
    alignment = "Left"
    if isinstance(item, AtomLabelItem) and item.anchor_at_end:
        alignment = "Right"
        ax += item.label_advance() * item_scale * scale
        t.set("p", _pt_attr(ax, ay))
    t.set("Justification", alignment)
    t.set("LabelJustification", alignment)
    t.set("InterpretChemically", "yes" if interpret_chemically else "no")
    t.set("CaptionLineHeight", "1")

    s_el = ET.SubElement(t, "s")
    s_el.set("font", str(font_id))
    s_el.set("size", _font_size_attr(label_size))
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


def _line_element(
    ids: _IdAllocator,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    width: float,
    line_type: str = "Solid",
) -> ET.Element:
    """A native no-head arrow preserves local width across ChemDraw SaveAs."""
    return ET.Element(
        "arrow",
        id=str(ids.next()),
        FillType="None",
        ArrowheadType="Solid",
        LineType=line_type,
        Tail3D=_pt3_attr(start_x, start_y),
        Head3D=_pt3_attr(end_x, end_y),
        LineWidth=f"{width:.12g}",
    )


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

    if kind in _SUPPORTED_LINE_KINDS:
        g = _line_element(
            ids,
            sx,
            sy,
            ex,
            ey,
            context.renderer.bold_bond_width() * s
            if kind == "line_bold"
            else arrow_lw_scaled,
            _LINE_TYPE_FOR_KIND[kind],
        )
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

        group.append(
            _line_element(ids, seg_sx, seg_sy, seg_ex, seg_ey, arrow_lw_scaled)
        )

    effective_color = record.color or bond_color_hex
    if effective_color != "#000000":
        color_ref = str(colors.reference(effective_color))
        for child in group:
            child.set("color", color_ref)

    return group


# ── TS bracket check and emission ─────────────────────────────────────
#
# A TS bracket is a filled path item drawn from its record: the square kinds
# stroke the M/L commands of ``bracket_path_commands`` and the dagger kinds
# outline one glyph laid out by ``bracket_symbol_layout``. The exporter reads
# the same record and the same pure functions, checks that the item still
# paints exactly that path, and writes the strokes as unheaded arrows (the
# polyline vertices, not the filled outline) or the glyph as one text run.


def _ts_bracket_record(
    context: SceneRenderContext, item: QGraphicsItem, index: int
) -> TSBracket:
    rec_id = item.data(3)
    record = (
        context.state.ts_bracket_state.records.get(rec_id)
        if type(rec_id) is int
        else None
    )
    if record is None:
        raise CdxmlUnsupportedObjectError(
            "ts_bracket", str(index), "bracket item has no document record"
        )
    return record


def _ts_bracket_bounds(record: TSBracket) -> tuple[float, float, float, float]:
    left, right = sorted((record.left, record.right))
    top, bottom = sorted((record.top, record.bottom))
    return left, top, right - left, bottom - top


def _check_ts_bracket_paint(item: QGraphicsItem, object_id: str) -> QGraphicsPathItem:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QGraphicsPathItem

    if not isinstance(item, QGraphicsPathItem):
        raise CdxmlUnsupportedObjectError(
            "ts_bracket", object_id, "bracket item is not a path item"
        )
    if not item.sceneTransform().isIdentity():
        raise CdxmlUnsupportedObjectError(
            "ts_bracket",
            object_id,
            "moved, scaled or rotated bracket item has no proved encoding",
        )
    if item.effectiveOpacity() != 1.0:
        raise CdxmlUnsupportedObjectError(
            "ts_bracket", object_id, "translucent bracket cannot be represented"
        )
    if item.pen().style() != Qt.PenStyle.NoPen:
        raise CdxmlUnsupportedObjectError(
            "ts_bracket", object_id, "bracket item has an outline pen"
        )
    brush = item.brush()
    if brush.style() != Qt.BrushStyle.SolidPattern or brush.color().alpha() != 255:
        raise CdxmlUnsupportedObjectError(
            "ts_bracket",
            object_id,
            "bracket paint is not one opaque solid colour",
        )
    return item


def _ts_bracket_glyph_run(item: QGraphicsItem, object_id: str) -> tuple[str, QFont]:
    from PyQt6.QtGui import QFont

    glyph_run = getattr(item, "export_glyph_run", None)
    run = glyph_run() if callable(glyph_run) else None
    if (
        not isinstance(run, tuple)
        or len(run) != 2
        or not isinstance(run[0], str)
        or not isinstance(run[1], QFont)
    ):
        raise CdxmlUnsupportedObjectError(
            "ts_bracket", object_id, "dagger glyph run is not available"
        )
    return run[0], run[1]


def _ts_bracket_color(item: QGraphicsItem) -> str:
    from PyQt6.QtWidgets import QGraphicsPathItem

    if not isinstance(item, QGraphicsPathItem):
        raise CdxmlUnsupportedObjectError(
            "ts_bracket", str(item.data(3) or "?"), "bracket item is not a path item"
        )
    return item.brush().color().name()


def _check_ts_bracket_glyph(
    item: QGraphicsItem,
    kind: str,
    pixels: int,
    object_id: str,
) -> None:
    from PyQt6.QtGui import QFont, QFontInfo

    text, font = _ts_bracket_glyph_run(item, object_id)
    if text != BRACKET_SYMBOLS[kind]:
        raise CdxmlUnsupportedObjectError(
            "ts_bracket", object_id, "dagger glyph text does not match its kind"
        )
    if font.italic() or font.weight() != QFont.Weight.Normal:
        raise CdxmlUnsupportedObjectError(
            "ts_bracket", object_id, "dagger glyph is not in the plain document font"
        )
    if font.pixelSize() != pixels:
        raise CdxmlUnsupportedObjectError(
            "ts_bracket",
            object_id,
            "dagger glyph size does not match its bracket layout",
        )
    _check_glyph_font_consistency(
        font, QFontInfo(font).family(), text, "ts_bracket", object_id
    )


def _check_ts_bracket(
    context: SceneRenderContext, item: QGraphicsItem, index: int
) -> None:
    from PyQt6.QtWidgets import QGraphicsPathItem

    from chemvas.ui.annotations.records import render_ts_bracket_item

    record = _ts_bracket_record(context, item, index)
    kind = record.bracket_kind
    object_id = str(index)
    if kind not in _SQUARE_BRACKET_KINDS and kind not in BRACKET_SYMBOLS:
        raise CdxmlUnsupportedObjectError(
            "ts_bracket",
            object_id,
            f"bracket kind '{kind}' is drawn with curves that have no "
            "proved CDXML encoding",
        )
    path_item = _check_ts_bracket_paint(item, object_id)
    bounds = _ts_bracket_bounds(record)
    bond_length = context.renderer.style.bond_length_px
    # The record's path comes from its single painter, drawn onto a detached
    # item so the scene item is only read.
    expected = QGraphicsPathItem()
    render_ts_bracket_item(context, expected, record)
    if path_item.path() != expected.path():
        raise CdxmlUnsupportedObjectError(
            "ts_bracket",
            object_id,
            "bracket item does not paint the path of its record",
        )
    if kind in BRACKET_SYMBOLS:
        pixels, _x, _y = bracket_symbol_layout(bounds, bond_length)
        _check_ts_bracket_glyph(item, kind, pixels, object_id)
        return
    commands = bracket_path_commands(bounds, kind, bond_length)
    if not commands or any(cmd not in ("M", "L") for cmd, _ in commands):
        raise CdxmlUnsupportedObjectError(
            "ts_bracket",
            object_id,
            "bracket path has commands other than M and L",
        )


def _check_ts_brackets(
    context: SceneRenderContext,
    export_items: list[QGraphicsItem],
    export_set: set[QGraphicsItem],
) -> None:
    listed: set[QGraphicsItem] = set()
    for idx, bracket_item in enumerate(context.state.ts_bracket_items()):
        if bracket_item is None:
            continue
        listed.add(bracket_item)
        if bracket_item in export_set and bracket_item.isVisible():
            _check_ts_bracket(context, bracket_item, idx)
    for item in export_items:
        if item.data(0) == "ts_bracket" and item.isVisible() and item not in listed:
            raise CdxmlUnsupportedObjectError(
                "ts_bracket",
                str(item.data(3) or "?"),
                "bracket item is not a document bracket",
            )


def _emit_ts_bracket_glyph(
    item: QGraphicsItem,
    bounds: tuple[float, float, float, float],
    bond_length: float,
    color_ref: str,
    ids: _IdAllocator,
    fonts: _FontTable,
    s: float,
    origin: tuple[float, float],
) -> ET.Element:
    from PyQt6.QtGui import QFontInfo

    text, font = _ts_bracket_glyph_run(item, str(item.data(3) or "?"))
    pixels, x, y = bracket_symbol_layout(bounds, bond_length)
    t_el = ET.Element("t")
    t_el.set("id", str(ids.next()))
    t_el.set(
        "p",
        _pt_attr(_scale_coord(x, origin[0], s), _scale_coord(y, origin[1], s)),
    )
    t_el.set("Justification", "Left")
    t_el.set("InterpretChemically", "no")
    t_el.set("CaptionLineHeight", "1")
    s_el = ET.SubElement(t_el, "s")
    s_el.set("font", str(fonts.id_for(QFontInfo(font).family())))
    s_el.set("size", _font_size_attr(pixels * s))
    s_el.set("color", color_ref)
    s_el.text = _validate_xml_text(text, "ts_bracket", str(item.data(3) or "?"))
    return t_el


def _emit_ts_bracket(
    context: SceneRenderContext,
    item: QGraphicsItem,
    record: TSBracket,
    ids: _IdAllocator,
    colors: _ColorTable,
    fonts: _FontTable,
    s: float,
    origin: tuple[float, float],
) -> ET.Element:
    style = context.renderer.style
    bounds = _ts_bracket_bounds(record)
    color_hex = _ts_bracket_color(item)
    if record.bracket_kind in BRACKET_SYMBOLS:
        color_ref = str(colors.reference(color_hex)) if color_hex != "#000000" else "3"
        return _emit_ts_bracket_glyph(
            item, bounds, style.bond_length_px, color_ref, ids, fonts, s, origin
        )

    width = bracket_stroke_width(style.bond_line_width) * s
    group = ET.Element("group")
    group.set("id", str(ids.next()))
    current = (0.0, 0.0)
    for cmd, args in bracket_path_commands(
        bounds, record.bracket_kind, style.bond_length_px
    ):
        point = (args[0], args[1])
        if cmd == "L":
            g = _line_element(
                ids,
                _scale_coord(current[0], origin[0], s),
                _scale_coord(current[1], origin[1], s),
                _scale_coord(point[0], origin[0], s),
                _scale_coord(point[1], origin[1], s),
                width,
            )
            group.append(g)
            if color_hex != "#000000":
                g.set("color", str(colors.reference(color_hex)))
        current = point
    return group


def _serialize_ts_brackets(
    context: SceneRenderContext,
    export_set: set[QGraphicsItem],
    scene_rank: dict[int, int],
    ids: _IdAllocator,
    colors: _ColorTable,
    fonts: _FontTable,
    s: float,
    ox: float,
    oy: float,
) -> list[tuple[int, ET.Element]]:
    result: list[tuple[int, ET.Element]] = []
    for idx, item in enumerate(context.state.ts_bracket_items()):
        if item is None or item not in export_set or not item.isVisible():
            continue
        record = _ts_bracket_record(context, item, idx)
        el = _emit_ts_bracket(context, item, record, ids, colors, fonts, s, (ox, oy))
        result.append((scene_rank.get(id(item), 0), el))
    return result


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
    rotation_angle = _note_rotation_angle(item_transform, "serialization")
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
            if rotation_angle:
                t_el.set("RotationAngle", str(rotation_angle))

            line_start = line.textStart()
            line_end = line_start + line.textLength()
            # Qt includes a forced line separator in its line range. This is
            # layout control already represented by the separate <t> baseline,
            # not a printable character for the consumer.
            if block_utf16[(line_end - 1) * 2 : line_end * 2] == "\u2028".encode(
                "utf-16-le"
            ):
                line_end -= 1

            positioned = _note_line_has_script(block, line_start, line_end)
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
                        run_parent = ET.Element("t") if positioned else t_el
                        _emit_note_run(
                            run_parent,
                            text,
                            overlap_start,
                            fragment,
                            layout,
                            default_font,
                            item,
                            item_scale,
                            s,
                            fonts,
                            colors,
                        )
                        if positioned:
                            result.extend(
                                _position_note_segments(
                                    t_el,
                                    run_parent,
                                    overlap_start,
                                    fragment,
                                    layout,
                                    item,
                                    ids,
                                    s,
                                    ox,
                                    oy,
                                )
                            )

                frag_it += 1

            if len(t_el) > 0:
                result.append(t_el)

        block = block.next()

    return result


def _note_line_has_script(block: QTextBlock, start: int, end: int) -> bool:
    from PyQt6.QtGui import QTextCharFormat

    fragments = block.begin()
    while not fragments.atEnd():
        fragment = fragments.fragment()
        position = fragment.position() - block.position()
        if position < end and position + fragment.length() > start:
            if fragment.charFormat().verticalAlignment() in (
                QTextCharFormat.VerticalAlignment.AlignSubScript,
                QTextCharFormat.VerticalAlignment.AlignSuperScript,
            ):
                return True
        fragments += 1
    return False


def _position_note_segments(
    template: ET.Element,
    parent: ET.Element,
    start: int,
    fragment: QTextFragment,
    layout: QTextLayout,
    item: QGraphicsTextItem,
    ids: _IdAllocator,
    scale: float,
    ox: float,
    oy: float,
) -> list[ET.Element]:
    """Keep editable script faces at the common renderer's shaped origins.

    Native script faces paint at 3/4 size. Subscript shifts by the full-size
    descent; superscript by -(em - descent)/2 (ADR 0053). Each run gets an
    explicit origin so a consumer cannot reflow the following normal text.
    """
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QGlyphRun

    from chemvas.features.annotations import atom_label_baseline_offset
    from chemvas.ui.canvas.graphics_items import note_fragment_baseline_shift

    elements: list[ET.Element] = []
    item_scale = math.hypot(item.sceneTransform().m11(), item.sceneTransform().m12())
    for segment in parent:
        length = len((segment.text or "").encode("utf-16-le")) // 2
        runs = layout.glyphRuns(start, length)
        positions = [p for run in runs for p in run.positions()]
        if not positions or any(
            run.flags()
            & (
                QGlyphRun.GlyphRunFlag.RightToLeft
                | QGlyphRun.GlyphRunFlag.SplitLigature
            )
            for run in runs
        ):
            raise CdxmlUnsupportedObjectError(
                "note", str(item.data(3) or "?"), "script glyph origin is ambiguous"
            )
        raw = runs[0].rawFont()
        if any(run.rawFont() != raw for run in runs) or any(
            not math.isclose(p.y(), positions[0].y(), abs_tol=1e-6) for p in positions
        ):
            raise CdxmlUnsupportedObjectError(
                "note", str(item.data(3) or "?"), "script glyph baseline is ambiguous"
            )
        native_size = float(segment.get("size", "0")) / (item_scale * scale)
        native_descent = raw.descent() * native_size / raw.pixelSize()
        face = int(segment.get("face", "0"))
        native_shift = 0.0
        if face & _FACE_SUBSCRIPT:
            native_shift = native_descent
        elif face & _FACE_SUPERSCRIPT:
            native_shift = -atom_label_baseline_offset(native_size, native_descent)
        point = layout.position() + QPointF(
            min(p.x() for p in positions),
            positions[0].y()
            + note_fragment_baseline_shift(fragment.charFormat(), raw)
            - native_shift,
        )
        scene_point = item.mapToScene(point)
        text = ET.Element("t", template.attrib)
        text.set("id", str(ids.next()))
        text.set(
            "p",
            _pt_attr(
                _scale_coord(scene_point.x(), ox, scale),
                _scale_coord(scene_point.y(), oy, scale),
            ),
        )
        text.append(segment)
        elements.append(text)
        start += length
    return elements


def _note_font_segments(
    layout: QTextLayout, start: int, text: str, object_id: str, weight: int
) -> list[tuple[str, str, float]]:
    from PyQt6.QtGui import QFont, QGlyphRun

    length = len(text.encode("utf-16-le")) // 2
    runs = layout.glyphRuns(start, length)
    keys: set[tuple[str, float]] = set()
    for run in runs:
        raw = run.rawFont()
        key = (raw.familyName(), float(raw.pixelSize()))
        if not key[0] or not math.isfinite(key[1]) or key[1] <= 0:
            raise CdxmlUnsupportedObjectError(
                "note", object_id, "painted glyph font is unavailable"
            )
        if raw.style() != QFont.Style.StyleNormal or int(raw.weight()) != weight:
            raise CdxmlUnsupportedObjectError(
                "note",
                object_id,
                "painted fallback font face differs from text formatting",
            )
        keys.add(key)
        for glyph in run.glyphIndexes():
            if glyph == 0:
                raise CdxmlUnsupportedObjectError(
                    "note", object_id, "painted glyph maps to index 0 (.notdef)"
                )
    if not keys:
        raise CdxmlUnsupportedObjectError(
            "note", object_id, "painted glyph runs are unavailable"
        )
    if len(keys) == 1:
        family, pixel_size = next(iter(keys))
        if not text.isspace() and all(
            run.rawFont().pathForGlyph(glyph).isEmpty()
            for run in runs
            for glyph in run.glyphIndexes()
        ):
            raise CdxmlUnsupportedObjectError(
                "note", object_id, "painted glyph outlines are unavailable"
            )
        return [(text, family, pixel_size)]
    if length != len(text):
        raise CdxmlUnsupportedObjectError(
            "note", object_id, "mixed fallback surrogates have no proved mapping"
        )
    result: list[tuple[str, str, float]] = []
    previous_position: QPointF | None = None
    for index, character in enumerate(text):
        character_runs = layout.glyphRuns(start + index, 1)
        if len(character_runs) != 1 or len(character_runs[0].glyphIndexes()) != 1:
            raise CdxmlUnsupportedObjectError(
                "note", object_id, "mixed fallback glyph cluster mapping is ambiguous"
            )
        run = character_runs[0]
        if run.flags() & QGlyphRun.GlyphRunFlag.SplitLigature:
            raise CdxmlUnsupportedObjectError(
                "note", object_id, "mixed fallback split ligature has no proved mapping"
            )
        raw = run.rawFont()
        position = run.positions()[0]
        if previous_position is not None and (
            position.x() <= previous_position.x()
            or not math.isclose(position.y(), previous_position.y(), abs_tol=1e-6)
        ):
            raise CdxmlUnsupportedObjectError(
                "note",
                object_id,
                "mixed fallback glyph positions have no proved mapping",
            )
        previous_position = position
        family, pixel_size = raw.familyName(), float(raw.pixelSize())
        if (
            not character.isspace()
            and raw.pathForGlyph(run.glyphIndexes()[0]).isEmpty()
        ):
            raise CdxmlUnsupportedObjectError(
                "note", object_id, "painted glyph outlines are unavailable"
            )
        if result and result[-1][1:] == (family, pixel_size):
            result[-1] = (result[-1][0] + character, family, pixel_size)
        else:
            result.append((character, family, pixel_size))
    return result


def _emit_note_run(
    t_el: ET.Element,
    text: str,
    text_start: int,
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
    from PyQt6.QtGui import QTextCharFormat

    fmt = fragment.charFormat()
    frag_font = fmt.font().resolve(default_font)

    segments = _note_font_segments(
        layout, text_start, text, str(item.data(3) or "?"), int(frag_font.weight())
    )

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
    # Text runs record their literal painted color. Native SaveAs elides the
    # default foreground index 3; absolute black/white indexes keep the authored
    # literal choice explicit without relying on the reader's default scope.
    color_ref = {"#000000": "0", "#ffffff": "1"}.get(color_hex)
    if color_ref is None:
        color_ref = str(colors.reference(color_hex))

    face = _FACE_BOLD if frag_font.bold() else 0
    alignment = fmt.verticalAlignment()
    if alignment == QTextCharFormat.VerticalAlignment.AlignSubScript:
        face |= _FACE_SUBSCRIPT
    elif alignment == QTextCharFormat.VerticalAlignment.AlignSuperScript:
        face |= _FACE_SUPERSCRIPT
    script_scale = _NATIVE_SCRIPT_SCALE if face & 96 else 1.0

    for run_text, family, pixel_size in segments:
        s_el = ET.SubElement(t_el, "s")
        s_el.set("font", str(fonts.id_for(family)))
        s_el.set("size", _font_size_attr(pixel_size * item_scale * s / script_scale))
        s_el.set("color", color_ref)
        if face:
            s_el.set("face", str(face))
        s_el.text = _validate_xml_text(run_text, "note", str(item.data(3) or "?"))


# ── Public API ─────────────────────────────────────────────────────────

__all__ = [
    "CdxmlLabelBinding",
    "CdxmlUnsupportedObjectError",
    "GroupsProvider",
    "LabelBindings",
    "preflight_cdxml",
    "serialize_cdxml",
]
