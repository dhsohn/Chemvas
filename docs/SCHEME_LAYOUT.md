# Structure and caption layout

[한국어](SCHEME_LAYOUT.ko.md)

`layout-document` arranges existing structures and caption notes into explicit
rows. It measures native painted text, centers captions beneath each structure,
aligns the first text baseline at each caption level, and uses common column
widths for rows with the same block count. An optional atom anchor aligns a
reaction center instead of the structure's bounding-box middle.

For drawings that are already spaced correctly, the CLI also supports
`"mode": "align-y"`: align molecular paint vertically without moving captions
or changing horizontal placement. This mode is explicit, never the default.

Arrange preserves the top-left of the requested source region (structures,
assigned items/captions and connecting arrows) rather than moving it to (0,0).
A wrap width measures the resulting region's width, not its absolute X coordinate.
Unassigned content stays exact; this is not automatic page fitting. Run the sheet
containment check after arranging. In `align-y`, arrow positions also stay fixed.
A multi-reactant block has one shared caption stack; use separate blocks for
separate captions or attached notes to preserve individual offsets. Roles are
explicit and are not inferred or persisted as a new caption schema.

## Arrange from the desktop

![Arrange Scheme walkthrough: group each structure with its caption, open the dialog, choose captions and the arrow, click Arrange](images/walkthrough-arrange.gif)

1. Select each complete structure together with its caption notes and use
   **Edit ▸ Group**. Include disconnected fragments and TS brackets in the same
   group when they belong to that state.
2. Open **Edit ▸ Arrange Scheme…**. Each existing group is one block. Set its
   row and order within that row; row **0** leaves that group untouched.
3. Use **Choose…** to assign each named note as a **Structure caption** or an
   **Attached note** that keeps its offset. No captions are guessed from position.
   The caption field lists 1-based note numbers; reorder them to choose caption
   levels. Hover for the note text and group atom IDs. Reaction conditions belong
   in the arrow's existing Above/Below fields; panel explanations should stay
   outside structure groups.
4. Choose each connecting **Arrow after** explicitly, or choose none for a
   gallery without arrows. The last block of a logical row must have no outgoing
   arrow. Existing arrows must satisfy the same horizontal-arrow rules as the CLI.
5. Set gaps and optional **Wrap width**, in canvas units, then click **Arrange**.
   A wrap width of **0** means no wrapping. The complete edit can be undone with
   **Ctrl+Z** and redone normally; existing group membership stays intact.

Use **Alignment group** to name related comparison rows. The same name shares
their column widths; different names keep unrelated comparisons independent.
One name per row is sufficient; conflicting names in one row are rejected.
Blank retains the original block-count alignment. Choose **Close to each
structure** to keep captions below their own block rather than at shared row
baselines. An optional **Connecting-arrow color**, for example `#000000`, applies
only to the chosen arrows and their attached labels. Blank preserves their colors.
Arrow line width and label fonts remain the document's common settings.

The dialog does not infer a mechanism or decide which note describes a structure.
Unassigned arrows and other objects remain where they were. Unsupported or stale
input and impossible width budgets leave the drawing unchanged; cancelling makes
no edit. The desktop uses the same measured layout plan as the command below.
Its first version uses existing groups and their geometric centers; use the CLI
for explicit atom anchors or for creating groups as part of layout.

In **File ▸ Export Figure…**, choose **Custom width (mm)** or a size preset, and
optionally enable **Limit exported height** and **Minimum exported font size**.
Font checking is available for whole-canvas SVG/PNG only, not selected-area
exports, PDF or TIFF. Custom-width and guarded exports have bounded vector and
raster dimensions. Rejected limits leave an existing destination file intact.
Height checks include the final format's dimension rounding (PNG/TIFF use the
requested DPI, excluding resolution-metadata quantization).

## Arrange from a script

```bash
chemvas inspect-document scheme.chemvas
chemvas layout-document scheme.chemvas --layout layout.json --output arranged.chemvas
chemvas check-layout arranged.chemvas
chemvas render-document arranged.chemvas --output arranged.svg --width-mm 174 --max-height-mm 120
```

Copy the exact source hash from inspection into the request. Atom references are
stable IDs; notes, arrows and other item references are zero-based indices in the
source document. This example requires the corresponding atoms and items:

```json
{
  "format": "chemvas-scheme-layout",
  "version": 1,
  "source_sha256": "<64 lowercase hexadecimal characters>",
  "gap": 12,
  "row_gap": 24,
  "caption_gap": 8,
  "line_gap": 4,
  "rows": [{
    "blocks": [
      {"atoms": [0, 1, 2], "captions": [0, 1], "anchor_atom": 0},
      {"atoms": [3, 4, 5], "captions": [2, 3], "anchor_atom": 3,
       "items": [["ts_brackets", 0]]}
    ],
    "arrows": [0]
  }]
}
```

This request applied to two structures with two captions each, a TS bracket
on the second and one arrow; before and after:

![Before layout: the second structure sits higher, its captions further down and the bracket loosely around it](images/cli-layout-arrange-before.png)

![After layout: both blocks share a row, captions are centred below each structure at common baselines, the bracket moved with its block](images/cli-layout-arrange-after.png)

Each block must include whole connected structures. Explicitly include separated
reactants or products that belong to the same state. `captions` lists existing
notes from top to bottom, for example identifier then energy. `items` adds notes,
TS brackets or shapes that move rigidly with the structure. Both are optional.
Include separate TS symbols such as a double dagger as well as their brackets.
`anchor_atom` must belong to its block. Optional `arrows` must have one entry per
adjacent pair of blocks. These must already be horizontal, left-to-right `arrow`
or `equilibrium` items. Their lengths and label text are preserved; colors also
stay unchanged unless explicitly overridden as described below.

## Explicit comparison rows

The existing row planner supports three optional choices in arrange mode:

- `rows[].column_group`: an identifier of 1–64 printable, non-whitespace characters. Rows
  with the same identifier must have the same block count and share column and
  arrow-slot widths. Different names keep comparisons independent. Omitted
  groups retain the original block-count sharing, separate from named groups.
  Width-limited wrapping still uses independent display lines.
- `caption_alignment`: `"row"` (default) aligns caption baselines across a row;
  `"structure"` places each caption stack below its own painted block, including
  explicitly attached items such as TS brackets. It does not ignore those items
  or move text through them to reach a molecular bounding box.
- `arrow_color`: a hexadecimal color such as `"#000000"`, applied only to the
  explicitly listed `rows[].arrows` and their labels. Unlisted arrows, molecular
  colors, captions, fonts, line widths and arrow kinds stay unchanged. Omit it
  to preserve deliberate color distinctions. Use separate requests for groups
  that intentionally use different colors.

These choices do not infer branching, duplicate reactants or decide chemical
equivalence. Choose the rows before arranging. For a narrow figure, two complete
reaction rows can communicate a comparison more clearly than a squeezed branch;
this is an authoring decision, not an automatic template conversion.

The GUI and CLI use the same validation and measured plan. Role choices are
one-shot layout instructions, not a new persistent document schema: after
reopening, choose roles again or rerun an explicit request with the current
source hash. The native groups and arrow labels themselves remain persistent.

## Align only the molecular drawings

Use the same command with this request when a product drawing floats above its
neighbours but the captions and horizontal spacing are already correct:

```json
{
  "format": "chemvas-scheme-layout",
  "version": 1,
  "mode": "align-y",
  "source_sha256": "<64 lowercase hexadecimal characters>",
  "rows": [{
    "reference_blocks": [0],
    "blocks": [
      {"atoms": [0, 1, 2], "captions": [0]},
      {"atoms": [3, 4, 5, 6], "captions": [1],
       "parts": [[3, 4, 5], [6]]}
    ]
  }]
}
```

The same request on a product that floats above the reactant, with a separate
chloride ion as its own part; captions and every X coordinate stay where they
were:

![Before align-y: the product chain and the Cl⁻ sit well above the reactant](images/cli-layout-align-y-before.png)

![After align-y: both parts moved down to the reactant's molecular midline, captions untouched](images/cli-layout-align-y-after.png)

`reference_blocks` contains zero-based block indices in that row. The target is
the vertical midpoint of the **union of those blocks' original molecular painted
bounds**, not the average of their atom positions and not a designated P atom.
Omit it to use all blocks in the row. Captions, free text, brackets and shapes do
not influence that molecular measurement; atom glyphs and attached molecular
marks do. All targets are measured before anything moves.

By default a block is one rigid unit, including disconnected reactants in a
complex. `parts` explicitly declares independent vertical movement units. It
must partition all block atoms exactly once, without cutting any bond—including
a dotted TS contact. A part can itself contain several connected components
that must stay rigid. Do not split a TS or a complex merely because its model has
disconnected components.

Every atom and scene item's X coordinate, all note content/positions, and all
existing native groups are retained exactly. Listed captions are validated but
not repositioned; notes in `items` stay fixed as well. Explicitly listed TS
brackets/symbols and shapes can follow a whole rigid block; they are excluded
from the molecular center. Combining movable decorations with multiple `parts`
is ambiguous and rejected. Arrows stay fixed. Existing group boundaries must
still be respected; unlike ordinary arrangement this mode does not create groups.

`anchor_atom`, `gap`, `row_gap`, `caption_gap`, `line_gap`, `max_row_width`,
`column_group`, `caption_alignment`, and `arrow_color`
are rejected in `align-y`, even when set to an old default. It neither lays out
columns nor wraps rows. `parts` and `reference_blocks` are rejected in ordinary
arrange requests. Omit `mode` to retain the existing arrangement path and report.
The align-only report adds `mode`, `part_count`, reference/target evidence per
row, and each part's molecular bounds before/after with `dx: 0` and its `dy`.

The desktop Arrange Scheme dialog remains a full arrangement interface. The new
align-only contract is currently available through the CLI; do not substitute the
desktop's caption-rearranging action when captions must remain fixed.

## Wrapping a long pathway

Add optional `"max_row_width": 900` at the request root to wrap each specified
row into lines no wider than 900 canvas units. The value must be positive,
finite and at most 100,000. Omit it to retain explicit rows and shared column
widths. This is a layout budget, not an output width in millimetres.

![Before wrapping: four states and three arrows in one long row](images/cli-layout-wrap-before.png)

![After wrapping with max_row_width 320: two lines, the continuation arrow at the start of the second line](images/cli-layout-wrap-after.png)

Wrapping follows the listed block order. Each complete structure/caption block
stays together, including any explicitly grouped fragments and TS symbols. A
connecting arrow that crosses a line break moves to the beginning of the next
line, immediately before its target block. Read left to right, then continue on
the next line; the leading arrow denotes continuation of the preceding line.
The command does not draw a connector across the page, duplicate intermediates,
infer branching or join separate input rows.

Widths include painted captions and arrow labels. Lines use compact, left-aligned
placement rather than expanding to shared columns. If one block, or a leading
arrow with its target block, cannot fit, layout fails without publishing output;
it never shrinks structures or produces a line containing only an arrow.
At most 128 display lines are supported. The wrapped report identifies the
source row/block positions and each continuation arrow for inspection.

The budget describes painted layout bounds, not the complete export's text-box
padding or outer margin. Unlisted objects still stay in place and can also
enlarge the complete export.
After arranging, choose the physical export width and inspect the result at that
size. A separate font-size guard can reject unreadably small text:

```bash
chemvas render-document arranged.chemvas --output arranged.svg --width-mm 174 --min-font-pt 6
```

Here 6 pt is an example threshold, not a universal journal requirement.
The threshold includes small subscript and superscript glyphs; use the
requirements of the intended figure and publication.

Distances are canvas units. Defaults are gap 40, row gap 30, caption gap 10 and
line gap 4. Gap is minimum clear space between neighbouring cells, or between a
cell and a row arrow; a cell includes its widest caption. The other gaps separate
rows, structure paint from captions, and caption levels. All distances are at
most 10,000; gap must be positive and the others may be zero.

Caption bounds include visible note-box fills and border strokes as well as text.
Structure–caption and caption-line gaps therefore clear the painted boxes too;
hidden or fully transparent boxes do not add spacing.

Requests are limited to 1 MiB, 128 rows, 128 blocks, 4,096 atom references and
4,096 item references. Inputs retain the 96 MiB / 20,000 graphics-record bounds.
Existing output files and symlinks are refused; a new output is published
atomically without modifying the source. The JSON report records source,
request and output hashes, translations and arranged-region dimensions in
canvas units, excluding unlisted objects.

## Scope and retained limitations

- Geometry changes are translations only. An explicit arrow-color override is
  separate from geometry. Layout does not normalize bonds, rotate structures, infer
  stereochemistry, change text or resize fonts. Unlisted objects stay in place.
- Automatic numbered/bulleted lists are not caption levels: their markers are
  not part of the caption-glyph bounds. Omit their caption number in the dialog
  (or put them in `items` in a CLI block) to move them as ordinary group items.
  Their text and export rendering remain supported.
- In ordinary arrange mode blocks become native GUI groups: moving a group after reopening
  keeps its structure and captions together. Existing groups are replaced only
  as whole units. Caption anchors are applied once, not persisted as a new
  document schema; editing text later does not automatically reflow it. Re-run
  layout with a fresh source hash after such an edit.
- Rows wrap only when `max_row_width` is supplied. Documents with a Calculation
  Plan or stored 3D perspective are rejected without removing their data.
- A successful layout is not a collision or publication-readability certificate.
  Run `check-layout` and inspect the native output at the intended print size.
- Rendering with `--width-mm` scales the complete figure, not individual
  structures. `--max-height-mm` rejects an overly tall plan before painting and
  never shrinks it. Add `--min-font-pt` to check final text sizes; none of these
  options changes source fonts or promises collision-free layout.

See [document CLI](AGENT_CLI.md#headless-document-rendering) for export rounding,
resource limits and deterministic-render guarantees. The
[publication recipe](PUBLICATION_SCHEMES.md) demonstrates a common physical scale
and the distinction between caption arrangement and molecular-only alignment.
