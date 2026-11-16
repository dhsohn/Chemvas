# Synthetic CDXML regression drawings

These drawings are hand-authored examples of CDXML behaviors observed in
ChemDraw 25. They contain generic geometry and short atom chains, with fresh
coordinates and object IDs. They are not excerpts of research documents.

| Fixture | Regression trigger |
| --- | --- |
| `cdxml-container-ranks.cdxml` | Group and fragment Z values share the drawable namespace. An atom label omits Z, and a superseded graphic shares its arrow's Z. A three-atom chain with a triple bond overlaps an opaque background. |
| `cdxml-zero-width-curves.cdxml` | A triangle and two nested diamonds use numeric closure/fill flags, explicit solid fill and zero outline width. |
| `cdxml-zero-width-rounded-rectangle.cdxml` | A rounded rectangle has zero local outline width, a nonzero document line width and a retained native corner radius. |
| `cdxml-interop-colors.cdxml` | Default and inherited palette colors differ from absolute black/white; text runs override their inherited color. |

The tests check import, editing snapshots and native XML after disk save.
Native checks remove the editing snapshot before reopening the XML. Raster
assertions check known filled interiors, transparent corners and the outline
boundary; the rounded contour also has an independent circular-arc expectation.
