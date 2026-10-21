# ADR 0030: CDXML export

- Status: Partly superseded by ADR 0058 and [ADR 0059](0059-cdxml-only-working-documents.md)
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
   known atomic number and an unambiguous meaning. Alias labels (including
   Ac and Ts, which collide with acetyl and tosyl abbreviations) other than
   the verified group labels of decision 17, multi-element abbreviations,
   raw `Ar` and identifier hydrogens without a typed binding, and any label
   not in the periodic table refuse with `CdxmlUnsupportedObjectError`.

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

13. **Z-order.** `Z` (CDX ZOrder, INT16) is written only on the objects the
    ZOrder property lists among those exported: every `n`, `b`, `t` and
    `graphic`, never on `group`, `fragment` or `page` (a missing `Z` is 0 and
    zeros are ordered arbitrarily). Values are unique positive integers from
    1; each page object takes one contiguous block, and inside a fragment the
    atoms and bonds follow their own scene paint order (a node, then its
    contracted group, then its label). An atom or bond whose items are split
    by another in z-order, or more than 32767 such elements, is refused
    before output. Page order uses `scene.items(AscendingOrder)` rank,
    which reflects actual scene stacking including z-value ties. Fragment
    layer interleaving (a non-fragment item whose scene rank falls between a
    fragment's lowest and highest item, overlapping spatially) and two
    overlapping fragments that interleave in z-order are both refused.
    Spatial overlap is bounding-rect intersection, except for a square TS
    bracket: its exact painted stroke rectangles (flat ends, mitre-filled
    corners, each free end lengthened by half the width for a consumer
    square cap) are tested against the fragment items' bounding rects, and
    touching counts. A bracket whose painted geometry cannot be fixed (not a
    right-angle M/L polyline, a transform other than uniform scale plus
    offset, or painted bounds that differ from those rectangles) and dagger
    brackets keep the bounding-rect test.

14. **Atom labels.** Label baseline and x-coordinate are read from the
    actual glyph origin: `item.sceneTransform()` applied to
    `layout.position() + line.x()` for x, and `layout.position() + line.y()
    + line.ascent()` for the baseline y. Missing owner, layout, or record
    refuses. Font family is the resolved `QFontInfo(atom_font()).family()`.
    Hydrogen counts are not emitted on element nodes; `InterpretChemically="yes"`
    on the root delegates inference to the consumer. This is documented as
    unproved. The internal carbons of a nickname (decision 17) carry explicit
    `NumHydrogens`.

15. **Empty page refusal.** Serialization refuses if the page would contain
    zero children (e.g. a bond-only selection with no atoms).

16. **No ChemDraw interoperability claim.** The dialog label reads
    "CDXML - ChemDraw XML (not verified in ChemDraw)". The vendor DTD has
    known lexical limitations (`AS` attribute type for `NMTOKEN` values).
    This export does not claim DTD validity.

17. **Typed atom label semantics (amended 2026-10-06).** A label's chemistry
    comes only from a typed source; text, colour, neighbours and legends are
    never used to guess it, and the drawn label (exact Unicode text, resolved
    font, size, colour, glyph-origin baseline) is written unchanged.
    - `Me`, `Ph` and `tBu` have exporter-owned fragment definitions whose
      carbon valences are checked at import. Each exports as
      `NodeType="Nickname"` holding an inner `<fragment>` with the group's
      carbons, explicit `NumHydrogens`, Kekulé bond orders for phenyl, and one
      `NodeType="ExternalConnectionPoint"` node on the outside neighbour's
      position. The outside bond keeps its native `B`/`E` order and ends on
      the nickname node. Only one ordinary single attachment is accepted
      (style `single`, order 1). Zero or several attachments, double, triple,
      wedge or hash attachments, and charge or radical annotations on the
      group refuse; the connection point is never guessed. `Atom_BondOrdering`
      is not emitted because it only matters with more than one attachment,
      which is refused.
    - Raw `Ar` refuses as ambiguous. Identifier hydrogens (`H` followed by
      superscript lowercase letters) refuse unless typed; digits and signs
      are never accepted, so an identifier is never read as an isotope or
      charge.
    - `CdxmlLabelBinding` is an exporter-level, keyword-only input
      (`label_bindings={atom_id: binding}`) for `preflight_cdxml` and
      `serialize_cdxml`: `element_identity(symbol)` (exact symbol, or `H`
      with an identifier label, emitting `Element="1"` without `Isotope`),
      `generic_aryl()` (`NodeType="GenericNickname"`,
      `GenericNickname="Ar"`, no inner graph), and `aryl_fragment("Ph")`
      (phenyl nickname graph under the `Ar` label). Each meaning takes
      exactly its own field as an exact `str`; an extra or conflicting field,
      a missing or non-`str` value, or an unknown meaning is refused, never
      dropped or converted. Bindings cannot override
      the alias registry, must name an atom in the document, and are not a
      document schema field: they are neither stored in nor read from
      `.chemvas`. No GUI or CLI caller passes them yet.
    - Generic groups are documented as a class statement, not a concrete
      molecular graph. This decision does not change marks, dashed or other
      refused lines, brackets, plots, note scripts or rotation, groups or
      images: they still refuse.

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
| Atoms     | Pure elements, colour, explicit C, Charge annotation; `Me`/`Ph`/`tBu` as Nickname with inner graph; typed `Ar` (argon, generic aryl, phenyl) and identifier hydrogens through `CdxmlLabelBinding` |
| Bonds     | single/1, double_center/2, side-placed double/2 (Left/Right from drawn lines), triple/3 (including order 2/3 with single style), wedge/1 (WedgeBegin), hash/1 (WedgedHashBegin) narrow at begin atom |
| Lines     | Headless solid lines; dashed lines as `LineType="Dashed"` (consumer dash pattern); endpoint-order BoundingBox |
| Arrows    | Arrow as grouped line components (M/L only, no Head3D)|
| TS brackets | `square_pair`/`square_left` as grouped Line graphics on the `bracket_path_commands` M/L vertices; `dagger`/`double_dagger` as one `<t>` with the exact glyph at the `bracket_symbol_layout` anchor |
| Shapes    | rect, circle; stroke-only, fill-only, or same colour; bond_color emitted for stroke-only |
| Notes     | Per-line `<t>` with per-run resolved family, size, bold, color |
| Other     | Unpainted ring records ignored                        |

### Refused

| Area      | Refused                                                |
|-----------|--------------------------------------------------------|
| Atoms     | Other aliases (incl. Ac/Ts), untyped raw `Ar` and identifier hydrogens, group labels without exactly one plain single attachment or with charge/radical, radicals, any scene mark; hidden atoms are excluded and bonds to them are refused |
| Bonds     | Bold, dotted, double_outer, double_either; unverified side line or stereo narrow orientation; mismatched style/order |
| Lines     | Wavy, bold lines; mirrored lines                       |
| TS brackets | Parentheses, braces (cubic strokes); transformed, translucent or outlined items; items not painting their record; dagger glyph fallback |
| Arrows    | Curved, double, other kinds, labels, mirrored; non-M/L path commands |
| Shapes    | Ellipse, rounded_rect, dashed/dotted stroke, translucent fill, mixed colours |
| Notes     | Italic, underline (all styles), overline, strikeout, scripts, non-mixed-case capitalization, custom word spacing, non-default font stretch, lists, tables, rotation (m12/m21 != 0), non-400/700 weights, non-left alignment, boxes/borders, glyph fallback fonts |
| Stacking  | Fragment layer interleaving (notes, lines, dashed lines, arrows, shapes, TS brackets; square brackets by painted strokes), overlapping interleaved fragments |
| Other     | Visible ring fills, images, orbitals, perspective, groups, empty pages |

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
- **`LineType="Dashed"`**: the CDX `Line_Type` property has values Solid,
  Dashed, Bold and Wavy and no dash length or gap, so the consumer chooses
  the dash pattern. The exported line is dashed; its pattern is unproved.
- **Square bracket corners**: the Line graphics carry the exact M/L
  vertices and width; joins and end caps are drawn by the consumer, while
  the scene uses flat caps and mitre joins.
- **U+2028 soft breaks**: may appear inside `<s>` text; consumer behaviour
  is unproved.
- **Tab characters**: may appear inside `<s>` text; the tab advance width
  is consumer-dependent and unproved.
- **Round caps and joins**: CDXML defaults may differ from the scene
  rendering; consumer interpretation is unproved.
- **Nickname / GenericNickname / ExternalConnectionPoint**: written from the
  public CDX specification mirror (Node, Node_Type, Atom_GenericNickname,
  Atom_NumHydrogens); internal coordinates, label display, expansion and
  reconnection in ChemDraw or other consumers are unverified. No consumer or
  roundtrip PASS is claimed.
- **Behaviour change**: a raw `Ar` label that exported as `Element="18"`
  before this amendment now refuses until a caller supplies a typed binding.
- **No DOCTYPE**: the output has no DOCTYPE declaration; DTD validity is
  not claimed.
