"""Shared rejection of entity declarations and internal DOCTYPE subsets."""

from __future__ import annotations

import pytest

from chemvas.domain.document.cdxml_source import (
    parse_native_xml,
    reject_unsafe_cdxml_declarations,
)
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.export import inspect_cdxml_roundtrip
from chemvas.features.export.cdxml_consumer_validation import parse_consumer_xml

EXTERNAL_DOCTYPE = (
    b'<?xml version="1.0"?>'
    b'<!DOCTYPE CDXML SYSTEM "http://www.cambridgesoft.com/xml/cdxml.dtd">'
    b'<CDXML><page id="1"/></CDXML>'
)
INTERNAL_ATTLIST = (
    b'<!DOCTYPE CDXML [<!ATTLIST n Element CDATA "7">]><CDXML><page id="1"/></CDXML>'
)
INTERNAL_AFTER_QUOTED_GT = (
    b'<!DOCTYPE CDXML SYSTEM "a>b" [<!ATTLIST n Element CDATA "7">]>'
    b'<CDXML><page id="1"/></CDXML>'
)


def test_parse_consumer_xml_rejects_internal_attlist_subset() -> None:
    with pytest.raises(ValueError, match="entities"):
        parse_consumer_xml(INTERNAL_ATTLIST)


def test_review_cdxml_service_rejects_internal_attlist_subset() -> None:
    with pytest.raises(ValueError, match="entities"):
        inspect_cdxml_roundtrip(INTERNAL_ATTLIST)


@pytest.mark.parametrize(
    ("name", "parse", "match"),
    [
        (
            "consumer",
            lambda raw: parse_consumer_xml(raw),
            r"must not declare entities",
        ),
        (
            "native",
            lambda raw: parse_native_xml(raw.decode("utf-8")),
            r"entity declarations and internal DTDs are not supported\.",
        ),
        (
            "document",
            lambda raw: parse_cdxml_document(raw),
            r"entity declarations and internal DTDs are not supported$",
        ),
    ],
)
def test_all_entry_points_reject_internal_subset_after_quoted_gt(
    name: str, parse, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        parse(INTERNAL_AFTER_QUOTED_GT)


@pytest.mark.parametrize(
    "entry",
    [
        ("consumer", lambda raw: parse_consumer_xml(raw)),
        ("native", lambda raw: parse_native_xml(raw.decode("utf-8"))),
        ("document", lambda raw: parse_cdxml_document(raw)),
    ],
)
def test_external_doctype_still_parses_at_all_entry_points(entry) -> None:
    _name, parse = entry
    root_or_doc = parse(EXTERNAL_DOCTYPE)
    root = getattr(root_or_doc, "state", root_or_doc)
    if hasattr(root, "tag"):
        assert root.tag == "CDXML"
    else:
        assert isinstance(root, dict)


def test_guard_accepts_large_external_doctype_and_stops_at_root() -> None:
    """External DOCTYPE is allowed; body after the root start is not scanned."""
    pages = "".join(f'<page id="{index}"/>' for index in range(2_000))
    large = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE CDXML SYSTEM "http://www.cambridgesoft.com/xml/cdxml.dtd">'
        f"<CDXML>{pages}</CDXML>"
    )
    reject_unsafe_cdxml_declarations(large)

    malformed_after_root = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE CDXML SYSTEM "http://www.cambridgesoft.com/xml/cdxml.dtd">'
        "<CDXML><<<<not-xml"
    )
    reject_unsafe_cdxml_declarations(malformed_after_root)
