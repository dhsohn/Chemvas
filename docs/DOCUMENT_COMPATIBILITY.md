# Document Compatibility

[한국어](DOCUMENT_COMPATIBILITY.ko.md)

## Core Guarantee

Future Chemvas updates will continue to open supported, valid **v7 `.chemvas` documents**, ensuring previously saved drawings and metadata remain fully editable without requiring an older application build.

- **Baseline**: The baseline is the v7 specification as of 2026-09-13 (supporting optional mark colors, equilibrium arrows, crossed `double_either` bonds, images, groups, and Calculation Plan v2).
- **Non-destructive Opening**: Opening a document never mutates the original file.
- **Saving**: Explicitly saving a document normalizes the data to the current format version while preserving all supported content.

## Format Evolution

- **Application Release vs. Format Version**: The application release version is decoupled from the document schema version. Chemvas writes **v8, schema 1** (supported in Chemvas 0.18.0+) while maintaining full read compatibility with v7.
- **Breaking Changes**: Any serialization change that older readers cannot parse requires a new document format generation.
- **Strict Validation**: Unknown format versions, unexpected fields, and corrupt files fail explicitly with clear diagnostics rather than silently discarding unparsed data.

## Format v8 Specification

To clearly distinguish additive updates from breaking schema changes, Format v8 includes explicit schema and version fields in the root JSON object:

```json
{
  "type": "chemvas",
  "version": 8,
  "schema": 1,
  "min_reader": "0.18.0",
  "state": {}
}
```

### Field Definitions

- **`version` (Generation)**: The major format generation. Readers supporting a generation must read all known revisions of that generation.
- **`schema` (Revision)**: The revision within a major generation. Increments for **additive** changes (e.g., new optional fields or attributes).
- **`min_reader`**: The minimum application release required to parse this specific revision in full.
- **`state`**: The core document state (atoms, bonds, arrows, notes, and canvas settings).

### Reader Validation Sequence

When loading a document, Chemvas validates fields in the following order:

1. **Format Version**: Checks if `version` is supported. Unsupported major versions produce an explicit error.
2. **Root Envelope**: Validates the required root keys (`type`, `version`, `schema`, `min_reader`, `state`).
3. **Schema Revision**: If `version` is recognized but `schema` exceeds what the current build understands, the app informs the user that the file was created with a newer release (citing `min_reader`).
4. **Document State**: Performs strict validation on all contained drawing elements.

## Scope & Calculation Data

- **Scope**: Covers native `.chemvas` files and `.chemvas` payloads embedded in editable SVGs.
- **Calculation Plans**: Calculation metadata stored in documents is preserved regardless of whether the optional RDKit backend is installed. Chemvas preserves existing plans and validates whether they remain consistent with the current drawing structure upon save or CLI inspection (`inspect-plan`).

## Test Fixtures

Fixed test fixtures are maintained in [`tests/fixtures/document-v7`](../tests/fixtures/document-v7) and [`tests/fixtures/document-v8`](../tests/fixtures/document-v8) to ensure long-term roundtrip compatibility across versions.
