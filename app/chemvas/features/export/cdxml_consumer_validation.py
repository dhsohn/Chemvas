"""Validate a measured CDXML against the actual uncorrected producer objects.

Consumer font mappings are explicit declarations, not proof that the same font
files will be installed during a later consumer run.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from chemvas.features.export.cdxml_paint_order import (
    line_overlaps_filled_rectangle,
    validate_relative_order,
)

COORDINATE_TOLERANCE_PT = 0.02


def numbers(value: str, count: int) -> tuple[float, ...]:
    try:
        result = tuple(map(float, value.split()))
    except ValueError as exc:
        raise ValueError("CDXML consumer geometry must be numeric") from exc
    if len(result) != count or not all(math.isfinite(n) for n in result):
        raise ValueError("CDXML consumer geometry must be finite")
    return result


def parse_consumer_xml(raw: bytes) -> ET.Element:
    try:
        text = raw.decode("utf-8-sig")
        if "<!ENTITY" in text:
            raise ValueError("CDXML consumer reference must not declare entities")
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError) as exc:
        raise ValueError("CDXML consumer reference is not UTF-8 CDXML") from exc
    if root.tag != "CDXML" or len(root.findall("page")) != 1:
        raise ValueError("CDXML consumer reference requires one page")
    return root


def _compare_points(a: str, b: str, count: int, field: str) -> None:
    if any(
        abs(x - y) > COORDINATE_TOLERANCE_PT
        for x, y in zip(numbers(a, count), numbers(b, count), strict=True)
    ):
        raise ValueError(f"CDXML consumer reference changed {field}")


@dataclass
class _Scene:
    root: ET.Element

    def __post_init__(self) -> None:
        self.parents = {
            child: parent for parent in self.root.iter() for child in parent
        }
        object_tags = {
            "page",
            "fragment",
            "n",
            "b",
            "group",
            "graphic",
            "arrow",
            "t",
            "objecttag",
        }
        identities = [
            x.attrib["id"]
            for x in self.root.iter()
            if x.tag in object_tags and "id" in x.attrib
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("CDXML consumer reference has duplicate object IDs")
        self.fonts: dict[str, str] = {}
        for font in self.root.findall("./fonttable/font"):
            identity, name = font.get("id", ""), font.get("name", "")
            if not identity or not name or identity in self.fonts:
                raise ValueError("CDXML reference has an invalid font table")
            self.fonts[identity] = name
        self.colors = self.root.findall("./colortable/color")

    def inherited(self, item: ET.Element, key: str, default: str) -> str:
        current: ET.Element | None = item
        while current is not None:
            if key in current.attrib:
                return current.attrib[key]
            current = self.parents.get(current)
        return default

    def color(self, item: ET.Element) -> tuple[float, ...]:
        try:
            parent = self.parents.get(item)
            if (
                item.tag == "s"
                and parent is not None
                and parent.tag == "t"
                and self.parents.get(parent) is not None
                and self.parents[parent].tag == "objecttag"
            ):
                # An object tag's text has its own default foreground. Native
                # SVG confirms that omitted run color stays black beneath a
                # colored atom; it does not inherit the atom-label color.
                index = int(item.get("color", parent.get("color", "3")))
            else:
                index = int(self.inherited(item, "color", "0"))
        except ValueError as exc:
            raise ValueError("CDXML reference has an invalid color") from exc
        if index < 2:
            if index < 0:
                raise ValueError("CDXML reference has an invalid color")
            return (float(index),) * 3
        if self.root.find("./colortable") is None and index in (2, 3):
            # Without a table, the standard background/foreground are white/black.
            return (float(3 - index),) * 3
        try:
            row = self.colors[index - 2]
        except IndexError as exc:
            raise ValueError("CDXML reference has an undefined color") from exc
        components = numbers(" ".join(row.get(k, "") for k in ("r", "g", "b")), 3)
        if any(not 0 <= value <= 1 for value in components):
            raise ValueError("CDXML reference color components must be within 0..1")
        return components

    def alignment(self, text: ET.Element) -> str:
        atom_label = self.parents[text].tag == "n"
        key = "LabelJustification" if atom_label else "CaptionJustification"
        preferred = self.inherited(text, key, "")
        if preferred:
            return preferred
        return self.inherited(text, "Justification", "Auto" if atom_label else "Left")

    def objects(self, tag: str) -> dict[tuple[str, ...], ET.Element]:
        result: dict[tuple[str, ...], ET.Element] = {}
        identities: set[str] = set()
        for item in self.root.iter(tag):
            identity = item.get("id", "")
            if not identity or identity in identities:
                raise ValueError(
                    "CDXML consumer reference has duplicate or missing IDs"
                )
            identities.add(identity)
            result[self.path(item)] = item
        return result

    def path(self, item: ET.Element) -> tuple[str, ...]:
        if item.tag == "CDXML":
            return ("CDXML",)
        if item.tag == "page":
            return ("page",)
        parent = self.parents[item]
        if item.tag == "fragment" and parent.tag == "n":
            if len(parent.findall("fragment")) != 1:
                raise ValueError("CDXML reference has ambiguous fragment ownership")
            # Native SaveAs renumbers a node's definition fragment, retaining
            # its owner, atom/bond IDs and ordered connection ports.
            return (*self.path(parent), "fragment[0]")
        # ChemDraw drops IDs on atom-label text and attached object tags.
        # Anchor their full relative paths at the owning persistent object.
        if item.tag not in {"t", "objecttag"} and item.get("id"):
            return (item.tag, item.attrib["id"])
        index = list(parent.findall(item.tag)).index(item)
        return (*self.path(parent), f"{item.tag}[{index}]")

    def owner(self, item: ET.Element) -> tuple[str, ...]:
        return self.path(self.parents[item])

    def texts(self) -> dict[tuple[str, ...], ET.Element]:
        result: dict[tuple[str, ...], ET.Element] = {}
        for item in self.root.iter("t"):
            parent = self.parents[item]
            key = (
                ("caption", item.attrib["id"])
                if parent.tag == "page" and "id" in item.attrib
                else self.path(item)
            )
            if key in result:
                raise ValueError("CDXML consumer reference has duplicate text paths")
            result[key] = item
        return result

    def runs(self, text: ET.Element) -> list[tuple[str, float, int, tuple[float, ...]]]:
        result: list[tuple[str, float, int, tuple[float, ...]]] = []
        for run in text.findall("s"):
            identity = run.get("font", "")
            if identity not in self.fonts:
                raise ValueError("CDXML consumer reference has an undefined font ID")
            size = numbers(run.get("size", ""), 1)[0]
            if size <= 0:
                raise ValueError("CDXML consumer font size must be positive")
            try:
                face = int(run.get("face", "0"))
            except ValueError as exc:
                raise ValueError("CDXML consumer text face is invalid") from exc
            result.extend(
                [(self.fonts[identity], size, face, self.color(run))]
                * len(run.text or "")
            )
        return result


def _same_color(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return all(round(x * 255) == round(y * 255) for x, y in zip(a, b, strict=True))


def _witnessed_exceptional_hydrogen_context(
    scene: _Scene, node: ET.Element, bonds: list[ET.Element]
) -> bool:
    """Limit the seven TS exceptions to the witnessed topology and display."""
    fragment = scene.parents[node]
    owner = scene.parents[fragment]
    if node.get("Element") == "1":
        return (
            owner.tag == "page"
            and len(bonds) == 2
            and all(
                b.get("Order", "1") == "1"
                and b.get("Display", "Solid") == "Dash"
                and b.get("Display2", "Solid") == "Solid"
                for b in bonds
            )
        )
    degree = 5 if node.get("Element") == "15" else 2
    if (
        owner.tag != "n"
        or owner.get("NodeType") != "Fragment"
        or owner.findall("fragment") != [fragment]
        or len(bonds) != degree
        or len(fragment.findall("b")) != degree
        or len(fragment.findall("n")) != degree + 1
        or any(
            b.get("B") != node.get("id")
            or b.get("Order", "1") != "1"
            or b.get("Display", "Solid") != "Solid"
            or b.get("Display2", "Solid") != "Solid"
            for b in bonds
        )
    ):
        return False
    ports = fragment.get("ConnectionOrder", "").split()
    external = [
        n.get("id")
        for n in fragment.findall("n")
        if n.get("NodeType") == "ExternalConnectionPoint"
    ]
    ordered = owner.get("BondOrdering", "").split()
    outer = [
        b
        for b in scene.parents[owner].findall("b")
        if owner.get("id") in (b.get("B"), b.get("E"))
    ]
    if (
        len(ports) != degree
        or len(set(ports)) != degree
        or set(ports) != set(external)
        or set(ports) != {b.get("E") for b in bonds}
        or len(ordered) != degree
        or len(set(ordered)) != degree
        or len(outer) != degree
        or set(ordered) != {b.get("id") for b in outer}
    ):
        return False
    signature = sorted(
        (
            b.get("Order", "1"),
            b.get("Display", "Solid"),
            b.get("Display2", "Solid"),
            "B" if b.get("B") == owner.get("id") else "E",
        )
        for b in outer
    )
    expected = (
        [
            ("Dash", "B"),
            ("Solid", "B"),
            ("Solid", "B"),
            ("WedgeBegin", "B"),
            ("WedgedHashBegin", "B"),
        ]
        if degree == 5
        else [("Dash", "E"), ("Solid", "B")]
    )
    return signature == sorted(
        ("1", display, "Solid", end) for display, end in expected
    )


def _native_hydrogen_default(scene: _Scene, node: ET.Element) -> str | None:
    """Recognize only the native-witnessed omission/explicit-count forms."""
    allowed = {
        "id",
        "p",
        "Z",
        "color",
        "NodeType",
        "Element",
        "Charge",
        "NumHydrogens",
        "GenericNickname",
        "AtomID",
        "NeedsClean",
        "Warning",
    }
    if set(node.attrib) - allowed:
        return None
    kind = node.get("NodeType", "Element")
    text = node.find("t")
    spelling = "" if text is None else "".join(s.text or "" for s in text.findall("s"))
    if kind == "GenericNickname":
        return (
            "0" if node.get("GenericNickname") == "ARY" and spelling == "ARY" else None
        )
    if kind != "Element" or scene.parents[node].tag != "fragment":
        return None
    identity = node.get("id")
    bonds = [
        b
        for b in scene.parents[node].findall("b")
        if identity in (b.get("B"), b.get("E"))
    ]
    if not bonds or any(b.get("Order", "1") not in {"1", "2"} for b in bonds):
        return None
    total = sum(int(b.get("Order", "1")) for b in bonds)
    element, charge = node.get("Element", "6"), node.get("Charge", "0")
    if element == "6" and charge == "0" and text is None and total in {1, 4}:
        return str(4 - total)
    # These labels contain no attached H count. Even in a TS graph that causes
    # a valence warning, native zero records the unchanged label's meaning;
    # it does not authorize repairing that graph or guessing implicit H.
    witnessed = {
        ("15", "0"): ("P", {5}),
        ("8", "0"): ("O", {2}),
        ("1", "0"): ("H", {1, 2}),
        ("15", "1"): ("P+", {4, 5}),
        ("8", "-1"): ("O-", {1, 2}),
    }
    expected = witnessed.get((element, charge))
    exceptional = (element, charge, total) in {
        ("1", "0", 2),
        ("15", "1", 5),
        ("8", "-1", 2),
    }
    if (
        expected is not None
        and spelling == expected[0]
        and total in expected[1]
        and text is not None
        and text.get("InterpretChemically", "yes") == "yes"
        and (
            not exceptional
            or _witnessed_exceptional_hydrogen_context(scene, node, bonds)
        )
    ):
        return "0"
    return None


def _same_hydrogens(a: _Scene, x: ET.Element, b: _Scene, y: ET.Element) -> bool:
    old, new = x.get("NumHydrogens"), y.get("NumHydrogens")
    if old == new:
        return True
    if old is not None and new is not None:
        return False
    explicit = new if old is None else old
    return (
        explicit is not None
        and explicit == _native_hydrogen_default(a, x)
        and explicit == _native_hydrogen_default(b, y)
    )


def _line_fallbacks(scene: _Scene) -> dict[str, ET.Element]:
    """Resolve only native no-head line aliases, never match by nearby geometry."""
    arrows = {x.attrib["id"]: x for x in scene.objects("arrow").values()}
    aliases: dict[str, ET.Element] = {}
    targets: set[str] = set()
    for graphic in scene.objects("graphic").values():
        target = graphic.get("SupersededBy")
        if target is None:
            continue
        arrow = arrows.get(target)
        if (
            arrow is None
            or target in targets
            or graphic.get("GraphicType") != "Line"
            or graphic.get("ArrowType", "NoHead") != "NoHead"
            or scene.owner(graphic) != scene.owner(arrow)
            or graphic.get("LineType", "Solid") != arrow.get("LineType", "Solid")
            or not _same_color(scene.color(graphic), scene.color(arrow))
        ):
            raise ValueError("CDXML consumer reference has invalid line alias")
        head = numbers(arrow.get("Head3D", ""), 3)
        tail = numbers(arrow.get("Tail3D", ""), 3)
        _compare_points(
            graphic.get("BoundingBox", ""),
            " ".join(map(str, (*head[:2], *tail[:2]))),
            4,
            "line alias geometry",
        )
        _compare_points(
            scene.inherited(graphic, "LineWidth", ""),
            scene.inherited(arrow, "LineWidth", ""),
            1,
            "line alias stroke",
        )
        aliases[graphic.attrib["id"]] = arrow
        targets.add(target)
    return aliases


def _validate_arrows(
    source: _Scene, measured: _Scene, aliases: dict[str, ET.Element]
) -> dict[ET.Element, ET.Element]:
    matched: dict[ET.Element, ET.Element] = {}
    originals = {x.attrib["id"]: x for x in source.objects("arrow").values()}
    outputs = {x.attrib["id"]: x for x in measured.objects("arrow").values()}
    used: set[str] = set()
    for identity, x in originals.items():
        y = outputs.get(identity)
        if y is None:
            y = aliases.get(identity)
        if y is None or y.attrib["id"] in used:
            raise ValueError("CDXML consumer reference changed arrow inventory")
        used.add(y.attrib["id"])
        matched[x] = y
        if source.owner(x) != measured.owner(y):
            raise ValueError("CDXML consumer reference changed arrow ownership")
        # Only straight, unheaded line primitives are emitted by Chemvas.
        # A visible arrowhead remains separate line primitives in a group.
        for item in (x, y):
            allowed = {
                "id",
                "Z",
                "BoundingBox",
                "Head3D",
                "Tail3D",
                "Center3D",
                "MajorAxisEnd3D",
                "MinorAxisEnd3D",
                "LineWidth",
                "LineType",
                "FillType",
                "ArrowheadType",
                "ArrowheadHead",
                "ArrowheadTail",
                "HeadSize",
                "ArrowheadCenterSize",
                "ArrowheadWidth",
                "color",
                "AngularSize",
                "NoGo",
            }
            if set(item.attrib) - allowed:
                raise ValueError("CDXML consumer reference has unsupported arrow paint")
            if any(
                item.get(key, default) != default
                for key, default in {
                    "FillType": "None",
                    "ArrowheadType": "Solid",
                    "ArrowheadHead": "None",
                    "ArrowheadTail": "None",
                    "AngularSize": "0",
                    "NoGo": "None",
                }.items()
            ):
                raise ValueError("CDXML consumer reference changed arrow semantics")
        if x.get("LineType", "Solid") != y.get("LineType", "Solid"):
            raise ValueError("CDXML consumer reference changed arrow line type")
        for key in ("Head3D", "Tail3D"):
            _compare_points(x.get(key, ""), y.get(key, ""), 3, "arrow endpoint")
        _compare_points(
            source.inherited(x, "LineWidth", ""),
            measured.inherited(y, "LineWidth", ""),
            1,
            "arrow stroke size",
        )
        if not _same_color(source.color(x), measured.color(y)):
            raise ValueError("CDXML consumer reference changed arrow color")
    if used != set(outputs):
        raise ValueError("CDXML consumer reference changed arrow inventory")
    return matched


def _validate_bond_spacing(
    source: _Scene, x: ET.Element, measured: _Scene, y: ET.Element
) -> None:
    """Compare both effective spacing forms, including newly added overrides.

    BondSpacing is a percentage, not a point coordinate. Native rounding of
    that percentage is not evidence of identical spacing and must fail closed.
    """
    for key in ("BondSpacing", "BondSpacingAbs"):
        old = source.inherited(x, key, "")
        new = measured.inherited(y, key, "")
        if not old and not new:
            continue
        try:
            a, b = numbers(old, 1)[0], numbers(new, 1)[0]
        except ValueError as exc:
            raise ValueError(
                "CDXML consumer reference has invalid bond spacing"
            ) from exc
        tolerance = 1e-8 if key == "BondSpacing" else COORDINATE_TOLERANCE_PT
        if min(a, b) < 0 or abs(a - b) > tolerance:
            raise ValueError("CDXML consumer reference changed bond spacing")


def _validate_objects(source: _Scene, measured: _Scene) -> None:
    old_aliases, new_aliases = _line_fallbacks(source), _line_fallbacks(measured)
    matched_arrows = _validate_arrows(source, measured, new_aliases)
    for key in ("BondLength", "LineWidth", "BoldWidth", "BondSpacing", "HashSpacing"):
        if key in source.root.attrib:
            _compare_points(
                source.root.attrib[key],
                measured.root.get(key, ""),
                1,
                "drawing scale or stroke defaults",
            )
    defaults = {
        "n": {
            "NodeType": "Element",
            "Element": "6",
            "Charge": "0",
            "Isotope": "0",
            "Radical": "0",
            "GenericNickname": "",
            "BondOrdering": "",
        },
        "b": {
            "B": "",
            "E": "",
            "Order": "1",
            "Display": "Solid",
            "Display2": "Solid",
            "DoublePosition": "",
            "BeginAttach": "0",
            "EndAttach": "0",
        },
        "graphic": {
            "GraphicType": "",
            "LineType": "Solid",
            "RectangleType": "Plain",
            "OvalType": "Circle",
            "ArrowType": "NoHead",
        },
        "fragment": {"ConnectionOrder": ""},
        "group": {},
    }
    for tag, attributes in defaults.items():
        a, b = source.objects(tag), measured.objects(tag)
        if tag == "graphic":
            a = {
                key: value
                for key, value in a.items()
                if value.get("id") not in old_aliases
            }
            b = {
                key: value
                for key, value in b.items()
                if value.get("id") not in new_aliases
            }
        if set(a) != set(b):
            raise ValueError(f"CDXML consumer reference changed {tag} object inventory")
        for identity, x in a.items():
            y = b[identity]
            if source.owner(x) != measured.owner(y):
                raise ValueError("CDXML consumer reference changed object ownership")
            if any(
                x.get(key, default) != y.get(key, default)
                for key, default in attributes.items()
            ):
                raise ValueError(
                    f"CDXML consumer reference changed {tag} semantics or topology"
                )
            if not _same_color(source.color(x), measured.color(y)):
                raise ValueError("CDXML consumer reference changed object color")
            for key, count in [
                ("p", 2),
                ("BoundingBox", 4),
                ("Center3D", 3),
                ("MajorAxisEnd3D", 3),
                ("MinorAxisEnd3D", 3),
            ]:
                if key in x.attrib and tag in {"n", "graphic"}:
                    _compare_points(
                        x.attrib[key], y.get(key, ""), count, f"{tag} geometry"
                    )
            if tag == "n" and not _same_hydrogens(source, x, measured, y):
                raise ValueError("CDXML consumer reference changed hydrogen count")
            if tag == "b":
                _validate_bond_spacing(source, x, measured, y)
            for key in ("LineWidth", "BoldWidth", "BondSpacingAbs", "MarginWidth"):
                if key in x.attrib:
                    _compare_points(
                        x.attrib[key],
                        measured.inherited(y, key, ""),
                        1,
                        "object stroke size",
                    )

    fills = {
        key: item
        for key, item in source.objects("graphic").items()
        if item.get("GraphicType") == "Rectangle"
        and item.get("RectangleType") == "Filled"
    }
    native_graphics = measured.objects("graphic")
    for old_line, new_line in matched_arrows.items():
        for fill_identity, old_fill in fills.items():
            new_fill = native_graphics[fill_identity]
            if line_overlaps_filled_rectangle(
                old_line, old_fill, source.inherited(old_line, "LineWidth", "")
            ) or line_overlaps_filled_rectangle(
                new_line, new_fill, measured.inherited(new_line, "LineWidth", "")
            ):
                validate_relative_order(old_line, old_fill, new_line, new_fill)


def _validate_all_text(
    source: _Scene, measured: _Scene, font_map: dict[str, str]
) -> None:
    a, b = source.texts(), measured.texts()
    if set(a) != set(b):
        raise ValueError("CDXML consumer reference changed text object inventory")
    used_fonts: set[str] = set()
    for key, x in a.items():
        y = b[key]
        if "".join(s.text or "" for s in x.findall("s")) != "".join(
            s.text or "" for s in y.findall("s")
        ):
            raise ValueError("CDXML consumer reference changed caption text")
        if source.owner(x) != measured.owner(y):
            raise ValueError("CDXML consumer reference changed text ownership")
        if x.get("InterpretChemically", "yes") != y.get("InterpretChemically", "yes"):
            raise ValueError("CDXML consumer reference changed text interpretation")
        if "LineStarts" in y.attrib:
            raise ValueError("CDXML consumer reference rewrapped a caption line")

        if source.alignment(x) != measured.alignment(y):
            raise ValueError("CDXML consumer reference changed text justification")
        _compare_points(x.get("p", ""), y.get("p", ""), 2, "caption position")
        try:
            if int(x.get("RotationAngle", "0")) % (360 * 65536) != int(
                y.get("RotationAngle", "0")
            ) % (360 * 65536):
                raise ValueError("CDXML consumer reference changed caption rotation")
        except ValueError as exc:
            raise ValueError(
                "CDXML consumer reference changed caption rotation"
            ) from exc
        xr, yr = source.runs(x), measured.runs(y)
        if len(xr) != len(yr):
            raise ValueError("CDXML consumer reference changed text runs")
        for (xf, xs, xb, xc), (yf, ys, yb, yc) in zip(xr, yr, strict=True):
            used_fonts.add(xf)
            if font_map.get(xf) != yf:
                raise ValueError(
                    "CDXML consumer reference changed expected font mapping"
                )
            # Consumer text sizes are quantized to twentieths of a point. Record
            # this as consumer precision; never describe it as exact preservation.
            size_same = abs(xs - ys) <= 1e-8
            size_quantized = (
                abs(xs - ys) <= 0.0250001 and abs(ys * 20 - round(ys * 20)) < 1e-7
            )
            if not (size_same or size_quantized) or xb != yb:
                raise ValueError(
                    "CDXML consumer reference changed caption size or face"
                )
            if not _same_color(xc, yc):
                raise ValueError("CDXML consumer reference changed text color")
    if used_fonts != set(font_map):
        raise ValueError("CDXML expected font mapping does not match source fonts")


def validate_consumer_paint_colors(producer: ET.Element, native: ET.Element) -> None:
    """Verify corresponding logical paint colors without accepting other fidelity.

    Native line aliases retain the existing strict arrow checks. Text content,
    object inventory and ownership are required so palette recovery cannot hide
    an intentional recoloring or assign a producer color to a different object.
    """
    source, measured = _Scene(producer), _Scene(native)
    old_aliases, new_aliases = _line_fallbacks(source), _line_fallbacks(measured)
    _validate_arrows(source, measured, new_aliases)
    for tag in ("n", "b", "fragment", "group", "graphic"):
        before, after = source.objects(tag), measured.objects(tag)
        if tag == "graphic":
            before = {k: v for k, v in before.items() if v.get("id") not in old_aliases}
            after = {k: v for k, v in after.items() if v.get("id") not in new_aliases}
        if before.keys() != after.keys():
            raise ValueError("CDXML palette recovery changed object inventory")
        for key, item in before.items():
            other = after[key]
            if source.owner(item) != measured.owner(other):
                raise ValueError("CDXML palette recovery changed object ownership")
            if not _same_color(source.color(item), measured.color(other)):
                raise ValueError("CDXML palette recovery changed object color")
    before_text, after_text = source.texts(), measured.texts()
    if before_text.keys() != after_text.keys():
        raise ValueError("CDXML palette recovery changed text inventory")
    for key, text in before_text.items():
        other = after_text[key]
        if "".join(run.text or "" for run in text.findall("s")) != "".join(
            run.text or "" for run in other.findall("s")
        ):
            raise ValueError("CDXML palette recovery changed text content")
        before_runs, after_runs = source.runs(text), measured.runs(other)
        if len(before_runs) != len(after_runs) or any(
            not _same_color(a[3], b[3])
            for a, b in zip(before_runs, after_runs, strict=True)
        ):
            raise ValueError("CDXML palette recovery changed text color")
    for attribute, default in (("color", "3"), ("bgcolor", "2")):
        a = ET.Element("color-reference", color=source.root.get(attribute, default))
        b = ET.Element("color-reference", color=measured.root.get(attribute, default))
        if not _same_color(source.color(a), measured.color(b)):
            raise ValueError("CDXML palette recovery changed document color")


def validate_consumer_objects(
    source: ET.Element, measured: ET.Element, font_map: dict[str, str]
) -> None:
    """Reject changed graph, object geometry and every text, including no-ID labels."""
    a, b = _Scene(source), _Scene(measured)
    _validate_objects(a, b)
    _validate_all_text(a, b, font_map)
