# ADR 0026: Endpoint selection draft

- Status: Accepted
- Date: 2026-09-28

## Problem

Reaction Mapping already owned correspondence outside its widgets, but endpoint
component inclusion and roles were read from combo boxes. Endpoint construction,
cross-side locking, charge display and canvas mapping snapshots depended on those
widget values and their signal sequence.

## Decision

`EndpointSelectionDraft` owns component inclusion and roles for both endpoints.
It computes effective members, roles, cross-side locking and modeled charge
without Qt. The dialog updates this draft on input and renders its values with
widget signals blocked. Loading and resetting explicitly update the draft before
rendering. Mapping snapshots and endpoint construction read the draft.

Inactive choices remain available when a side unlocks. Context-only membership,
catalyst/spectator roles and explicit cleared correspondence keep their existing
meaning. State IDs and multiplicity remain dialog fields; the saved calculation
plan format is unchanged.

## Verification and limits

Draft tests cover locking, context and catalysts, retained inactive choices and
modeled charge. Dialog tests verify that a widget-only change with blocked
signals cannot change the canvas mapping snapshot. Existing mapping, highlight,
calculation panel and handoff tests cover integration. No generic view-model
framework or alternate document format is introduced.
