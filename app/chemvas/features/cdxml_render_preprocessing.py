"""Render preprocessing for standard single-fragment external CDXML."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.features.cdxml_standard_depiction import depict_standard_cdxml

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET


def maybe_preprocess_external_cdxml(text: str, root: ET.Element) -> str:
    page = root.find("page")
    if page is None or len(page) != 1 or page[0].tag != "fragment":
        return text
    fragment = page[0]
    if any(child.tag not in {"n", "b"} for child in fragment):
        return text
    nodes = fragment.findall("n")
    if not nodes or any(node.find("fragment") is not None for node in nodes):
        return text
    if any(node.get("p") is not None for node in nodes):
        if not all(node.get("p") is not None for node in nodes):
            return text
        if not any(
            node.get("Element") == "8" and node.find("t") is None for node in nodes
        ):
            return text
    depicted, _ = depict_standard_cdxml(text)
    return depicted
