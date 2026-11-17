# ADR 0072: Outlined black native CDXML rectangles

- Status: Accepted
- Date: 2026-11-17
- Extends: [ADR 0069](0069-plain-filled-native-cdxml-shapes.md)

## Problem

Fill-only native rectangles and circle-filled ovals import as editable shapes
([ADR 0069](0069-plain-filled-native-cdxml-shapes.md)). Black
`RectangleType="Plain"` rectangles with a positive outline still rasterized, so
moving or resizing one changed a bitmap projection instead of an editable shape.
Chemvas shapes stroke with the fixed bond colour and have no stroke colour or
width of their own, so an outlined rectangle can only map to a shape while its
native outline is black and unchanged.

## Decision

`features.cdxml_editable_shapes.editable_outlined_rectangle` imports a
`RectangleType="Plain"` graphic as a bound shape record with
`stroke_style: solid` and no fill when it has no child elements, a solid line,
no `CornerRadius`, a colour that resolves to black (absolute index 0, or the
default index 3 when that slot is black), an inherited or explicit `LineWidth` in
`(0, 100]` and either no axes or axes matching its axis-aligned bounding box.
Fill-only import runs first, and linked fallback targets never reach either
importer, so they keep the raster path that already moves their fallback
graphics.

`update_outlined_rectangle` writes move and resize through `transform_native`,
which updates `BoundingBox` and any axes and leaves `Z`, `color`, `LineWidth`
and other attributes as they were. Deletion uses the existing writer path. Any
fill, a stroke-style change or a shape-kind change raises before the
destination is replaced, because writing them would turn the black outline into
a fill-only or differently drawn graphic. `update_shape` and the ADR 0069
fill-only contract are unchanged.

## Verification and limits

`tests/test_cdxml_editable_rectangles.py` covers import, palette indexes 0/1
and default 3, styled, rotated and child-bearing rectangles staying raster,
move/resize/delete write-back with axes and `Z`, the chemistry paint band, the
linked-fallback raster path, refusal of fills and stroke or kind changes through
the real CDXML save with the file left unchanged, and the unchanged fill-only
contract. `tests/test_cdxml_plain_filled_vector_shapes.py` and
`tests/test_cdxml_bold_graphics.py` remain the regression gates for fill-only
shapes and raster strokes; the latter measures the raster Plain stroke on a red
rectangle because black Plain rectangles no longer rasterize.

The canvas draws these outlines at `shape_stroke_width` of the document bond
line width, not at the native `LineWidth`, so a thin or heavy native outline
looks the same weight in Chemvas while the saved file keeps its width. Imported
outlined rectangles cannot be filled, recoloured or restyled; rotated, rounded,
dashed, shadowed, bold and coloured rectangles stay raster.
