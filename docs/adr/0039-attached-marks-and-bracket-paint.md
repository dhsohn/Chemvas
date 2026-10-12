# ADR 0039: Attached CDXML marks and bracket paint order

- Status: Proposed
- Date: 2026-10-07
- Extends: [ADR 0030](0030-cdxml-export.md)

## Decision

Reuse the existing note emitter for atom-attached plus/minus text in a node-child
objecttag with a relative baseline offset. Preserve source node Charge emission
and native document state. No new tool, schema, charge inference or independent
child paint-order guarantee is introduced. ChemDraw 25 movement, Undo/Redo and
save/reopen preserve the displayed attachment; consumer re-save may omit Charge.

Child marks refuse contact with fragment ink whose relative paint order is
unproved. Proven square-bracket strokes use painted glyph/stroke bounds and the
existing fragment page anchor: only contact that reverses source order refuses.
Note and fragment-pair contact use existing Qt painted bounds to exclude hit-box
margin false positives; their actual interleaved ink remains refused.

Note fonts are read from actual QTextDocument glyph runs rather than an
independently reshaped string. Simple one-glyph-per-character mixed fonts use
existing string runs with original baseline and face; ambiguous clusters,
surrogates and incompatible glyph positioning still refuse.

## Limits

Text font substitution can change consumer glyph extent. Full-scene overlap needs
consumer inspection. The double_outer geometry guard remains: native double-bond
probes shorten the opposite stroke and do not preserve source endpoints and caps.
Absolute vectors without proved editable endpoint binding are not a substitute.
