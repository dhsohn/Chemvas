# Frozen native document v7 fixtures

These small, synthetic documents capture the supported native v7 contract on
2026-09-13. They contain no user documents, experimental results, or external
artwork. Their literal `version: 7` and serialized fields are independent of the
current writer constant and serializer defaults.

- `minimal.chemvas`: required scene collections and settings, two atoms and one
  bond, without optional document collections or newer optional item fields.
- `extended.chemvas`: explicitly colored bound/free marks, atom annotations,
  `double_either`, a mirrored equilibrium arrow with multiline labels, Unicode
  note text and HTML, a group, ring fill, shape, orbital, TS bracket, perspective
  coordinates with stored depth, and a Calculation Plan v2. The embedded raster
  is a generated 1 x 1 RGB PNG; its original encoded bytes are part of the fixture.

The JSON was captured once from synthetic document builders, checked with native
validation, graph inspection and a color-only Graph Patch, then stored as
static data. Tests read these files directly: they must not regenerate them from
the current writer or replace version 7 with the current writer constant. When
a new format is introduced, retain these fixtures and add new ones separately.

Frozen UTF-8 file SHA-256 values (including the final newline):

| File | SHA-256 |
| --- | --- |
| `minimal.chemvas` | `872e42a2d1d6635279e28c3efbc8540f68918c87026ae62a052d32aa98d7403e` |
| `extended.chemvas` | `24d8b3cc358f00f5ca9188e56f7a6b39dbc4c57cebb224cd67f98eb81f91bd7e` |

The headless checks compare the complete normalized state after reading and
writing, and after a declared color-only patch. Editable SVG tests wrap this
literal v7 payload in the frozen SVG-source v1 envelope, not a newly generated
native document. GUI round-trip tests separately exercise scene materialization.
These are compatibility sentinels, not an exhaustive schema enumeration or a
chemical-validity, font-rendering, or historical-reader compatibility guarantee.
