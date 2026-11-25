from __future__ import annotations

import xml.etree.ElementTree as ET

from chemvas.domain.document.cdxml_source import (
    MAX_CDXML_SOURCE_BYTES,
    parse_native_xml,
    reject_unsafe_cdxml_declarations,
)
from chemvas.features.reaction_assembly.layout import apply_layout, compute_placements
from chemvas.features.reaction_assembly.validate import validate_normalized_reaction

MAX_ASSEMBLE_REACTION_BYTES = MAX_CDXML_SOURCE_BYTES


def assemble_reaction_cdxml(raw: bytes) -> bytes:
    if len(raw) > MAX_ASSEMBLE_REACTION_BYTES:
        raise ValueError("reaction input exceeds the byte limit")
    text = raw.decode("utf-8")
    reject_unsafe_cdxml_declarations(text)
    root = parse_native_xml(text)
    reaction = validate_normalized_reaction(root)
    placements = compute_placements(reaction)
    apply_layout(reaction, placements)
    payload = bytes(
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )
    if len(payload) > MAX_ASSEMBLE_REACTION_BYTES:
        raise ValueError("assembled output exceeds the byte limit")
    return payload
