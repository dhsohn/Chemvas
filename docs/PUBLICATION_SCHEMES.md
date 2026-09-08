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
5. **Validate the final size.** Run `check-layout`, render with height and minimum
   font guards, and inspect both the native drawing and the final SVG/PNG. A clean
   diagnostic report is not a chemistry or stereochemistry validation.

The small example intentionally has no invented arrows, energies or TS geometry.
For a real pathway, add the researcher-supplied states and arrows explicitly,
including all intermediates and branches that belong in that figure. Preserve
complexes and TSs as rigid blocks unless their independent movement is explicitly
intended. Do not choose wedge/hash direction or coordination geometry from aesthetics.

## Example print profile, not a new default

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
