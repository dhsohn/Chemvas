# ADR 0041: Experimental consumer-measured CDXML caption placement

- Status: Proposed
- Date: 2026-10-11

## Problem

Consumer font substitution changes text ink bounds. The first reference contract
could accept changed font tables, molecular objects and export assumptions after
a caller recomputed the consumer digest. A positive edge clearance alone did not
provide a useful safe margin. Native saving also removes IDs from some labels
and changes drawing-page dimensions independently of coordinate scale.

## Decision

The opt-in contract is version 2; version 1 is refused. Bind the source,
uncorrected producer and label-binding bytes, complete export options, producer
and consumer frames, explicit expected font mapping and declared consumer
environment. Bootstrap owns bounded strict file reads. The Qt-free export
validator compares each text by object path and checks molecular topology,
semantics, geometry and specified drawing scales against the fresh producer.
The serializer supplies actual uncorrected bytes and source glyph bounds.

Only selected whole note groups translate. Preserve their original horizontal
ink gaps and require 1 mm on every side plus 0.02 pt rounding reserve after all
movements, inside both declared frames. Refuse insufficient room and unsupported collisions before writing;
never resize text or pages. Default caption placement remains unchanged. The
color table separately serializes full channel precision because six significant
digits caused native truncation of RGB (140,150,159) to (140,149,158).

## Verification and limits

Synthetic CLI tests exercise rehashed font-table changes, undefined font IDs,
justification, graph edits, ID-less atom labels, mismatched options/frames and
post-collision margin failure. A native ChemDraw 25.0.2.14 rotated-note witness
saved and reopened with 2.86 pt top clearance and RGB (140,150,159). It used an
explicit Apple SD Gothic Neo to Arial substitution and native 23.85 pt text
instead of source 23.870700373 pt. The producer remained 40 mm wide; the native
drawing page remained 540 pt wide. These are distinct facts, not font or page
preservation claims.

The environment metadata is a declaration, not runtime authentication. Font
substitution and 0.05 pt native size quantization are reported. Validation does
not establish every consumer-specific graphic extension or molecule/graphic
clearance. The old full OMe reference also changes 48 generic Ar nodes to argon;
it is unsuitable for this contract even though all 243 text strings survive.
Manual GUI editing and Unicode Undo/Redo remain unverified. Native save/reopen
is bounded geometry evidence, not whole-drawing fidelity approval. Bold and
double_outer policies remain unchanged.
