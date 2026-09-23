# Repeatable publication figures

[한국어](PUBLICATION_SCHEMES.ko.md)

This guide demonstrates how to programmatically generate publication-quality chemical reaction figures with consistent physical sizing, professional typography, and fully editable `.chemvas` source files.

Run the example script from the repository root:

```bash
python examples/publication_scheme.py --output-dir /absolute/existing-parent/new-figures
```

The script generates two sample figures exported at a standardized scale (5 mm per standard bond):

![pair.png: two anisole drawings with subscript identifiers and a superscript footnote mark, captions arranged below](../examples/publication-pair.png)

![independent-parts.png: one caption describing two independently aligned molecular parts](../examples/publication-independent-parts.png)

The output directory contains the editable `.chemvas` documents, high-resolution exports (SVG, 600 DPI PNG), layout inspection reports, and a summary `manifest.json`.

## Best Practices for Publication Figures

1. **Use Standardized Templates**: Use `insert-template` to construct regular rings and aromatics with correct geometry and connectivity.
2. **Consistent Physical Sizing**: Maintain uniform bond lengths, font sizes, and stroke widths across all figures in a manuscript by applying a fixed scale (`mm_per_unit`).
3. **Structured Alignment**: Group structures with their captions and use `layout-document` for horizontal and vertical alignment. Use `mode: "align-y"` to align molecular centers along a shared baseline.
4. **Rich Typography**: Use structured `runs` with `vertical_align: "sub"` and `"super"` for chemical formulas and states (e.g., subscripts in formulas, transition state `‡` superscripts).
5. **Pre-Export Layout Validation**: Run `check-layout` to detect label collisions or sheet-boundary overflows before generating final raster or vector graphics.

## Connected Abbreviations & Labels

- **Reversible Abbreviations**: Abbreviations like `OMe` automatically adapt based on bond direction:
  - Bond from left: Displays as `OMe`.
  - Bond from right: Displays as `MeO` to ensure the bonding oxygen atom remains directly attached to the substituent bond.
- **Physical Scale**: Headless rendering uses a fixed 96 logical DPI to guarantee deterministic text and line dimensions across environments.

## Comparison Schemes

To generate a multi-row comparison scheme with aligned columns:

```bash
python examples/publication_comparison.py --output-dir /absolute/existing-parent/new-comparison
```

![comparison.png: two complete rows, each with an input, a labelled arrow and an output, sharing column widths](../examples/publication-comparison.png)

### Layout Principles for Comparisons

- **Independent Blocks**: Group each reactant or product with its corresponding labels and captions.
- **Shared Column Groups**: Specify `column_group: "comparison"` so related reaction steps share identical column widths across rows.
- **Structure-Relative Captions**: Use `caption_alignment: "structure"` to center captions under their respective molecular blocks rather than the entire row.

For detailed command options and JSON specifications, see the [Agent CLI guide](AGENT_CLI.md) and [Scheme Layout guide](SCHEME_LAYOUT.md).
