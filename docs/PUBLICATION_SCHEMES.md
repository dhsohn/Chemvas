# Repeatable publication figures

This recipe makes two **synthetic drawing examples**, not a reaction mechanism or
research result. It uses public Chemvas commands and retains native editable
documents alongside every export. It contains no private manuscript or calculation
data and does not need RDKit.

From a source checkout, use the Python environment where Chemvas is installed:

```bash
python examples/publication_scheme.py --output-dir /absolute/existing-parent/new-figures
```

The output directory must not exist. Requests, intermediate drawings, measured
layout/font reports, SVG, 600 dpi PNG and `manifest.json` are retained for review.
Failed runs leave their new directory for diagnosis; choose a new directory to
retry. No old drawing or output is overwritten. A CLI error or layout warning
stops this example before further publication; it does not auto-correct chemistry.
The final native SHA-256 is pinned before its layout check. The check, export-box
probe and both final export reports must reference those same bytes. Each
manifest figure includes `layout_check`, containing the saved report filename
and its SHA-256. A source mismatch stops the recipe without a final manifest;
any intermediate files remain diagnostic material, not an accepted delivery.

## What to reuse

1. **Native templates first.** `insert-template` creates a regular benzene and
   records native ring membership, which is needed for inner double-bond strokes.
   Use explicit bonds and atom IDs for substituents. The example bends O–Me with
   `set_terminal_angle`; it never distorts the ring to move a terminal group.
2. **One scale for the figure set.** Keep ordinary bond geometry, renderer metric,
   font family and body/script sizes common. Set each export width from its
   measured padded canvas width multiplied by one `mm_per_unit` value.
   A longer drawing therefore stays longer, not smaller.
3. **Arrange captions once, then align drawings.** Ordinary `layout-document`
   makes native structure/caption groups. A second `mode: "align-y"` operation
   fixes only molecular Y positions. In the second example, one caption describes
   two explicitly independent molecular parts; its horizontal position and text
   stay fixed.
4. **Use real typography.** Notes have native `runs` with `vertical_align: "sub"`
   and `"super"`. `A_1` and `kcal mol^-1` are not substitutes for formatting.
   The example's A identifiers and superscript a are typography samples only.
   There is no overall figure title that duplicates the manuscript caption.
5. **Validate editable and printed size separately.** Require a clean
   `check-layout` result, including full native-sheet containment, before any
   export. Render with height and minimum-font guards, then inspect both the
   native drawing and final SVG/PNG. A clean diagnostic report is not a chemistry
   or stereochemistry validation.

The small example intentionally has no invented arrows, energies or TS geometry.
For a real pathway, add the researcher-supplied states and arrows explicitly,
including all intermediates and branches that belong in that figure. Preserve
complexes and TSs as rigid blocks unless their independent movement is explicitly
intended. Do not choose wedge/hash direction or coordination geometry from aesthetics.

## Example print profile, not a new default

### Connected abbreviations

Use a native atom abbreviation such as `OMe` when its internal O–Me bond should
not be drawn explicitly. The attachment is oxygen: the O glyph stays at the
bonded atom for horizontal, vertical and steeply angled bonds. For a left-facing
label the display can read `MeO`; for a right-facing label it can read `OMe`.
An exactly vertical attachment keeps the typed order while still anchoring O.
Moving the bond or reopening the drawing recomputes this presentation through
the same native label service used by canvas and figure export.

This is display layout, not a change to the stored label, atom coordinates or
chemical conversion aliases. The rule uses the existing attachment information
for reversible labels; it does not infer an attachment atom in an unknown or
unreversible string. Isolated labels and label-body collision guards retain
their existing layout. Check surrounding text after reflow because anchoring
the correct glyph shifts the rest of the abbreviation sideways.

### Shared physical scale

The recipe uses ordinary bond length 40 canvas units, a target of 5 mm per bond,
Arial, native body font 17 and script-run font 22. Qt reduces script runs as part
of native layout. These values produce approximately 8.1 pt body/atom text and
6.7 pt scripts in the tested environment; the export reports provide the actual
resolved sizes. Font availability and Qt's physical viewport rounding can vary.
The 6 pt minimum is a guard with margin, not an asserted journal rule.

`settings.bond_length_px` is also the current renderer's metric for pens and atom
fonts; `text_font_size` alone does not independently set atom text size. This
example separates its explicitly supplied 40-unit geometry from the renderer
metric `17 × 20 / 12`. It then measures the padded default ACS export (14.4 pt per
renderer metric) to derive canvas width before applying the common 5/40 mm scale.
It does **not** rewrite an SVG, scale individual notes, or install a parallel
style engine. If changing presets or font settings, remeasure and review the
whole figure set; do not copy the ACS conversion constant to another preset.

The native working sheet and physical export are different coordinate spaces.
Small PDF dimensions do not make an oversized saved drawing editable within its
sheet. Keep the native geometry, fonts and whole-figure placement within that
sheet from the start; do not ignore boundary warnings and rely on export scaling
to hide them. Before delivery, reopen the final native file and check that its
complete drawing is visible and its groups can be selected and moved as intended.
Do not save temporary review moves back into the delivery file.

For larger authored documents, `check-layout --sheet-only` can run the bounded
linear containment check without the pairwise collision pass. Its report is only
sheet-fit evidence, not a substitute for collision or visual review. The small
examples here use the default combined check once; they do not need a redundant
sheet-only call. Neither mode modifies Save/Open or automatically shrinks content.

The template-to-composition step is deliberately limited to the new, graph-only
seed created inside the example. It transfers both inspected graph data and the
generated native `ring_fills` through Composition v1. `inspect-document` alone is
not a full document serializer. Do not reuse that step as a converter for existing
drawings: notes, groups, plans, perspectives and other scene data require their
native document workflows.

## Insert into a manuscript without changing the scale

Use each figure's `embed_width_mm` from `manifest.json` and preserve aspect ratio.
Do not stretch all images to a common Word column width. PNG/SVG dimension
rounding is included in their font reports and can cause a small scale difference.
Keep captions in the manuscript, not as a repeated heading inside the graphic.

The sample `--max-height-mm 105` is an illustrative figure-only ceiling, not an
automatic “half a page” rule. Compute a height budget from the actual manuscript
page, margins and caption space. Chemvas does not inspect DOCX page layout or
format manuscript text; verify super/subscripts and final figure sizes again in
the exported manuscript PDF.

If the drawing cannot fit at the chosen readable scale, shorten/reorganize the
panel or explicitly choose a new row structure. `max_row_width` requests wrapping;
omit it to keep the specified single row. Width/height/font guards never decide
to wrap, reduce fonts or shrink structures for you.

See [CLI contracts](AGENT_CLI.md) and [alignment contracts](SCHEME_LAYOUT.md) for
source hashes, explicit part membership, supported operations and resource limits.

## Two complete comparison rows

For a narrow-column comparison, a second runnable example keeps both alternatives
complete instead of making the reader reconstruct a shared reactant or product:

```bash
python examples/publication_comparison.py --output-dir /absolute/existing-parent/new-comparison
```

This is a **symbolic connectivity example only**. R₁–R₄ denote abstract fragments,
not specified compounds. Each input and output contains all four fragment labels
once; the two product pairings are authored explicitly, not predicted by Chemvas.
The native arrow labels “case 1”/“case 2” and “symbolic only” demonstrate above/below
condition placement without inventing reagents, conditions, yields or selectivity.
Replace them only with information appropriate to the actual figure.

The example uses the existing recipe's public command helpers. It saves the
composition, source-pinned layout request, native source and final document,
`comparison-graph.json`, collision report, SVG/600 dpi PNG and `manifest.json`.
The output directory must be new; any command error or collision warning stops
the run. The original template example and its print profile remain unchanged.
The same source-pinned `layout_check` receipt and export checks apply to this
comparison's manifest.

Ownership is explicit in the layout request:

- Each side is a rigid block containing four atom IDs and its plus-sign note.
  Its separate Input/Output caption belongs to that block, not the arrow.
- Both complete rows use `column_group: "comparison"`, with one existing
  horizontal arrow per row. No row, component, caption or branch is inferred.
- `caption_alignment: "structure"` centers each caption under its own block.
  Use `"row"` instead when a shared caption baseline is the intended design.
- `arrow_color: "#000000"` explicitly applies black to the listed row arrows.
  It is not a global recoloring operation on structures, notes or other arrows.
- `max_row_width` is omitted: each specified path remains one horizontal row.

The comparison uses 20-unit bonds at **5 mm per bond**, Arial, native body font 10
and note-script font 13. This one profile is shared by both rows, every structure,
caption and condition label. It produces approximately 9.2 pt body text, 7.1 pt
atom subscripts and 7.8 pt caption subscripts in the tested environment. The
smaller native coordinates also keep the arranged example on the native A4
working sheet; physical size comes from the common 5/20 mm-per-unit conversion,
not from filling the sheet or scaling individual structures. Actual font reports
remain authoritative when fonts or Qt versions differ.

The resulting figure is about 79 × 42 mm. Its **85 × 100 mm** bounds are maxima,
not a command to stretch a short figure to that size. Use `embed_width_mm` and
preserve aspect ratio when inserting it into a manuscript. A width failure asks
for an explicit reorganization; a height or font failure stops the native export.
None of these guards shrinks a molecule, font or arrow to force a fit.

Choose parallel complete rows when the comparison itself is the message, especially
when conditions or products differ. A symmetric branch is a different authored
scheme: use it only when a shared origin and the intended arrow connectivity are
actually appropriate. Do not turn a comparison into branching just to save width,
and do not imply a chemical relationship from spatial symmetry. If meaningful
content is too wide at readable scale, split panels or explicitly reorganize rows.

`check-layout` covers only its reported collision and sheet-boundary classes. It
does not establish caption ownership, chemical meaning, visual balance, or final
publication quality. Review the complete native figure and exported image at the
intended insertion size as well as at zoom: a clean collision report alone is not
approval of the design. The example's regression tests check graph preservation,
explicit grouping, native scripts and physical dimensions separately.
