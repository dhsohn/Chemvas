# ADR 0051: Measured native CDXML palette recovery

- Status: Proposed for the review candidate; not released
- Date: 2026-10-12

## Context

The original eight-bit producer colors initially render correctly in ChemDraw
25.0.2.14. Its CDXML writer emits four decimal places; its next import loses one
channel unit for 125 of 256 grayscale values. Native CDX retains the values.
Input offsets cannot avoid the writer's rounding. Stable alternative colors
would change 12 of the regression document's 16 colors, by up to two units per
channel, and therefore cannot silently replace authored RGB.

Changing the font-table charset or family spelling does not recover an absent
physical font. In 24 native controls, Apple SD Gothic Neo, its PostScript-style
bold name and Arial all render as Arial for four charset forms. Regular and
bold retain their correct style weights. These are measured controls, not a
general cross-platform font equivalence claim.

## Decision

Expose `inspect_cdxml_roundtrip` and `recover_native_cdxml_palette` through
`features.export`. A Qt-free `review-cdxml` command owns bounded file reads,
JSON output and atomic creation of a new CDXML through `core.document_io`.
The feature owns XML validation, color analysis and restoration. Existing
consumer fidelity validation remains unchanged.

Inspection shows modeled palette stability and logical font/style changes.
Nearest stable colors are reported, never applied. Matching family names do
not establish identical physical faces. Every report retains
`full_fidelity_accepted: false`.

Recovery requires an exact eight-bit producer and its known first native
SaveAs with the measured writer identifier. It verifies matching object and
text inventories, ownership and per-object/per-character logical RGB, reusing
the existing strict arrow-alias checks. Native colors must exist in the source
palette and differ from exact RGB only within four-decimal rounding. Only
color-table component spellings are replaced; other bytes are preserved.
Reindexing is accepted only when the corresponding painted colors still match.
Real recoloring, unknown writer profiles, prior channel loss and occupied output
paths are refused. The writer string is not a provenance signature; the caller
must retain the original and first native save.

## Verification and limits

`tests/test_cdxml_roundtrip_workflow.py` contains 256 actual native grayscale
observations and 24 font-encoding observations in
`tests/fixtures/native_cdxml_roundtrip.json`, plus palette-reindexing,
real-change rejection, non-palette byte preservation, Qt-free CLI and
no-overwrite checks. The fixture stores native hashes and physical EMF font
records; BMP identity and real reopens are additionally checked in the review
evidence. Existing CDXML, application CLI, renderer CLI, architecture and
dependency tests run in separate processes.

Recovery does not change fonts, original documents, chemistry, common rendering
or tolerance thresholds, and does not accept a full consumer reference. The
91 text-object font substitutions in the full native document remain visible.
The measured native writer reintroduces its rounding on every later save, so
the workflow must retain the original and recover each known save before the
next import, or use native CDX for the evidenced color-preserving roundtrip.
This command is a bounded palette workflow, not arbitrary document repair,
an automatic desktop import/export hook or a GUI validation result.

## References

- [Prior color scope and native limitations](0050-literal-text-colors-and-native-default-scope.md)
- [Product workflow](../CDXML_EXPORT.md#review-a-native-save-and-recover-its-palette)
- [CDXML font definitions](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/Font.htm)
- [CDXML color table](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/ColorTable.htm)
