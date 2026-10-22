"""Bounded CDXML document import and integrity-bound editable snapshots.

Native objects are the interchange representation. A snapshot comment preserves
Chemvas-only editing state only while the native XML remains byte-identical.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from chemvas.domain.atom_aliases import ATOM_ALIAS_DEFINITIONS
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    MAX_DOCUMENT_BYTES,
    build_document_payload,
    extract_document_state,
    normalize_json_numbers,
)
from chemvas.domain.json_io import strict_json_loads
from chemvas.features.document_composition import compose_document_state

_MARKER = re.compile(
    rb"\n<!-- ChemvasDocument:([0-9a-f]{64}):([A-Za-z0-9+/=]+) -->[ \t\r\n]*\Z"
)
_ELEMENTS = (
    "? H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni "
    "Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe "
    "Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg "
    "Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg "
    "Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og"
).split()


@dataclass(frozen=True)
class CdxmlDocument:
    state: dict[str, Any]
    source_sha256: str


def embed_document(raw: bytes, state: dict[str, Any]) -> bytes:
    payload = build_document_payload(state, CANVAS_FILE_VERSION)
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=True).encode())
    result = (
        raw
        + b"\n<!-- ChemvasDocument:"
        + hashlib.sha256(raw).hexdigest().encode()
        + b":"
        + encoded
        + b" -->\n"
    )
    if len(result) > MAX_DOCUMENT_BYTES:
        raise ValueError("CDXML document exceeds the document byte limit")
    return result


def read_cdxml_document(path: str | Path) -> CdxmlDocument:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
    return parse_cdxml_document(raw, preserve_source=True)


def parse_cdxml_document(raw: bytes, *, preserve_source: bool = False) -> CdxmlDocument:
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("CDXML document exceeds the document byte limit")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8-sig")
        if "<!ENTITY" in text or re.search(r"<!DOCTYPE[^>]*\[", text):
            raise ValueError(
                "CDXML entity declarations and internal DTDs are not supported"
            )
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError) as exc:
        raise ValueError("Not a valid UTF-8 CDXML document") from exc
    if root.tag != "CDXML" or len(root.findall("page")) != 1:
        raise ValueError("CDXML editing requires exactly one page")
    match = _MARKER.search(raw)
    if match and hashlib.sha256(raw[: match.start()]).hexdigest().encode() == match[1]:
        payload = strict_json_loads(
            base64.b64decode(match[2], validate=True).decode("utf-8")
        )
        extract_document_state(payload)
        normalized = normalize_json_numbers(payload)
        assert isinstance(normalized, dict)
        from chemvas.features.cdxml_editable_arrows import promote_snapshot_arrows

        promote_snapshot_arrows(normalized["state"])
        build_document_payload(normalized["state"], CANVAS_FILE_VERSION)
        return CdxmlDocument(normalized["state"], digest)
    if preserve_source:
        from chemvas.features.cdxml_preservation import PreservingImporter

        state = PreservingImporter(text).state()
    else:
        state = _Importer(root).state()
    build_document_payload(state, CANVAS_FILE_VERSION)
    return CdxmlDocument(state, digest)


class _Importer:
    def __init__(self, root: ET.Element):
        if root.tag != "CDXML" or len(root.findall("page")) != 1:
            raise ValueError("CDXML editing requires exactly one page")
        self.root = root
        if root.get("InterpretChemically", "yes") != "yes":
            self.unsupported(root, "nonchemical drawing")
        self.parents = {c: p for p in root.iter() for c in p}
        objects = list(root.iter())
        if len(objects) > 100_000:
            raise ValueError("CDXML has too many objects")
        ids = [
            e.get("id") for e in objects if e.get("id") is not None and e.tag != "font"
        ]
        if len(set(ids)) != len(ids):
            raise ValueError("CDXML contains duplicate object IDs")
        allowed = {
            "CDXML",
            "page",
            "fragment",
            "n",
            "b",
            "t",
            "s",
            "fonttable",
            "font",
            "colortable",
            "color",
            "arrow",
            "graphic",
            "group",
        }
        for e in objects:
            if e.tag not in allowed:
                self.unsupported(e, f"object {e.tag}")
        placements = {
            "page": {"CDXML"},
            "fragment": {"page", "group"},
            "n": {"fragment"},
            "b": {"fragment"},
            "t": {"page", "group", "n"},
            "s": {"t"},
            "arrow": {"page", "group"},
            "graphic": {"page", "group"},
            "group": {"page"},
            "fonttable": {"CDXML"},
            "colortable": {"CDXML"},
            "font": {"fonttable"},
            "color": {"colortable"},
        }
        for e in objects[1:]:
            if self.parents[e].tag not in placements.get(e.tag, set()):
                self.unsupported(e, "nested object placement")
        for fragment in root.iter("fragment"):
            self.attributes(fragment, "id Z BoundingBox color")
        self.colors = ["#ffffff", "#000000"]
        for color in root.findall("./colortable/color"):
            rgb = [self.number(color.get(k, ""), color) for k in ("r", "g", "b")]
            if not all(0 <= c <= 1 for c in rgb):
                raise ValueError("CDXML color is outside 0..1")
            self.colors.append("#" + "".join(f"{round(c * 255):02x}" for c in rgb))
        self.fonts = {
            f.get("id"): f.get("name", "") for f in root.findall("./fonttable/font")
        }
        self.caption_font = self.fonts.get(root.get("CaptionFont"), "Arial")
        page = root.find("page")
        assert page is not None
        self.page = page
        bounds = self.page.get("BoundingBox", "0 0 842 595").split()
        if len(bounds) != 4:
            self.unsupported(self.page, "page bounds")
        left, top, right, bottom = [self.number(v, self.page) for v in bounds]
        width = self.number(self.page.get("Width", str(right - left)), self.page)
        height = self.number(self.page.get("Height", str(bottom - top)), self.page)
        if width <= 0 or height <= 0:
            raise ValueError("CDXML page dimensions must be positive")
        self.offset = (left + width / 2, top + height / 2)
        self.sheet_mm = [width * 25.4 / 72, height * 25.4 / 72]
        self.nodes = list(self.page.iter("n"))
        self.node_ids = {e.get("id"): i for i, e in enumerate(self.nodes)}
        if None in self.node_ids:
            raise ValueError("CDXML atoms require IDs")

    @staticmethod
    def unsupported(e: ET.Element, reason: str) -> NoReturn:
        raise ValueError(
            f"Unsupported CDXML {e.tag} #{e.get('id', '?')}: {reason}. No document was opened or overwritten."
        )

    def number(self, value: str, e: ET.Element) -> float:
        try:
            n = float(value)
        except ValueError as exc:
            raise ValueError(f"Invalid CDXML number on {e.tag}") from exc
        if not math.isfinite(n) or abs(n) > 1_000_000:
            raise ValueError(f"CDXML number out of range on {e.tag}")
        return n

    def inherited(self, e: ET.Element, key: str, default: str) -> str:
        current: ET.Element | None = e
        while current is not None:
            if key in current.attrib:
                return current.attrib[key]
            current = self.parents.get(current)
        return default

    def color(self, e: ET.Element, attribute: str = "color", default: str = "0") -> str:
        index = int(self.inherited(e, attribute, default))
        if index == 0 and "fgcolor" in self.root.attrib:
            index = int(self.root.attrib["fgcolor"])
        if index == 0:
            return "#000000"
        if index == 1:
            return "#ffffff"
        if index >= len(self.colors) or index < 0:
            raise ValueError("CDXML references a missing color")
        return self.colors[index]

    def point(self, value: str, e: ET.Element, count: int = 2) -> list[float]:
        values = [self.number(x, e) for x in value.split()]
        if len(values) != count or (count == 3 and values[2] != 0):
            self.unsupported(e, "invalid or three-dimensional position")
        return [values[0] - self.offset[0], values[1] - self.offset[1]]

    def attributes(self, e: ET.Element, allowed: str) -> None:
        extra = set(e.attrib) - set(allowed.split())
        if extra:
            self.unsupported(e, "properties " + ", ".join(sorted(extra)))

    def atom(self, e: ET.Element, index: int) -> dict[str, Any]:
        self.attributes(
            e,
            "id p Z Element NodeType Charge NumHydrogens Geometry AS CIP ShowAtomQuery ShowAtomStereo ShowTerminalCarbonLabels ShowNonTerminalCarbonLabels ShowNonTerminalCarbonLabel color Warning SuppressWarnings AtomID NeedsClean BondOrdering IgnoreWarnings",
        )
        stereo = e.get("AS", "N")
        if stereo not in ("N", "U", "u", "R", "S"):
            self.unsupported(e, "absolute atom stereochemistry")
        if stereo in ("R", "S") and not any(
            (
                bond.get("B") == e.get("id")
                and bond.get("Display") in ("WedgeBegin", "WedgedHashBegin")
            )
            or (
                bond.get("E") == e.get("id")
                and bond.get("Display") in ("WedgeEnd", "WedgedHashEnd")
            )
            for bond in self.page.iter("b")
        ):
            self.unsupported(
                e, "absolute stereochemistry without an explicit stereo bond"
            )
        if e.get("NodeType", "Element") != "Element" or any(c.tag != "t" for c in e):
            self.unsupported(e, "abbreviated, query, or nested atom")
        z = int(e.get("Element", "6"))
        if not 1 <= z < len(_ELEMENTS):
            self.unsupported(e, "atomic number")
        symbol = _ELEMENTS[z]
        label = "".join(e.itertext()).strip()
        # Display labels may include the element and explicit hydrogen count.
        if label and not re.fullmatch(re.escape(symbol) + r"(H[0-9]*)?", label):
            self.unsupported(e, "label differs from its chemical element")
        if label and label != symbol:
            alias = ATOM_ALIAS_DEFINITIONS.get(label)
            if alias is None or alias.terminal_hydrogens is None:
                self.unsupported(e, "explicit hydrogen label")
            if (
                "NumHydrogens" in e.attrib
                and int(e.attrib["NumHydrogens"]) != alias.terminal_hydrogens
            ):
                self.unsupported(e, "hydrogen label/count mismatch")
            symbol = label
        x, y = self.point(e.get("p", ""), e)
        result: dict[str, Any] = dict(
            id=index,
            element=symbol,
            x=x,
            y=y,
            color=self.color(e),
            explicit_label=bool(label),
        )
        if "Charge" in e.attrib:
            result["formal_charge"] = int(e.attrib["Charge"])
        if "NumHydrogens" in e.attrib and symbol == _ELEMENTS[z]:
            # Accept redundant zero-H constraints only when the ordinary neutral
            # valence is already saturated. Never silently remove a radical or
            # nonstandard hydrogen constraint.
            valence = {
                "H": 1,
                "B": 3,
                "C": 4,
                "N": 3,
                "O": 2,
                "F": 1,
                "Cl": 1,
                "Br": 1,
                "I": 1,
            }.get(symbol)
            order_sum = sum(
                self.number(b.get("Order", "1"), b)
                for b in self.page.iter("b")
                if e.get("id") in (b.get("B"), b.get("E"))
            )
            if (
                int(e.attrib["NumHydrogens"]) != 0
                or int(e.get("Charge", "0")) != 0
                or valence != order_sum
            ):
                self.unsupported(
                    e, "explicit hydrogen count; expand hydrogens before importing"
                )
        return result

    def bond(self, e: ET.Element) -> dict[str, Any]:
        self.attributes(
            e,
            "id B E Order Display Display2 DoublePosition Z color BS CIP BondCircularOrdering CrossingBonds ShowBondQuery ShowBondStereo BondLength IgnoreWarnings",
        )
        if e.get("B") not in self.node_ids or e.get("E") not in self.node_ids:
            raise ValueError("CDXML bond references a missing atom")
        order = int(e.get("Order", "1"))
        if order not in (1, 2, 3):
            self.unsupported(e, "bond order")
        display = e.get("Display", "Solid")
        styles = {
            "Solid": {1: "single", 2: "double", 3: "triple"},
            "WedgeBegin": {1: "wedge"},
            "WedgeEnd": {1: "wedge"},
            "WedgedHashBegin": {1: "hash"},
            "WedgedHashEnd": {1: "hash"},
            "Dash": {1: "dotted"},
            "Bold": {1: "bold_in"},
        }
        style = styles.get(display, {}).get(order)
        if style is None or e.get("Display2", "Solid") != "Solid":
            self.unsupported(e, "bond display")
        a, b = self.node_ids[e.get("B")], self.node_ids[e.get("E")]
        if display.endswith("End"):
            a, b = b, a
        if order == 2 and display == "Solid":
            position = e.get("DoublePosition", "Auto")
            if position == "Center":
                style = "double_center"
            elif position == "Right":
                style = "double_outer"
            elif position not in ("Auto", "Left"):
                self.unsupported(e, "double bond position")
        return dict(a=a, b=b, order=order, style=style, color=self.color(e))

    def note(self, e: ET.Element) -> dict[str, Any]:
        self.attributes(
            e, "id p BoundingBox Z color Justification CaptionJustification LineHeight"
        )
        if e.get("Justification", "Left") not in ("Left", "0"):
            self.unsupported(e, "text alignment")
        x, y = self.point(e.get("p", ""), e)
        runs: list[dict[str, Any]] = []
        for run in e:
            if run.tag != "s":
                self.unsupported(run, "text child")
            self.attributes(run, "font size face color")
            font_id = run.get("font", self.root.get("CaptionFont"))
            if font_id is not None and self.fonts.get(font_id) != self.caption_font:
                self.unsupported(run, "mixed or unknown caption font")
            size = self.number(run.get("size", self.root.get("CaptionSize", "12")), run)
            if not size.is_integer() or not 6 <= size <= 96:
                self.unsupported(run, "text size outside editable integer range 6..96")
            face = int(run.get("face", "0"))
            if face & ~0x63:
                self.unsupported(run, "text face")
            style = dict(
                font_size=int(size),
                font_weight=700 if face & 1 else 400,
                italic=bool(face & 2),
                color=self.color(run),
            )
            if face & 0x60:
                style["vertical_align"] = "sub" if face & 0x20 else "super"
            runs.append(dict(text=run.text or "", style=style))
        if not runs:
            self.unsupported(e, "empty text")
        # CDXML p is a baseline; the note origin is the top of its text box.
        if "BoundingBox" in e.attrib:
            box = e.attrib["BoundingBox"].split()
            if len(box) != 4:
                self.unsupported(e, "text bounds")
            x, y = self.point(" ".join(box[:2]), e)
        else:
            y -= float(runs[0]["style"]["font_size"])
        return dict(x=x, y=y, runs=runs)

    def arrow(self, e: ET.Element) -> dict[str, Any]:
        self.attributes(
            e,
            "id Z color BoundingBox Tail3D Head3D ArrowheadType ArrowheadHead ArrowheadTail FillType LineType HeadSize AngularSize",
        )
        if (
            e.get("ArrowheadTail", "None") != "None"
            or e.get("ArrowheadHead", "None") not in ("None", "Full")
            or e.get("ArrowheadType", "Solid") != "Solid"
            or e.get("LineType", "Solid") != "Solid"
        ):
            self.unsupported(e, "arrow style")
        return dict(
            kind="arrow" if e.get("ArrowheadHead", "None") == "Full" else "line",
            start=self.point(e.get("Tail3D", ""), e, 3),
            end=self.point(e.get("Head3D", ""), e, 3),
            color=self.color(e),
        )

    def graphic(self, e: ET.Element) -> tuple[str, dict[str, Any]]:
        self.attributes(e, "id Z color BoundingBox GraphicType LineType RectangleType")
        coords = e.get("BoundingBox", "").split()
        if len(coords) != 4:
            self.unsupported(e, "graphic bounds")
        first = self.point(" ".join(coords[:2]), e)
        second = self.point(" ".join(coords[2:]), e)
        if e.get("GraphicType") == "Line":
            line = {"Solid": "line", "Dashed": "line_dashed", "Bold": "line_bold"}.get(
                e.get("LineType", "Solid")
            )
            if line is None:
                self.unsupported(e, "line type")
            return "arrows", dict(
                kind=line, start=first, end=second, color=self.color(e)
            )
        if (
            e.get("GraphicType") == "Rectangle"
            and e.get("RectangleType", "Plain") == "Plain"
            and self.color(e) == "#000000"
        ):
            return "shapes", dict(
                shape_kind="rect",
                stroke_style="solid",
                left=min(first[0], second[0]),
                top=min(first[1], second[1]),
                right=max(first[0], second[0]),
                bottom=max(first[1], second[1]),
            )
        self.unsupported(e, "graphic type or style")

    def state(self) -> dict[str, Any]:
        notes: list[dict[str, Any]] = []
        arrows: list[dict[str, Any]] = []
        shapes: list[dict[str, Any]] = []
        references: dict[ET.Element, list[Any]] = {}
        for e in self.page.iter():
            if e.tag == "t" and self.parents[e].tag in {"page", "group"}:
                references[e] = ["notes", len(notes)]
                notes.append(self.note(e))
            elif e.tag == "arrow":
                references[e] = ["arrows", len(arrows)]
                arrows.append(self.arrow(e))
            elif e.tag == "graphic":
                collection, record = self.graphic(e)
                target = arrows if collection == "arrows" else shapes
                references[e] = [collection, len(target)]
                target.append(record)
        state = compose_document_state(
            dict(
                format="chemvas-document-composition",
                version=1,
                atoms=[self.atom(e, i) for i, e in enumerate(self.nodes)],
                bonds=[self.bond(e) for e in self.page.iter("b")],
                notes=notes,
                arrows=arrows,
                shapes=shapes,
                settings={
                    "sheet_size": "Custom",
                    "sheet_custom_size_mm": self.sheet_mm,
                    "text_font_family": self.caption_font,
                    "bond_length_px": self.number(
                        self.root.get("BondLength", "20"), self.root
                    ),
                },
            )
        )
        groups = []
        for group in self.page.iter("group"):
            self.attributes(group, "id Z BoundingBox")
            atoms = [self.node_ids[e.get("id")] for e in group.iter("n")]
            items = [references[e] for e in group.iter() if e in references]
            if atoms or items:
                groups.append(dict(atoms=atoms, items=items))
        if groups:
            state["groups"] = groups
        build_document_payload(state, CANVAS_FILE_VERSION)
        return state
