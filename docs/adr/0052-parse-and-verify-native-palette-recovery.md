# ADR 0052: Parse and verify native palette recovery

- Status: Proposed for the review candidate; not released
- Date: 2026-10-12
- Extends: [ADR 0051](0051-measured-native-cdxml-palette-recovery.md)

## Counterexamples

The X candidate accepted an edited red component `0.14505` because rounding to
eight-bit RGB still yielded 37 and its broad rounding window allowed the value.
The measured native importer renders this value as 36. Recovery silently changed
an intentional color edit back to 37. A paired paint guard alone was insufficient.

X also located the palette with a whole-document regular expression. A valid
XML comment immediately inside the real color table could contain fake color
rows and a closing table tag. Recovery then edited only that comment and reported
success while leaving the actual palette at its lossy native values.

## Decision

Accept a native palette component only when its Decimal value exactly equals
the measured writer's four-place serialization of the corresponding original
eight-bit component. No tolerance window or approximate inference is allowed.
Keep object/text paint matching and exact original producer RGB requirements.

Use the XML parser's start-element byte positions to locate actual direct color
children of the root palette. Comments and CDATA are not elements. Lex attributes
only within these parser-selected tags; preserve quoted data and every byte
outside the actual RGB component values. Reparse the output and require its
real palette to contain the exact intended canonical RGB values before returning
a report or allowing the CLI to publish a new file.

Explicit `--recover-palette NEW_CDXML` is required to write anything. Atomic
creation still refuses existing regular files, hard links and symbolic links.
Source/native inputs and partial-output guarantees remain unchanged.

## Provenance boundary

Exact numeric agreement proves a palette matches a measured writer profile; it
does not prove the application wrote the bytes or that this was the first save.
An intentional edit with identical resulting bytes cannot be distinguished from
writer output. The caller must know the first-save provenance and intent. The
CLI help, API docstring and product documentation state this explicitly.
Reports retain `provenance_runtime_verified: false` and
`full_fidelity_accepted: false`. No automatic application during desktop save or
import is added. If provenance is unknown, leave the document unchanged.

## Verification

`tests/test_cdxml_palette_writer_contract.py` reproduces both counterexamples
through the public API and CLI, verifies real parsed output colors and untouched
comments, refuses nearby edited values, and checks output aliases. Its fixture
contains a real minimal native first-save pair and 256 observed native grayscale
serializations. Actual ChemDraw reopens confirm the edited value paints red 36,
the recovered/comment control paints the intended color, and the full/matrix
recovery remains correct. Existing strict consumer checks and all common
renderer/font/geometry/movement/rollback code are unchanged.

The native writer still loses precision on later CDXML saves. Unavailable
physical fonts, 91 font substitutions, other full-document fidelity limits and
GUI interaction acceptance remain unresolved. The fix closes two product write
boundary defects, not the external writer or font environment.
