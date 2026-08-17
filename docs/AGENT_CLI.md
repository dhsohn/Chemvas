# Chemvas agent CLI

Chemvas exposes its document operations as headless commands, so an agent (or
any script) can render, inspect, edit, and hand off calculations without
starting a Qt window. Each command below documents its own guarantees; the
common theme is narrow contracts that fail closed instead of guessing.
User-facing detail (GUI, file format, shortcuts) is in
[REFERENCE.md](REFERENCE.md).

## Headless document composition

An agent can create a canonical, reopenable Chemvas v7 document from the smaller
public Composition v1 contract instead of constructing internal document state:

```bash
chemvas compose-document scheme.json --output scheme.chemvas
```

A minimal composition is:

```json
{
  "format": "chemvas-document-composition",
  "version": 1,
  "atoms": [
    {"id": 0, "element": "O", "x": 72.0, "y": 72.0,
     "explicit_label": true, "formal_charge": -1},
    {"id": 1, "element": "P", "x": 92.0, "y": 72.0,
     "formal_charge": 1}
  ],
  "bonds": [{"a": 0, "b": 1, "order": 1}],
  "notes": [
    {"text": "Condition", "x": 64.0, "y": 108.0,
     "style": {"font_size": 12, "font_weight": 700,
               "italic": false, "color": "#245caa"}}
  ]
}
```

Atom IDs must be contiguous and ordered from zero. Optional atom fields are
`color`, `explicit_label`, `formal_charge`, and `radical_electrons`; Chemvas
derives linked visual charge/radical marks from those annotations and rejects a
candidate whose electronic semantics are inconsistent. Bonds accept the normal
Chemvas order/style/color contract. The manifest can also contain bounded
`notes`, `arrows`, `shapes`, `ring_fills`, and documented canvas `settings`.
Canvas settings start from the live A4 landscape defaults; the global text size
is limited to the same 6–96 pt range as interactive note editing. Structured
note style accepts only `font_size` (6–96 pt), `font_weight`
(100–900), `italic`, and hexadecimal `color`; text is escaped and converted to
safe canonical span HTML by Chemvas rather than accepting arbitrary HTML.

The command rejects duplicate JSON keys, non-finite numbers, unknown keys,
invalid graph references, unsupported styles, and inputs larger than 1 MiB. It
builds and validates the complete candidate in memory, refuses an existing or
symlink output, and publishes one new canonical file atomically. Standard output
is a deterministic JSON report with the output SHA-256, document version, and
atom/bond counts. Existing source drawings are not inputs to this command and
are never modified.

## Headless layout diagnostics

An agent can restore a document into the real offscreen canvas and request
read-only layout warnings:

```bash
chemvas check-layout scheme.chemvas > layout-report.json
```

The current v1 checker reports these stable warning codes:

- `text-text-overlap` for intersecting visible note glyph paths;
- `text-shape-border-overlap` when note text crosses the painted shape border;
- `outside-sheet` when a visible note or shape extends beyond the sheet.

The report includes the exact source SHA-256, document version, deterministic
warning counts, persisted note/shape indices, and rounded intersection bounds.
The checker does not move objects, write history, normalize, or save the source.
Before starting Qt it conservatively rejects a document whose potential
note-pair, note–shape, and outside-sheet work exceeds 10,000 units, so the
complete deterministic warning report remains bounded.
Exit status is `0` for a valid clean document, `1` for a valid document with one
or more warnings, and `2` for invalid input or bootstrap/resource failure. It is
a diagnostic gate, not an automatic layout engine, and currently does not claim
atom-label or arrow–structure collision coverage.

## Headless document rendering

An agent can render the complete drawing through the same figure-export path as
the desktop app without opening a window or loading RDKit:

```bash
chemvas render-document scheme.chemvas --output scheme.svg
chemvas render-document scheme.chemvas --output scheme.png --dpi 600
chemvas render-document scheme.chemvas --output scheme-transparent.png \
  --background transparent
```

The output suffix selects SVG or PNG. White is the default background; PNG DPI
may be 150, 300, 600, or 1200, while SVG ignores DPI. The command starts only an
invisible offscreen Qt canvas, does not start session recovery, and leaves the
source untouched. It refuses existing files, directories, and symlinks and
publishes the new output atomically.

Standard output is a deterministic JSON report containing the exact source and
output SHA-256 hashes, document version, output byte count, physical point size,
and PNG pixel dimensions. Repeated renders are byte-identical within the same
Chemvas/Qt/font environment; Qt or font changes can alter path geometry or encoded
bytes, so consumers should use the reported hash rather than assume
cross-platform byte identity. Rendering is fail-closed at 8 MiB of source data,
20,000 graphics records, 64 MiB of output, 14,400 points per side, and—for
PNG—10,000 pixels per side or 25 million total pixels.

## Graph Patch v1

An agent can inspect every stable atom ID and then propose a bounded Graph Patch
without starting Qt or rewriting the whole `.chemvas` document:

```bash
chemvas inspect-document scheme.chemvas > inspection.json
chemvas apply-patch scheme.chemvas patch.json --dry-run
chemvas apply-patch scheme.chemvas patch.json --output revised.chemvas
```

`inspect-document` reports the exact source-file SHA-256, document version,
`next_atom_id`, complete atom/bond inventory, effective charge/radical annotations,
connected components, and dependent scene-state counts. The agent copies that exact
hash into a Graph Patch v1 precondition:

```json
{
  "format": "chemvas-graph-patch",
  "version": 1,
  "source_sha256": "<64 lowercase hexadecimal characters>",
  "operations": [
    {"op": "add_atom", "atom_id": 12, "element": "O",
     "x": 216.0, "y": 72.0, "color": "#000000", "explicit_label": true},
    {"op": "add_bond", "a": 4, "b": 12, "order": 1,
     "style": "single", "color": "#000000"},
    {"op": "update_bond", "a": 4, "b": 12,
     "changes": {"order": 2, "style": "double"}}
  ]
}
```

Supported operations are `add_atom`, `update_atom` (element/color/explicit label),
`move_atom`, `add_bond`, `update_bond`, and `remove_bond`. Operations run in order on
a private copy and publish only after full document and Calculation Plan validation.
`move_atom` also moves dependent ring-fill, bound-mark, and perspective coordinates.
Dry-run performs the identical validation and reports the candidate file hash but
writes nothing. Apply preserves the input document version, never changes the source,
and refuses to replace an existing file or symlink.

Graph Patch v1 deliberately does not delete atoms or edit charge/radical annotations,
arrows, groups, or Calculation Plans. It makes no chemical or mechanistic inference;
use the GUI or a separately reviewed plan update for those semantics.

## Headless structure inspection

Installed Chemvas can expose structures to an agent without starting Qt:

```bash
chemvas inspect scheme.chemvas
```

`inspect` needs no RDKit and prints a JSON inventory of connected components
with stable atom IDs, formal charges, and annotation totals. Machine handoff of
geometries happens exclusively through the elementary-step `machine.json`
published by `pack-step` below; there is no separate per-species bundle format.

## Calculation states and elementary steps

Draw the reactant, product, catalyst, and spectators on one canvas, then open
**Calculation ▸ Edit States and Steps...**. For each endpoint, assign every
connected component one of these inclusion modes:

- `included`: enters the XYZ geometry, electron count, charge, and multiplicity
  validation;
- `context_only`: records a catalyst, solvent, additive, or other condition but
  does not enter the calculation coordinates.

Roles (`reactant`, `product`, `catalyst`, `spectator`) belong to a step endpoint,
not globally to a structure. A state can therefore be S01's product and S02's
reactant without changing the state itself. Including a component as an
endpoint's own reactant or product disables it on the opposite endpoint (a
consumed species is not present on both sides), while catalysts and spectators
stay editable on both. The atom-correspondence table lists
only included reactant atoms and offers same-element product atoms by stable
Chemvas ID. **Suggest by structure** _(RDKit)_ fills the unmapped atoms of the
maximum common substructure; bond orders are matched loosely, so a reaction
center whose bonds only change order (e.g. C-O → C=O) is suggested too, and only
atoms whose connectivity breaks or forms are left for you. It never overwrites a
mapping you made and is a review-only starting point, not an automated mechanism
inference. While the dialog is open, each included atom is labelled with its
Chemvas ID on the drawing. Mapped reactant atoms are blue, mapped product atoms
are orange, and unmapped atoms stay gray, so mapping progress is visible on the
structure. Exact IDs shared by both endpoints, such as a drawn catalyst reused
on both sides, are suggested once; they are not inferred by element or position,
and an explicit **Unmapped** choice is preserved. Duplicate product mappings are
rejected. The GUI saves an incomplete table as a draft, while its mapped/total
status stays blocked until every included atom on both endpoints has a complete
one-to-one source map. This status covers the source mapping gate; RDKit geometry
generation and downstream chemical review are still separate requirements.
The labels are temporary overlays: closing the dialog removes them without
changing the drawing, the current canvas selection, or undo history.

Agents can attach and inspect the same contract without Qt:

```bash
chemvas attach-plan scheme.chemvas plan.json --output mechanism.chemvas
chemvas inspect-plan mechanism.chemvas
chemvas pack-step mechanism.chemvas --step S01 --output calculations/machine.json
```

For a step with exactly two included components on each endpoint, generate and
review bounded rigid-placement candidates before packing:

```bash
chemvas generate-precomplex mechanism.chemvas precomplex-request.json \
  --step S01 --output mechanism-candidates.chemvas
chemvas inspect-precomplex mechanism-candidates.chemvas --step S01
chemvas select-precomplex mechanism-candidates.chemvas --step S01 \
  --reactant-candidate <candidate-id> --product-candidate <candidate-id> \
  --reviewer <reviewer> --output mechanism-reviewed.chemvas
chemvas pack-step mechanism-reviewed.chemvas --step S01 \
  --output calculations/machine.json
```

The strict request binds generation to the exact input through
`source_document_sha256` and `step_id`, names one intercomponent contact per
endpoint, records an explicit gas-phase or solvent environment, and sets a
retained candidate cap. Generation writes a new version-7 document with
Calculation Plan v2 and `selection: null`; `inspect-precomplex` exposes IDs,
provenance, validation metrics, hashes, and exact XYZ. `select-precomplex`
records one reactant/product pair with the same reviewer and timestamp and binds
each selection to its XYZ hash. Before handoff, `pack-step` deterministically
regenerates both bounded ensembles from the current graph, plan, RDKit
provenance, contacts, and profile and rejects any mismatch. Placement scores are
geometric clash and contact metrics, not energies or stability rankings.
Unreviewed or partially reviewed multicomponent endpoints remain blocked.

Precomplex generation accepts request format v2 only and requires
`"profile": "chemvas-rigid-precomplex-placement/2"`. This profile uses the
covalent radii from [Cordero et al., Table 2](https://doi.org/10.1039/B801115J)
(C sp3 and low-spin Fe/Co entries) and the van der Waals radii from
[Alvarez, Table 1](https://doi.org/10.1039/C3DT50599E) for every supported
element. The ensemble, generation/inspection reports, and final
`machine.json` placement metadata carry the profile, dataset IDs, DOIs, and an
exact radius-table hash. Other request versions and placement profiles are
rejected.

The profile is stored in document version 7 and Calculation Plan v2. These
cited radii and Chemvas's thresholds still define a deterministic geometric
heuristic: designated contacts use `0.85 ×` the covalent-radius sum; other pairs
use the
larger of `1.05 ×` the covalent-radius sum and `0.60 ×` the van der Waals-radius
sum; soft-overlap scoring uses `0.85 ×` the van der Waals-radius sum. This is
not a hard-sphere physical model, energy, or stability claim. Fe/Co spin and
coordination are not represented in the current input model, so the documented
low-spin selector is fixed rather than inferred. Researcher review and
downstream quantum optimization remain required.

`plan.json` uses Calculation Plan v2. States own calculation membership and
charge/multiplicity; step endpoints own roles:

```json
{
  "format": "chemvas-calculation-plan",
  "version": 2,
  "states": [
    {"id": "R01", "charge": 0, "multiplicity": 1,
     "members": [
       {"component_atom_ids": [0, 1], "inclusion": "included"},
       {"component_atom_ids": [9], "inclusion": "context_only"}]},
    {"id": "P01", "charge": 0, "multiplicity": 1,
     "members": [{"component_atom_ids": [2, 3], "inclusion": "included"}]}
  ],
  "steps": [{
    "id": "S01",
    "reactant": {"state_id": "R01", "roles": [
      {"component_atom_ids": [0, 1], "role": "reactant"},
      {"component_atom_ids": [9], "role": "spectator"}],
      "precomplex": {"kind": "none"}},
    "product": {"state_id": "P01", "roles": [
      {"component_atom_ids": [2, 3], "role": "product"}],
      "precomplex": {"kind": "none"}},
    "atom_correspondence": [
      {"reactant_atom_id": 0, "product_atom_id": 2},
      {"reactant_atom_id": 1, "product_atom_id": 3}]
  }]
}
```

Every `component_atom_ids` list must equal one complete connected component and
must be sorted. `pack-step` atomically writes exactly one non-overwriting file
named `machine.json`. It uses the shared `factory/machine-observation` v1
envelope and a `chemistry/elementary-step` v1 payload containing the source
document hash, endpoint state and RDKit atom provenance, complete
source/generated atom correspondence, and bond changes. Draw transferred
hydrogens explicitly when implicit-hydrogen counts differ between endpoints;
the generated atoms must also form a complete bijection.

`inspect-plan` reports a deterministic `path_precheck` for each step. When the
source mapping is complete, both endpoints have the same charge and
multiplicity, and either each endpoint is single-component or both
multicomponent endpoints have an explicitly reviewed precomplex selection, the
single artifact's `endpoint_pair` contains the exact reactant/product XYZ text
and hashes. The product XYZ is rewritten into the reactant atom-identity order;
the same object records that order and the bond-change reaction-center atoms as
canonical 0-based indices. Downstream tools therefore do not need to reconstruct
the mapping from element order or coordinates.

An incomplete source mapping still blocks `pack-step` without creating the
output. Once that gate and the generated-atom bijection pass, an unreviewed
multicomponent endpoint or electronic-state mismatch writes one observation with
`handoff.status: "blocked"`, namespaced `handoff.codes`, and
`payload.data.endpoint_pair: null`. Chemvas does not invent contacts, select a
candidate automatically, or treat generated coordinates as optimized minima.
Reviewed generated coordinates remain initial guesses requiring downstream
quantum optimization and scientific validation.
