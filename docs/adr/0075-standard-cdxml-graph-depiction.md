# ADR 0075: Standard CDXML graph-only depiction

- Status: Accepted
- Date: 2026-11-25
- Partly supersedes: [ADR 0055](0055-retire-rdkit-chemistry-provider.md) (CLI depiction only)

## Problem

Standard single-page CDXML can carry a complete bond graph without atom
coordinates. Chemvas could not import or render those files because the
preserving importer requires every visible atom position. Partial geometry —
some atoms positioned and others not — is ambiguous and must not silently
guess coordinates.

Neutral phenolic hydroxyls may carry ``NumHydrogens="1"`` on an oxygen node
without an explicit ``OH`` text object. Headless render should display them as
literal ``OH`` labels without moving existing coordinates.

## Decision

1. **Render path.** ``chemvas render-document`` preprocesses eligible external
   CDXML before import: assigns 2D coordinates when every visible atom lacks
   ``p``, or adds neutral phenolic ``OH`` labels when coordinates are already
   complete. No separate prepass command is required.

2. **Partial geometry.** If any visible atom has ``p`` while another lacks it, the
   command exits with an error and writes nothing.

3. **Backend.** Graph-only depiction uses the declared runtime dependency on
   RDKit. RDKit loads only when depiction runs, not at module import time. The
   desktop app entry path does not call the depiction backend.

4. **Phenolic OH.** Neutral singly bonded phenolic oxygens receive
   ``NumHydrogens="1"`` and a literal ``OH`` label when no label is present,
   including when coordinates are preserved. The depiction label is added to the render copy.

5. **In scope.** The preprocessor preserves bond orders,
   charges, and existing explicit labels while assigning coordinates. It rejects
   wedge/hash, unsupported stereo, query, and ambiguous nodes on graph-only inputs instead of
   silently changing stereochemistry.

6. **Bounded preprocessing.** Only single-fragment external molecules rendered to SVG, PNG or PDF are
   preprocessed. Layout supports up to 1,000 atoms and 2,000 bonds. Native Chemvas snapshots, schemes, graphics, and other complex
   inputs keep the existing reader behavior unchanged.

## Verification

- ``tests/test_cdxml_standard_depiction.py`` uses in-test synthetic fixtures for
  graph-only depiction, phenolic ``OH``, dangling references, and
  ``render-document`` integration.
- Headless import tests confirm depiction modules load without Qt or RDKit at
  import time.
- Clean package installs include RDKit as a runtime dependency (package-smoke).