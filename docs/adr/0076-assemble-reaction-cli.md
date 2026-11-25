# ADR 0076: Assemble one-step reaction CDXML

- Status: Accepted
- Date: 2026-11-25

## Problem

Headless workflows need a deterministic way to turn a normalized one-step native
reaction CDXML—fragments and role references already present, but without global
layout—into a readable reaction row Chemvas and ChemDraw can open. Manual layout
in the desktop editor is unsuitable for scripted assembly, and `layout-document`
expects an already arranged canvas state rather than role-only inputs.

## Decision

Add an explicit Qt-free owner at `chemvas.features.reaction_assembly` that:

- validates one scheme step, local fragment coordinates, and absent page or arrow
  geometry on input,
- resolves arrow role references through legacy `graphic` aliases when
  `SupersededBy` names the real arrow,
- lays out reactants, optional counterions, plus notes, a single arrow, products,
  and stacked arrow conditions on one horizontal row using conservative text and
  fragment extents,
- preserves native IDs, styled text, and the chemical graph while writing global
  positions and page bounds, and
- rejects unsupported decorations, multiple steps, and inputs that are not already
  normalized.

Expose the work as `chemvas assemble-reaction INPUT --output OUT.cdxml`. The
bootstrap wrapper reports JSON on success and fails closed otherwise.

When a two-fragment reactant side contains one isolated ion and an oppositely
charged partner, the ion is placed above the substrate. Separators can be
standalone page notes. Local molecule bounds include atom-label extents.

## Verification and limits

`tests/test_assemble_reaction_cli.py` covers argparse help, the public CLI,
shuffled page order, counterion placement, multi-step rejection, input bounds
rejection, preservation of native IDs, reopening through `parse_cdxml_document`,
and `render-document` on assembled output. Run `bash scripts/check.sh tests/test_assemble_reaction_cli.py`.

Only one reaction step and one arrow are supported. Layout uses conservative
measurements rather than a full caption engine. The command does not invent plus
notes or alter chemistry beyond translation.