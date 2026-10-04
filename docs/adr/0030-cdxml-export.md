# ADR 0030: CDXML export

- Status: Accepted
- Date: 2026-10-03
- Depends on: ADR 0005 (responsibility-based editor boundaries)

## Context

Chemvas documents contain molecular structures and annotations that users may
need to edit in ChemDraw or exchange with tools that consume the CDXML format.
Project 1 evidence shows that native editable CDXML with graphics and text is
feasible using filled rectangles, circles, lines and styled text runs. No
prior converter source exists; only output evidence at 170 mm page width.

## Decision

1. **Export only.** CDXML import remains refused. The existing `.chemvas`
   format is the document truth; CDXML is an export representation.

2. **One owner module.** `app/chemvas/ui/export/export_cdxml.py` reads the
   `SceneRenderContext` model and scene items, receives the shared
   `ExportPlan`, and serializes CDXML bytes. No new domain wrapper package.

3. **Uniform scale.** One scale `s = out_w_pt / source_w` applies to all
   coordinates, font sizes, line widths, bold widths, hash spacings, arrow
   geometry, and bond lengths. Origin is the plan source (x, y). The page
   width is `out_w_pt` in points, matching the 170 mm fractional-point
   contract from the evidence. Numeric precision uses 12 significant digits
   (`.12g` format) where coordinates, page widths, fonts, and line attributes
   are emitted.

4. **Native fragment/node/bond for pure elements.** Atom labels map to
   `<n Element=Z>` only when the label is a recognized element symbol with a
   known atomic number. Alias labels (including Ac and Ts, which collide
   with acetyl and tosyl abbreviations), multi-element abbreviations, and
   any label not in the periodic table refuse with
   `CdxmlUnsupportedObjectError`.

5. **Bond style/order consistency.** Supported bonds include single/1,
   double_center/2 (`DoublePosition="Center"`), side-placed double/2
   (`DoublePosition` resolved as `Left` or `Right` from drawn scene lines,
   including benzene and ring double bonds; consumer visual interpretation
   is unverified and parsers such as RDKit ignore it), triple/3, and stereo
   wedge/hash bonds (order 1, `Display="WedgeBegin"` or
   `Display="WedgedHashBegin"`) whose narrow end starts at atom B (`bond.a`).
   Legacy order-2 and order-3 bonds stored with generic style "single" are
   supported. Double bonds with style `double_outer` or `double_either`, bold,
   dotted, and bonds whose drawn lines cannot confirm side or narrow begin
   orientation refuse explicitly. Unpainted ring records (transparent fill,
   no stroke) are ignored; visible ring fills refuse.

6. **Formal charge: native atom annotation only.** The `Charge` attribute
   maps directly from `atom_annotation["formal_charge"]`. Scene marks
   (including `plus`/`minus` charge marks) have no proved CDXML mapping and
   are explicitly refused. The annotation value is emitted as a native atom
   attribute; it does not depend on the mark being visible.

7. **Graphics: evidenced constructs only.**
   - Line (NoHead, Solid): headless straight lines, endpoint-order
     BoundingBox.
   - Filled Rectangle, Plain Rectangle: rect shapes with/without fill.
   - Circle Filled, Circle (Oval): circle shapes via Center/MajorAxis/
     MinorAxis with axis-end-first BoundingBox.
   - Arrow as grouped line components (shaft + head lines). Line
     components carry BoundingBox only (no Head3D/Tail3D). Only M and L
     path commands are supported; any other command refuses. The
     `mirrored` property on arrows is explicitly refused.
   - Shape stroke width uses the source `shape_stroke_width(style.
     bond_line_width)`, not the renderer-scaled metric.
   - Stroke-only shapes and uncoloured arrows emit `style.bond_color`
     when it is non-black.

8. **Text: per-run preservation.** Walk QTextDocument blocks and layout
   lines. Each laid-out line becomes a `<t>` with per-fragment `<s>` runs
   carrying family, scaled size, bold face bit, and color. Font family
   uses the actual resolved font (`QFontInfo(font).family()`), not the
   requested family. Font size uses `QRawFont` pixel size scaled once.
   Glyph fallback is detected via `QTextLayout.glyphRuns()` and refused
   when any run's raw font family differs from the primary resolved family.
   Italic, underline (all styles including dash), overline, strikeout,
   sub/superscript, non-mixed-case capitalization (uppercase, small caps),
   custom word spacing, non-default font stretch, backgrounds, lists,
   tables, bitmap fonts, and non-400/700 weights refuse. Non-left
   alignment (detected via `blockFormat().hasProperty(BlockAlignment)` then
   document `defaultTextOption` alignment) refuses. Note boxes (both
   fill-enabled and border-only) refuse. No whitespace is injected inside
   `<t>`/`<s>` text content by indentation.

9. **Preflight before write.** `preflight_cdxml` checks every visible item
   before any file I/O. `CdxmlUnsupportedObjectError` names the object kind,
   id, and reason, and suggests SVG/PDF as alternatives. The atomic write path
   preserves destination bytes on failure. Hidden items (including hidden atom
   items) in the export set are excluded. Bond items whose endpoints are not
   both in the exported atom set are refused.

10. **Transform checks.** Both note and atom label items are checked for
    rotation: `m12 approx 0`, `m21 approx 0`, and `m11 approx m22 > 0`.
    This catches pure rotations, `setTransform`-applied rotations, and
    factory items with no record. The check does not depend on any note
    record's rotation field.

11. **Color table indices.** Reference index = table position + 2 (implicit
    indices 0 and 1). White and black are always the first two entries.

12. **Groups.** Group emission is not yet implemented. `FigureExportService`
    accepts a typed `groups` provider. The GUI passes
    `runtime_state.group_state.groups`; the CLI restores from
    `state["groups"]` using the existing `restored_groups` helper and the
    single-owner `GROUP_COLLECTION_STATES` dict. Groups overlapping with
    exported atoms via `atom_ids` refuse. Groups with `item_ids` that
    intersect the exported items' `data(3)` record ids refuse; groups
    whose items are entirely outside the export scope are ignored.

13. **Z-order.** Every page child carries a `Z` attribute with monotonically
    increasing integers. Sort order uses `scene.items(AscendingOrder)` rank,
    which reflects actual scene stacking including z-value ties. Fragment
    layer interleaving (a non-fragment item whose scene rank falls between a
    fragment's lowest and highest item, overlapping spatially) and two
    overlapping fragments that interleave in z-order are both refused.

14. **Atom labels.** Label baseline and x-coordinate are read from the
    actual glyph origin: `item.sceneTransform()` applied to
    `layout.position() + line.x()` for x, and `layout.position() + line.y()
    + line.ascent()` for the baseline y. Missing owner, layout, or record
    refuses. Font family is the resolved `QFontInfo(atom_font()).family()`.
    Hydrogen counts are not emitted; `InterpretChemically="yes"` on the root
    delegates inference to the consumer. This is documented as unproved.

15. **Empty page refusal.** Serialization refuses if the page would contain
    zero children (e.g. a bond-only selection with no atoms).

16. **No ChemDraw interoperability claim.** The dialog label reads
    "CDXML - ChemDraw XML (not verified in ChemDraw)". The vendor DTD has
    known lexical limitations (`AS` attribute type for `NMTOKEN` values).
    This export does not claim DTD validity.

## Scope and consequences

CDXML appears in `EXPORT_FORMATS`, `_SUFFIX`, `_FILTER`, and
`_FORMAT_SUFFIXES` in the dialog module. The CLI `render-document` accepts
`.cdxml` output. `FigureExportService.export_figure` branches for the `cdxml`
format key and runs preflight before the atomic write. `validate_export_budget`
is called before serialization for `max_height_mm` validation.

Existing SVG, PDF, PNG, and TIFF export contracts are unchanged. CDXML does
not support `--min-font-pt` (no font measurement contract for XML output).

Perspective rendering refuses rather than silently omitting depth. The root
element carries `FractionalWidths="yes"`.

### Supported

| Area      | Emitted                                               |
|-----------|-------------------------------------------------------|
| Atoms     | Pure elements, colour, explicit C, Charge annotation  |
| Bonds     | single/1, double_center/2, side-placed double/2 (Left/Right from drawn lines), triple/3 (including order 2/3 with single style), wedge/1 (WedgeBegin), hash/1 (WedgedHashBegin) narrow at begin atom |
| Lines     | Headless solid lines, endpoint-order BoundingBox      |
| Arrows    | Arrow as grouped line components (M/L only, no Head3D)|
| Shapes    | rect, circle; stroke-only, fill-only, or same colour; bond_color emitted for stroke-only |
| Notes     | Per-line `<t>` with per-run resolved family, size, bold, color |
| Other     | Unpainted ring records ignored                        |

### Refused

| Area      | Refused                                                |
|-----------|--------------------------------------------------------|
| Atoms     | Aliases (incl. Ac/Ts), radicals, any scene mark; hidden atoms are excluded and bonds to them are refused |
| Bonds     | Bold, dotted, double_outer, double_either; unverified side line or stereo narrow orientation; mismatched style/order |
| Lines     | Dashed, wavy, bold lines; mirrored lines               |
| Arrows    | Curved, double, other kinds, labels, mirrored; non-M/L path commands |
| Shapes    | Ellipse, rounded_rect, dashed/dotted stroke, translucent fill, mixed colours |
| Notes     | Italic, underline (all styles), overline, strikeout, scripts, non-mixed-case capitalization, custom word spacing, non-default font stretch, lists, tables, rotation (m12/m21 != 0), non-400/700 weights, non-left alignment, boxes/borders, glyph fallback fonts |
| Stacking  | Fragment layer interleaving, overlapping interleaved fragments |
| Other     | Visible ring fills, brackets, images, orbitals, perspective, groups, empty pages |

### Unproved / consumer-dependent

- **`DoublePosition` consumer rendering**: `DoublePosition="Left"|"Right"`
  follows drawn scene lines, but actual visual display in ChemDraw or other
  consumers is unverified, and chemical parsers like RDKit ignore it.
- **Hydrogen counts**: not emitted; consumer infers from element and bond
  count. This is documented as unproved; there is no evidence tying the
  consumer inference to the Chemvas model for all cases.
- **`CaptionLineHeight="1"`**: emitted on node labels; consumer behaviour
  is unproved.
- **`charset="utf-8"`**: emitted on font table entries; consumer behaviour
  with non-ASCII text is unproved.
- **`InterpretChemically="no"` on node labels under a root `"yes"`**:
  consumer behaviour is unproved.
- **U+2028 soft breaks**: may appear inside `<s>` text; consumer behaviour
  is unproved.
- **Tab characters**: may appear inside `<s>` text; the tab advance width
  is consumer-dependent and unproved.
- **Round caps and joins**: CDXML defaults may differ from the scene
  rendering; consumer interpretation is unproved.
- **No DOCTYPE**: the output has no DOCTYPE declaration; DTD validity is
  not claimed.
