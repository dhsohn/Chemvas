# ADR 0050: Literal text colors and native default scope

Status: Accepted for this review candidate. Full consumer fidelity and actual
GUI acceptance remain blocked.

## Correction to the U color verdict

U reported eight attached-mark color differences by inheriting an omitted text
run color from the containing atom. Native SVG comparison disproves that visual
loss: U and V native SVGs are byte-identical, and all eight marks already paint
black in U. Object-tag text has its own default foreground. Its omitted run color
must not inherit the atom-label color. This corrects a validator false positive;
it is not a color-tolerance exception or a claim of a visible recoloring fix.

Resolve an object-tag text run's color from its explicit run attribute, its text
attribute, then the document foreground index 3. Keep existing object inheritance
outside this narrowly defined context. Native fixtures include default foreground,
absolute black/white, duplicate palette black and custom red. Check inferred RGB
against native SVG fill. Continue rejecting an explicit change to white or to the
colored owner's color.

When the color table itself is absent, the CDXML standard defines index 2 as white
and index 3 as black. Resolve these two defaults only when no table element exists.
An explicit empty/incomplete table must still reject its undefined indexes, and
an actual change from black to default white must still fail the public validator.
This closes the independently reproduced V false rejection for an omitted table
and omitted attached-run color beneath an explicitly black owner.

Serialize literal black/white note runs using absolute CDXML indexes 0/1. This
keeps an explicit authored value when ChemDraw elides its default foreground
index. Other RGB values retain the original palette representation. Live and
headless renderers, model colors, typography, geometry, source documents and
consumer guard tolerances are unchanged. The full regression document changes
only eight `s.color` values from 3 to 0; common SVG and PNG are byte-identical to U.

## Palette precision is a separate consumer limitation

In 1,024 native grayscale controls, the four input encodings `n/255` and diagnostic
offsets `(n + 0.25/0.5/0.75)/255` all initially paint the same intended n. Each
256-control group retains only 131 values after the native CDXML is read again;
the same native CDX roundtrip retains all 256. The original OMe palette retains
16/16 values on native CDX reopen but only 4/16 on native CDXML reopen.

Input epsilon compensation cannot fix this measured native writer/readback
behavior. Preserve exact authored RGB and the existing 17-digit producer
serialization. Do not quantize source colors or waive actual loss. Native CDX
save/reopen is an evidenced workflow alternative for colors; it does not establish
font or whole-document fidelity and does not add a product CDX exporter.

## Font preservation boundary

Retain the requested source font and style plus actual painted fallback segments.
Apple SD Gothic Neo and Helvetica are absent from the measured Windows font
inventory. The native consumer substitutes Arial, leaving 91 caption font
mismatches. CDXML's font table records logical font names; it does not carry the
font files. Under the current no-install constraint, exact editable-text font
preservation is unresolved. Do not substitute a new source font or outline text
to hide a loss of editable typography. A same-name font alone is still insufficient
evidence of identical faces or fallback.

## Evidence and verification

The native eight-case fixture compares the actual SVG fill with parsed CDXML
color. The unmodified U fails nine of the new 22 regression cases. The tests cover
literal colors, attachment/charge preservation, native default scope, and refusal
of actual recoloring. Final selected checks retain U's shaping/baseline/Z-order,
movement, rotation and rollback coverage. All native scripts operate on temporary
documents and record process receipts; these are not GUI interaction tests.

Specification references:

- [Color table and reserved absolute indexes](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/ColorTable.htm)
- [Foreground color and its default index](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/ForegroundColor.htm)
- [Object tags and their displayed text](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/ObjectTag.htm)
- [Logical font definitions](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/Font.htm)

The object-tag scope behavior and precision results above are empirical findings
from ChemDraw 25.0.2.14; the specifications alone are not treated as proof of them.
