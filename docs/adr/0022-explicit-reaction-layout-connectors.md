# ADR 0022: Explicit reaction layout connectors

- Status: Accepted
- Date: 2026-09-28

## Problem

[Issue #306](https://github.com/dhsohn/Chemvas/issues/306) describes a reaction
with two independently captioned reactants and one product. Arrow-only gaps
required two arrows; combining reactants in one block centered their captions
under the combined block. A plus note could not own a molecule block.

## Decision

Extend the version 1 layout request with row `connectors`, ordered existing
`[kind, index]` references to arrows or notes whose visible text is `+`. Keep
`arrows` as the supported arrow-only request syntax, but reject both fields in
one row. Normalize both forms to one connector representation in `LayoutRow`.
No document schema or persistent role metadata is added.

The Qt-free feature validator owns reference exclusivity, plus-note eligibility,
and wrap boundaries. The measured Qt planner owns painted bounds and translation.
`layout-document` uses those owners. Captions
remain owned by their molecular block; connector notes cannot also be captions
or block items. Plus-linked runs are indivisible for wrapping. An incoming arrow
can move to the beginning of the next line with its target run.

## Verification and limits

Feature tests cover legacy arrow input, mixed connectors, invalid and duplicate
references, and wrapping. Canvas tests check measured geometry. CLI tests cover saved layout, reopening and SVG export. Run `make check`.

Only existing plus notes and arrows are supported; connectors are not generated.
Explicit connectors are rejected in `align-y` mode. Oversized plus-linked runs
fail before editing. Existing arrow color options affect arrows only. This does
not change molecular depiction or macrocycle policy.
