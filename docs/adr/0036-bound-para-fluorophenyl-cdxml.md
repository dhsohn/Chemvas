# ADR 0036: Bound para-fluorophenyl CDXML nickname graph

- Status: Proposed
- Date: 2026-10-06
- Extends: [ADR 0030](0030-cdxml-export.md)
- Recorded: 2026-10-06

## Problem

Inventory drawings can carry an explicit legend that an `Ar` label means
para-fluorophenyl (`4-FC6H4`), but ADR 0030 decision 17 only emitted a concrete
aryl graph for `aryl_fragment("Ph")`. Other fluorophenyl names, ortho/meta
isomers, and `MeOPh` have no fixed exporter graph. The document stores only the
drawn text `Ar`; legends are not read to infer chemistry.

## Decision

1. **Bound identifier only.** `CdxmlLabelBinding.aryl_fragment("4-F-Ph")` on a
   drawn `Ar` label exports a fixed para-fluorophenyl inner graph under
   `NodeType="Nickname"` with display text still `Ar`. The identifier is listed
   in a bound-only aryl catalog separate from unbound `_VERIFIED_FRAGMENTS`
   aliases; literal `4-F-Ph` on the canvas and raw `Ar` without a binding
   remain refused.

2. **Fixed graph.** Six ring carbons (indices 0–5, ipso 0 to one
   `ExternalConnectionPoint`), Kekulé ring bonds alternating single/double per
   vertex, hydrogen counts `0,1,1,0,1,1` on carbons, one fluorine
   (`Element="9"`, `NumHydrogens="0"`) singly bonded to carbon 3 (graph distance
   3 from ipso). Formula `C6H4F`. Valence checks at import: carbon 4 including
   the sole external attachment, fluorine 1. Layout is finite; the connection
   point stays on the outside neighbour. Only existing native `Element`,
   `NumHydrogens`, and bond order primitives are used; no new CDXML attributes.

3. **Unchanged guards.** Single plain external attachment rules,
   `_group_label_attachment`, stereo wide-end `Ph`, interleaving, Z-order,
   sidecar schema, and alias registry semantics are unchanged. `4-F-Ph` bindings
   require an ordinary single attachment even when other labels use stereo wide
   ends.

4. **Producer-only claim.** This records native graph encoding from Chemvas
   export tests. ChemDraw visual display, chemical interpretation, and
   roundtrip success are **not** claimed; consumer validation remains pending.

## Verification

- `tests/test_cdxml_bound_fluorophenyl.py` — synthetic export assertions for the
  graph, refusals, and displayed-leaf Z behaviour.
- Owner runs `bash scripts/check.sh tests/test_cdxml_bound_fluorophenyl.py` and
  related CDXML suites serially.

## Consequences

Export-only change in `export_cdxml.py`. No document schema, sidecar parser,
GUI, or CLI surface changes beyond what ADR 0030 already documents for
`aryl_fragment`. Ortho/meta fluorophenyl, `MeOPh`, and legend-driven inference
stay out of scope until a later decision.
