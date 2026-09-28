# ADR 0027: Record-based annotation transforms

- Status: Accepted
- Date: 2026-09-28
- Extends: [ADR 0008](0008-shared-annotation-rendering-and-records.md)

## Problem

Shapes, brackets and arrows already had document records, but rotation and
reflection rules edited dictionary fields in the UI. Arrow handedness and label
side rules lived alongside Qt bounds handling for notes and images.

## Decision

Qt-free annotation transforms accept and return the existing `Shape`, `TSBracket`
and `Arrow` records. They own axis-aligned rectangle orbiting, reflected bounds,
arrow control points, arc handedness and equilibrium label sides. The UI converts
its captured history state through the existing record codecs and delegates these
rules. History dictionaries and the saved file format are unchanged.

Note and image bounds remain in Qt, as do the existing mark and orbital paths.
No universal annotation registry or transform protocol is added.

## Verification and limits

Record tests cover rectangle dimensions and style preservation, curved arrow
control geometry, arc handedness and involutive equilibrium reflections. Existing
mixed-selection rotation, flip, history and save/reopen tests cover integration.
A deterministic comparison against the previous implementation checked 3,900
canonical transformations within a numerical tolerance of 1e-10. Incomplete
synthetic bracket states now fail the existing record validation; production
snapshots already contain complete records.
