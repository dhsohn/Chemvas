# Document compatibility

[한국어](DOCUMENT_COMPATIBILITY.ko.md)

## Product promise

Future Chemvas updates must continue to open currently supported, valid **v7
`.chemvas` documents**, keeping their stored drawing and document information
editable. Users must not need an old installation just to recover a supported
drawing. This is a supported file contract, not a temporary migration window.

The baseline is the v7 contract supported on 2026-09-13, including
optional mark colors, mirrored equilibrium arrows, crossed `double_either` bonds,
images, groups, perspective coordinates, and Calculation Plan v2. Existing v7
files without optional fields remain supported too. Some older Chemvas releases
used the same version number before those additions and cannot read all of them;
this promise does not retroactively change those installed readers.

Opening a document does not rewrite its source file. Explicit saving may use the
current output format and normalize its representation, but must preserve the
supported stored information. Keeping the original or using Save As is useful
when sharing with an older installation.

## Format changes

- The application release number and document format number are independent.
  The current writer still emits **v7**; this policy introduces no new schema.
- A serialized change that an existing reader cannot correctly interpret needs
  a new document format version. This includes new fields rejected by the
  existing strict schema, new enum values, and changes to a field's meaning.
  Do not add another incompatible feature under the v7 label.
- A future writer version must not remove v7 from the readable versions. Version
  interpretation belongs at the document boundary, not in every GUI or CLI
  consumer. Implement any necessary conversion there when an actual new format
  is introduced; do not add speculative migrations or capability negotiation.
- Before a format change ships, verify opening supported old fixtures and
  preserving their information through editing, saving and reopening. Audit
  outputs that currently retain their input version, including Graph Patch:
  never label newly introduced information as v7 or silently discard it to fit.
- Unknown versions, unknown fields, malformed documents and invalid references
  remain errors. Do not guess their meaning, silently omit unsupported content,
  or bypass validation to make a file appear to open successfully.

## Scope and limits

This promise covers native document reading, including a v7 document embedded in
an editable Chemvas SVG. Clipboard payloads, CLI requests/reports, SVG wrapper
metadata and calculation handoff artifacts have their own versioned contracts;
a native document change does not automatically change those versions.

It does not add support for pre-v7 documents, guarantee that old applications can
open newly saved formats, or promise byte-identical JSON or pixel-identical text
across fonts and platforms. Opening a saved calculation plan preserves its data;
it does not guarantee that a future chemistry backend will reproduce its results
or that an incomplete or stale plan is ready to execute. Scientific validation
remains separate from document readability. Correctness and security fixes may
still reject malformed inputs that an earlier implementation accidentally accepted.

## Regression baseline

[`tests/fixtures/document-v7`](../tests/fixtures/document-v7) contains fixed,
synthetic examples, not user research data. The files keep a literal version `7`
and must not be regenerated from the current writer when the format evolves.
They are representative witnesses, not an exhaustive specification of every
valid v7 document; the domain validation tests remain necessary.

[`test_document_compatibility.py`](../tests/test_document_compatibility.py) checks
native I/O, editable SVG and CLI preservation.
[`test_document_edit_roundtrip.py`](../tests/test_document_edit_roundtrip.py)
checks the desktop editing and save/reopen path. Both run under `make check`.
Tests for unsupported history pin versions 1–6 rather than treating every version
below the current writer as unsupported. Updating the writer constant alone must
not invalidate the v7 reading baseline.
