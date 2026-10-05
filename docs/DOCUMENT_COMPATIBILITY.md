# Document Compatibility

[한국어](DOCUMENT_COMPATIBILITY.ko.md)

## Core Guarantee

Future Chemvas updates will continue to open supported, valid **v7 `.chemvas` documents**, ensuring previously saved drawings and metadata remain fully editable without requiring an older application build.

- **Baseline**: The baseline is the v7 specification as of 2026-09-13 (supporting optional mark colors, equilibrium arrows, crossed `double_either` bonds, images, groups, and Calculation Plan v2).
- **Non-destructive Opening**: Opening a document never mutates the original file.
- **Saving**: Explicitly saving a document normalizes the data to the current format version while preserving all supported content.

The retired `last_smiles_input` field is insertion metadata, not drawing content.
Readers continue accepting its existing string or `null` values in v7/v8 files.
It has no runtime or Undo state; new saves normalize it to `null`. The field stays
in the current schema so existing readers can parse new files. Opening a legacy
file never rewrites its bytes.

## Format Evolution

- **Application Release vs. Format Version**: The application release version is decoupled from the document schema version. Chemvas writes **v9, schema 1** (Chemvas 0.23.0+) while maintaining full read compatibility with v7 and v8.
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
- **Calculation Plans**: A calculation plan already stored in a document is kept when it still matches the drawing. Save refuses when the current drawing would drop that plan. Chemvas does not create, map, or export plans, and it does not depend on a chemistry backend.

## Test Fixtures

Fixed test fixtures are maintained in [`tests/fixtures/document-v7`](../tests/fixtures/document-v7) and [`tests/fixtures/document-v8`](../tests/fixtures/document-v8) to ensure long-term roundtrip compatibility across versions.

## Format v9 paper settings

v9 retains the v8 envelope and drawing fields. It expands `settings.sheet_size`
to A0–A5, Letter, Legal, Tabloid and Custom. Custom requires the optional
`sheet_custom_size_mm: [width, height]` field (finite values, 10–2000 mm per side);
presets must omit it. Custom dimensions are actual width and height, independent
of `sheet_orientation`. A4 retains its exact 595 × 842 drawing-unit dimensions.
Older readers reject v9 explicitly rather than opening a large sheet as A4.
v7/v8 remain A4-only; opening them preserves their original bytes, and explicit
save upgrades to v9. The minimum release for v9 is 0.23.0.
