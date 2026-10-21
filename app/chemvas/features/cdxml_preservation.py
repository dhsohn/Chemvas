"""Native CDXML document ownership and editing projections.

A projection is never the source of truth for an untouched native object. The
original XML, including nested fragments and reaction references, travels with
its projection through native document saves and recovery.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy
from html import escape
from typing import Any, override

from chemvas.domain.document import CANVAS_FILE_VERSION, build_document_payload
from chemvas.domain.document.cdxml_source import parse_native_xml
from chemvas.features.cdxml_document import _ELEMENTS, _Importer
from chemvas.features.document_composition import compose_document_state


class PreservingImporter(_Importer):
    def __init__(self, xml: str):
        root = parse_native_xml(xml)
        self.root = root
        self.parents = {c: p for p in root.iter() for c in p}
        page = root.find("page")
        assert page is not None
        self.page = page
        known = {
            "CDXML",
            "page",
            "fonttable",
            "font",
            "colortable",
            "color",
            "group",
            "fragment",
            "n",
            "b",
            "t",
            "s",
            "graphic",
            "arrow",
            "curve",
            "scheme",
            "step",
            "represent",
            "objecttag",
            "bracketedgroup",
            "bracketattachment",
            "crossingbond",
            "ColoredMolecularArea",
            "embeddedobject",
            "annotation",
        }
        for e in root.iter():
            if e.tag not in known:
                self.unsupported(e, "unrecognized native object")
        ids = [
            e.attrib["id"]
            for e in root.iter()
            if e.get("id") and e.tag not in {"font", "objecttag"}
        ]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate native CDXML object IDs.")
        next_id = max((int(v) for v in ids if v.isdigit()), default=0) + 1
        # Text inside an object tag can be visible without a native ID. Give
        # such objects a stable ID in the owned XML, never in the input file.
        for e in root.iter():
            if e.tag in {
                "t",
                "graphic",
                "arrow",
                "curve",
                "ColoredMolecularArea",
                "embeddedobject",
            } and not e.get("id"):
                e.set("id", str(next_id))
                next_id += 1
        bounds = self.page.get("BoundingBox", "0 0 842 595").split()
        if len(bounds) != 4:
            self.unsupported(self.page, "page bounds")
        left, top, right, bottom = [self.number(v, self.page) for v in bounds]
        width = self.number(self.page.get("Width", str(right - left)), self.page)
        height = self.number(self.page.get("Height", str(bottom - top)), self.page)
        if width <= 0 or height <= 0:
            raise ValueError("Invalid CDXML page size.")
        self.offset = (left + width / 2, top + height / 2)
        self.sheet_mm = [width * 25.4 / 72, height * 25.4 / 72]
        self.colors = ["#ffffff", "#000000"]
        for e in root.findall("./colortable/color"):
            rgb = [self.number(e.get(k, ""), e) for k in ("r", "g", "b")]
            if any(not 0 <= v <= 1 for v in rgb):
                raise ValueError("Invalid CDXML color.")
            self.colors.append("#" + "".join(f"{round(v * 255):02x}" for v in rgb))
        self.fonts = {
            e.get("id"): e.get("name", "Arial")
            for e in root.findall("./fonttable/font")
        }
        self.caption_font = self.fonts.get(root.get("CaptionFont"), "Arial")
        self.nodes = [e for e in self.page.iter("n") if not self.has_ancestor(e, "n")]
        self.node_ids = {e.get("id"): i for i, e in enumerate(self.nodes)}
        if None in self.node_ids:
            raise ValueError("Native atoms require IDs.")
        self.native_bonds = [
            e for e in self.page.iter("b") if not self.has_ancestor(e, "n")
        ]

    def has_ancestor(self, e: ET.Element, tag: str) -> bool:
        p = self.parents.get(e)
        while p is not None:
            if p.tag == tag:
                return True
            p = self.parents.get(p)
        return False

    @override
    def atom(self, e: ET.Element, index: int) -> dict[str, Any]:
        text = e.find("t")
        label = "".join(text.itertext()).strip() if text is not None else ""
        z = int(e.get("Element", "6"))
        if not 0 < z < len(_ELEMENTS):
            self.unsupported(e, "atomic number")
        kind = e.get("NodeType", "Element")
        if kind not in {
            "Element",
            "Fragment",
            "Nickname",
            "GenericNickname",
            "Unspecified",
        }:
            self.unsupported(e, "unsupported visible node type")
        symbol = label or _ELEMENTS[z]
        if kind != "Element" and not label:
            self.unsupported(e, "missing contracted node label")
        x, y = self.point(e.get("p", ""), e)
        result = dict(
            id=index,
            element=symbol,
            x=x,
            y=y,
            color=self.color(e),
            explicit_label=bool(label),
        )
        # Native labels/charge marks already specify appearance. Preserve the
        # underlying charge and radical in XML; separate represented graphics
        # are imported below at their exact native location.
        return result

    @override
    def bond(self, e: ET.Element) -> dict[str, Any]:
        if e.get("B") not in self.node_ids or e.get("E") not in self.node_ids:
            raise ValueError("Native bond references missing visible atom.")
        native_order = e.get("Order", "1")
        orders = {"1": 1, "2": 2, "3": 3, "1.5": 2, "2.5": 3}
        if native_order not in orders:
            self.unsupported(e, "bond order")
        order = orders[native_order]
        display = e.get("Display", "Solid")
        styles = {
            "Solid": {1: "single", 2: "double", 3: "triple"},
            "WedgeBegin": {1: "wedge"},
            "WedgeEnd": {1: "wedge"},
            "WedgedHashBegin": {1: "hash"},
            "WedgedHashEnd": {1: "hash"},
            "Hash": {1: "hash_plain"},
            "Wavy": {1: "wavy", 2: "double_either"},
            "Dash": {1: "dotted", 2: "dotted_double"},
            "Bold": {1: "bold_in", 2: "bold_center"},
        }
        if native_order in {"1.5", "2.5"} and display in {
            "WedgeBegin",
            "WedgeEnd",
            "WedgedHashBegin",
            "WedgedHashEnd",
        }:
            order = 1
        style = styles.get(display, {}).get(order)
        if style is None:
            self.unsupported(e, "bond display")
        # Fractional native orders remain exact in the source, independently
        # of the integer editor graph used to draw and manipulate the bond.
        if native_order == "1.5" and display == "Solid":
            style = "dotted_double"
        if native_order == "2.5" and display == "Solid":
            style = "triple"
        a, b = self.node_ids[e.get("B")], self.node_ids[e.get("E")]
        if display.endswith("End"):
            a, b = b, a
        if order == 2 and display == "Solid" and native_order == "2":
            style = {
                "Center": "double_center",
                "Right": "double_outer",
                "Left": "double",
                "Auto": "double",
            }.get(e.get("DoublePosition", "Auto"), "double")
        return dict(a=a, b=b, order=order, style=style, color=self.color(e))

    def caption(self, e: ET.Element) -> dict[str, Any]:
        x, y = self.point(e.get("p", ""), e)
        bbox = e.get("BoundingBox", "").split()
        if len(bbox) == 4:
            x, y = self.point(" ".join(bbox[:2]), e)
        pieces = []
        plain = []
        for run in e.findall("s"):
            text = run.text or ""
            plain.append(text)
            size = self.number(run.get("size", self.root.get("CaptionSize", "12")), run)
            if not 0 < size <= 1000:
                self.unsupported(run, "caption size")
            face = int(run.get("face", "0"))
            family = self.fonts.get(run.get("font"), self.caption_font)
            css = [
                f"font-family: {escape(family, quote=True)}",
                f"font-size: {size:g}px",
                f"color: {self.color(run)}",
            ]
            if face & 1:
                css.append("font-weight:700")
            if face & 2:
                css.append("font-style:italic")
            if face & 4:
                css.append("text-decoration:underline")
            # 96 means chemical text with automatic baseline formatting.
            if face & 0x60 == 0x20:
                css.append("vertical-align:sub")
            elif face & 0x60 == 0x40:
                css.append("vertical-align:super")
            pieces.append(
                '<span style="'
                + ";".join(css)
                + '">'
                + escape(text).replace("\n", "<br/>")
                + "</span>"
            )
        align = e.get(
            "Justification", self.root.get("CaptionJustification", "Left")
        ).lower()
        if align not in {"left", "center", "right", "justify"}:
            align = "left"
        return dict(
            x=x,
            y=y,
            text="".join(plain),
            html=f'<p style="margin-top:0;margin-bottom:0;text-align:{align}">'
            + "".join(pieces)
            + "</p>",
        )

    @override
    def state(self) -> dict[str, Any]:
        from chemvas.features.cdxml_graphics import graphic_image

        atoms = [self.atom(e, i) for i, e in enumerate(self.nodes)]
        bonds = [self.bond(e) for e in self.native_bonds]
        state = compose_document_state(
            dict(
                format="chemvas-document-composition",
                version=2,
                atoms=[],
                bonds=[],
                settings={
                    "sheet_size": "Custom",
                    "sheet_custom_size_mm": self.sheet_mm,
                    "text_font_family": self.caption_font,
                    "text_font_size": int(float(self.root.get("LabelSize", "10"))),
                    "bond_length_px": self.number(
                        self.root.get("BondLength", "20"), self.root
                    ),
                },
            )
        )
        state["model"] = {
            "atoms": {
                a["id"]: {k: v for k, v in a.items() if k != "id"} for a in atoms
            },
            "bonds": bonds,
            "next_atom_id": len(atoms),
        }
        bindings: dict[str, list[str | None]] = {"notes": [], "images": []}
        state["images"] = []
        for e in self.page.iter():
            if self.has_ancestor(e, "n"):
                continue
            if e.tag == "t" and self.inherited(e, "Visible", "yes") != "no":
                state["notes"].append(self.caption(e))
                bindings["notes"].append(e.get("id"))
            elif e.tag == "embeddedobject":
                from chemvas.features.cdxml_graphics import embedded_image

                state["images"].append(embedded_image(self, e))
                bindings["images"].append(e.get("id"))
            elif e.tag in {"graphic", "arrow", "curve", "ColoredMolecularArea"}:
                if e.get("SupersededBy"):
                    continue
                image = graphic_image(self, e)
                if image is not None:
                    state["images"].append(image)
                    bindings["images"].append(e.get("id"))
        baseline = deepcopy(state)
        state["cdxml_source"] = dict(
            xml=ET.tostring(self.root, encoding="unicode"),
            offset=list(self.offset),
            atoms={str(i): e.get("id") for i, e in enumerate(self.nodes)},
            bonds={
                f"{min(b['a'], b['b'])}:{max(b['a'], b['b'])}": e.get("id")
                for b, e in zip(bonds, self.native_bonds, strict=True)
            },
            items=bindings,
            baseline_items=deepcopy(bindings),
            baseline=baseline,
        )
        build_document_payload(state, CANVAS_FILE_VERSION)
        return state
