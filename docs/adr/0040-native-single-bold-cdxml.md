# ADR 0040: Native single bold CDXML bonds

- Status: Proposed
- Date: 2026-10-11

## Problem

The Bold toolbar creates `bold_in`/1 bonds. CDXML export rejects this style even
though the native bond vocabulary has Display=Bold and a BoldWidth property.
The document already emits a default BoldWidth, but Qt may fall back to the
normal stroke when that width does not exceed the line width.

## Decision

Extend the existing bond exporter for `bold_in` with exact integer order 1.
Emit one chemical bond with unchanged endpoints, positions and colour, explicit
Order=1, Display=Bold and the scaled effective Qt stroke width. Reuse the current
fragment, atom and export plan owners. Reject other bold variants and orders.
The Ar attachment vocabulary is unchanged.

Native editability and width are the mapping’s contract. Exact outline identity
is excluded: Qt builds a one-sided strip with label trimming and miter joins;
ChemDraw controls its own bold outline. Do not shift nodes or replace bonds with
detached graphics to compensate. This decision remains proposed for independent product acceptance; the bounded
native checks below do not approve deployment.

## Verification and limits

`tests/test_cdxml_export.py` checks connectivity, atom coordinates, colour,
scaled/default/custom/fallback widths, labelled reversed endpoints, source byte
preservation and atomic rejection of invalid live orders. Existing selected
CDXML graphics, label-binding CLI and dashed-object tests cover neighbouring
contracts. Each test file runs in its own process with an all-app coverage
denominator; this is not a full-suite or RDKit verification.

ChemDraw 25.0.2.14 opened, saved and reopened the default synthetic witness
in fresh processes. All 12 nodes remained within 0.005 pt and all six bonds
retained endpoints, order and display. Moving only the labelled N endpoint,
Undo, Redo, save and another fresh-process reopen preserved connectivity and
effective width while the other 11 nodes stayed fixed. A separate runtime
custom-width witness passed open/save/fresh-process reopen; its editing and
Undo/Redo were not separately exercised.

Default BoldWidth 4.75817199341 pt normalized to 4.76 pt when saved. The custom
BoldWidth 7.14874683616 pt and LineWidth 2.85949873446 pt normalized to 7.15 pt
and 2.86 pt. Native SVG measurement confirmed the default horizontal bold
width, but also a positional difference: the source strip centre lies
1.29768327 pt to one side of the atom axis; the native strip is centred on it.
Exact source-outline equivalence therefore failed. The custom witness had no
separate native SVG measurement. Consumer warnings and chemical interpretation
were not accepted by these drawing checks.

Double_outer, font substitution, tight-page clipping and generic aryl
reinterpretation are outside this change.

References: [Bond object](https://chemapps.stolaf.edu/iupac/cdx/sdk/Bond.htm),
[Bond Display](https://chemapps.stolaf.edu/iupac/cdx/sdk/properties/Bond_Display.htm).
