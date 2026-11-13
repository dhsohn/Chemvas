# Frozen native document v7 fixtures

These small, synthetic documents capture the supported native v7 contract on
2026-09-13. They contain no user documents, experimental results, or external
artwork. Their literal `version: 7` in the `.json` snapshots and their
serialized fields are independent of the current writer constant and serializer
defaults.

Each fixture pair provides a frozen v7 JSON snapshot (`*.json`, originally stored
under the retired `.chemvas` extension with identical bytes) and a corresponding
CDXML working-document wrapper (`*.cdxml`) whose embedded `ChemvasDocument`
comment carries the same `state` in the current CDXML snapshot envelope
(`version: 10`, `schema: 1`, `min_reader: "0.26.0"`):

- `minimal.json` / `minimal.cdxml`: required scene collections and settings, two
  atoms and one bond, without optional document collections or newer optional
  item fields.
- `extended.json` / `extended.cdxml`: explicitly colored bound/free marks, atom
  annotations, `double_either`, a mirrored equilibrium arrow with multiline
  labels, Unicode note text and HTML, a group, ring fill, shape, orbital, TS
  bracket, perspective coordinates with stored depth, and a Calculation Plan v2.
  The embedded raster is a generated 1 x 1 RGB PNG; its original encoded bytes
  are part of the fixture.
- `legacy-reviewed-precomplex.json` / `legacy-reviewed-precomplex.cdxml`: a
  Calculation Plan v2 whose step S01 stores reviewed `candidate_ensemble`
  precomplex data on both endpoints. Chemvas 0.15.0 wrote it with
  `generate-precomplex` and `select-precomplex` (using the fake RDKit adapter of
  the test suite) on 2026-09-17, before those commands were removed. Later
  releases must keep reading and preserving this data even though nothing creates
  or uses it.

The JSON was captured once from synthetic document builders, checked with native
validation, graph inspection and a color-only Graph Patch, then stored as
static data. Tests read these files directly: they must not regenerate them from
the current writer or replace version 7 with the current writer constant. When
a new format is introduced, retain these fixtures and add new ones separately.

Frozen v7 JSON snapshot UTF-8 file SHA-256 values (including the final newline):

| File | SHA-256 |
| --- | --- |
| `minimal.json` | `872e42a2d1d6635279e28c3efbc8540f68918c87026ae62a052d32aa98d7403e` |
| `extended.json` | `24d8b3cc358f00f5ca9188e56f7a6b39dbc4c57cebb224cd67f98eb81f91bd7e` |
| `legacy-reviewed-precomplex.json` | `3d14aeb67cdda436c23220ec960f5283fcb683dbb94319add177b076ca81bdf4` |

CDXML working-document wrapper UTF-8 file SHA-256 values (including the final
newline):

| File | SHA-256 |
| --- | --- |
| `minimal.cdxml` | `3600970bded9b40a42e4f787da629c630ecf74f691d8b0784e2881658980404c` |
| `extended.cdxml` | `ba9b22eb063379f90bf3e067ff725533e605c4166e99602c9686309ad0998dcc` |
| `legacy-reviewed-precomplex.cdxml` | `1758f7c148a15906c675968463f1e2ec304aac1812dba14dfeccc1361d0f2950` |

`tests/test_document_compatibility.py`, `tests/calculation_workflow_support.py`,
and `tests/test_document_fixture_lifetime.py` consume the frozen `.json`
snapshots directly (and wrap their v7 payloads into temporary CDXML metadata
fixtures for headless `inspect-document` and `apply-patch` checks).
`tests/test_document_edit_roundtrip.py` and `tests/test_document_inspection.py`
consume the `.cdxml` wrappers for GUI open/edit/save-as round trips and
isolated inspection checks.
These are compatibility sentinels, not an exhaustive schema enumeration or a
chemical-validity, font-rendering, or historical-reader compatibility guarantee.
