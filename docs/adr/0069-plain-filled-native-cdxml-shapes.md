# ADR 0069: Plain filled native CDXML shapes

- Status: Accepted
- Date: 2026-11-13
- Extends: [ADR 0060](0060-editable-native-arrows-and-local-platform-gates.md)

## Problem

ChemDraw fill-only rectangles and circle-filled ovals with zero or omitted local
`LineWidth` draw without a visible border, including when the document root sets a
positive width. Rasterizing every such graphic also counts against the document
image limit.

## Decision

Import exact `RectangleType="Filled"` and `OvalType="Circle Filled"` graphics with
no child elements, no styled variants, validated circular axis geometry, and zero or
omitted local width as editable `Shape` records bound to native IDs. The importer
validates inherited width and uses the existing raster path for explicitly positive
local widths, linked fallback graphics and geometry outside the shape model.
The native writer supports moving, resizing and recoloring bound
graphics with opaque fills. A resized circle uses the shorter side of the resize
box as its diameter, matching the canvas. The writer refuses unsupported edits
before replacing the destination.

## Verification

`tests/test_cdxml_plain_filled_vector_shapes.py` covers import, ChemDraw-style
omitted width, reversed bounding boxes, save preservation, limits, and refusal
paths. macOS `make check` is the release gate.
