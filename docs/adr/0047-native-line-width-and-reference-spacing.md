# ADR 0047: Native line width and effective bond-spacing validation

Status: Accepted for the candidate; full consumer-reference approval remains blocked.

ChemDraw 25.0.2.14 reads legacy Line graphics using the document LineWidth even
when each graphic specifies another width. The native save creates an arrow
and a SupersededBy fallback graphic; a fresh process reading that file retains
the wrong width. This changes plot lines and square TS brackets.

Emit each nonchemical straight segment as a native unheaded arrow with explicit
Tail3D, Head3D, LineType, FillType=None and LineWidth. Reaction-arrow heads remain
the same grouped straight segments. Documentary-contact metadata stays on its
nonchemical line. Chemical bonds remain b elements. Every arrow carries its own
Z. All documents use this serializer and the existing common renderer; there is
no document-version switch, alternate renderer or source-document rewrite.

The paired native probe compares solid/dashed legacy and native line forms at
two widths. Full OMe output then verifies 308 lines after SaveAs and a separate
process reopening the result. The 278 plot segments retain 0.66 pt instead of
the document 0.71 pt; the 30 bracket segments retain 0.90 pt instead of 0.71 pt.
These are native decimal-coordinate approximations of 0.65950185788 pt and
0.896510338055 pt. SVG path quantization remains measurable: maximum width error
is 0.02705 pt and 0.00349 pt respectively. This is not exact raster equivalence.

The reference validator checks active arrows, effective width and color,
directed endpoints, owner and inventory. A native fallback is accepted only
when its SupersededBy target exists, is unique, has the same owner/style/color
and agrees with its endpoint and width fields. It can connect adjacent saves
using the prior active arrow ID. It does not guess a correspondence from nearby
geometry or skip arbitrary graphic differences. Unknown arrow paint fields and
new heads, arcs, extra arrows, broken aliases or changed ownership are refused.
Source-to-second-save IDs cannot be inferred without the intermediate file;
direct full-reference validation therefore remains fail closed.

BondSpacing is a percentage, not a point coordinate. Compare effective
inherited/local percentages without applying the point-coordinate tolerance.
Check both directions for new or removed BondSpacing/BondSpacingAbs overrides.
Native percentage truncation on all 51 OMe doubles is now a surfaced refusal,
not a visual regression introduced by this change. Absolute spacing retains
the existing 0.02 pt coordinate tolerance.

Whole OMe Chemvas SVG/PNG and all exported n/b/t/fragment subtrees are unchanged
from the preceding candidate. Font identity, size quantization, label anchoring,
charge-mark interpretation/color, second-save color drift and two filled-shape
outline differences are still unresolved. This decision neither weakens those
checks nor claims full reference or GUI acceptance.
