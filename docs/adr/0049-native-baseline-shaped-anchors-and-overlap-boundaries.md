# ADR 0049: Native baseline, shaped anchors and overlap boundaries

Status: Accepted for this review candidate. Whole-document consumer-reference
and GUI acceptance remain blocked.

## Common atom-label placement

Position the label's painted normal baseline at `(em - descent) / 2` below the
atom, using the actual Qt face's em and descent. Preserve the painter baseline
and move the whole item. Apply the same rule to plain labels, typographic runs
and the element line of stacked hydrides. Existing and newly created documents,
live canvas and headless output use this shared placement. Keep the physical
anchor rectangle for bond trimming; its vertical box center is not the atom's
placement reference. Tests measure painted outlines instead of assuming the
old text-document box center.

The independent reference consists of 96 ChemDraw 25.0.2.14 labels: six font
families, eight sizes from 6 to 24 pt, normal and bold. Windows GDI metrics
predict the native baseline within the 0.005 pt CDXML coordinate rounding.
The fixture retains input/output hashes. This is evidence for a metric rule,
not an empirical family-specific correction or a claim that different operating
systems have identical font files or hinting.

## Shaping and native character advances

Measure the facing character's cell in its complete shaped run. Standalone
character widths fail for kerned Ta, Te, Tc and Ts. Explicit kerning-enabled
regressions read actual glyph positions independently of the cursor-cell helper.

The native chemical-label engine uses character advances without the Qt default
pair kerning. Use `QFont.setKerning(False)` in the common atom-font provider;
free-text captions keep their own font settings. In fourteen native left/right
Me, Ar, Cl, tBu, Ta, Te and Tc controls, this reduces maximum horizontal-origin
error from 1.777198 pt to 0.011574 pt. The new baseline rule reduces the earlier
eight-control 1.31624 pt vertical error to at most 0.004597 pt. The final candidate
was saved and reopened independently of the temporary experimental override.
These are origin/baseline measurements, not proofs of identical glyph ink.
Ts is covered in live/headless/save/shaping tests but the existing CDXML binding
refusal remains; no native Ts acceptance is claimed.

## Overlap at a rounding boundary

Preserve line/fill relative Z order when positive-area overlap exists in either
the producer or consumer scene. A permitted 0.01 pt line/fill displacement or
stroke-width change can create or remove overlap. Testing only the producer
misses consumer-only occlusion. The same bounded separating-axis geometry and
identity checks apply; numeric Z renumbering is allowed, reversal and ties are
refused. Regressions cover both one-sided cases and unchanged order for all three
geometry changes. This is still limited to straight flat-capped strokes and
opaque axis-aligned filled rectangles, not a general occlusion proof.

## Font and color boundaries

Preserve requested fonts and authored colors. Require actual face/style identity,
coverage of the document's required glyphs and reproducible fallback choices
before claiming portable typography; family-name equality alone is insufficient.
The source captions request Apple SD Gothic Neo, which Windows substitutes.
Mac glyph runs, Windows face-file hashes and coverage of 170 required characters
are recorded separately. Among the probed candidates, an identical installed
face with complete coverage was not established. Windows WPF face probing does
not identify ChemDraw's actual per-glyph fallback. No font is installed, bundled,
or silently substituted, and the reference font guard remains strict.

Native SaveAs strips explicit attached-mark colors, and its four-decimal palette
serialization can lose an 8-bit color channel on the next read. Setting color
on the text, object tag, or both did not preserve the eight attached mark colors
in the bounded native probe. Do not change authored colors, redefine implicit
mark color, quantize the common renderer or relax the color guard to conceal
these differences. They remain consumer-reference blockers with raw evidence.

The earlier chemistry, movement/rotation/rollback, bond-width and spacing guards
remain. Verification uses selected whole test files in separate processes and
bounded native automation. It does not authorize installation, deployment,
merging, source-document edits or a GUI-success claim.
