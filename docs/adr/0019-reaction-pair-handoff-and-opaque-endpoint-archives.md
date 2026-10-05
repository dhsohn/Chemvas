# ADR 0019: Reaction-pair handoff and opaque endpoint archives

- Status: Superseded by [ADR 0035](0035-retire-rdkit-chemistry-provider.md)
- Date: 2026-09-27
- Supersedes: [ADR 0018](0018-reaction-pair-handoff-and-retired-precomplex.md)

## Problem

Before #488 the desktop Calculation dialog edited the plan but did not check
or export a pair. Its mapping text sent users on to the CLI ("pack-step remains
blocked until both endpoints have a complete one-to-one source mapping", in
`ui/dialogs/calculation_step_dialog.py` at 8ba1818), and only `pack-step` ran
the expanded-atom checks, as
`tests/test_calculation_step_cli.py::test_pack_step_rejects_generated_hydrogen_mismatch_without_partial_output`
shows. #488 states its motivation as recording atom correspondence between 2D
reactant and product drawings, saving it in the `.chemvas` file and using that
mapping to explain bond changes. The guide it added describes the exported
folder as input for external NEB preparation (`docs/AGENT_CLI.md`, desktop
reaction mapping).

Chemvas 0.16.0 removed the precomplex commands, and its changelog records why
`pack-step` stopped requiring placements: a drawing does not determine how
separate molecules sit against each other. Stored precomplex data was "kept but
no longer used", yet the document reader still validated it with the geometry
validator and placement profiles (`domain/document/precomplex.py` and
`precomplex_profile.py` at 8ba1818). #488 removed that validation and gives no
reason beyond "Removed precomplex geometry/profile interpretation while
preserving archived v2 document data"; the record does not say why it was
removed then rather than kept. Documents written by earlier releases still hold
multi-step plans and reviewed endpoint ensembles, such as the
`legacy-reviewed-precomplex` fixture written by Chemvas 0.15.0
(`tests/fixtures/document-v7/README.md`).

ADR 0018, merged with #488, lacks the citations and named checks that
`docs/adr/README.md` requires and gives a reason that no pull request or commit
records. The code merged with it (1fba9fa) also departed from that ADR, the
guides or the tier rules in four places:

- `core/calculation_handoff.py` imported `chemvas.features.calculation_bundle`,
  the only `core` module that imported `features`, and the package root for
  the Chemvas version, although `docs/ARCHITECTURE.md` states that `core` and
  `features` import only `domain`. Its builder took the document and the
  source bytes as separate arguments and hashed the bytes itself when the
  document carried no digest; no caller reached that fallback.
- `core/calculation_handoff_folder.py` wrote the observation it was given with
  its own JSON encoding (`ensure_ascii=True`) rather than the `machine.json`
  bytes the check wrote, and published `machine.json`, whose handoff status
  reads `ready`, second, before the XYZ files and the README.
- `domain/document/retired_endpoint_data.py` bounded archive numbers by digit
  count and read integral ones as integers, while the document reader turns
  every fraction or exponent into a float (`normalize_json_numbers`). An
  archived `1e400` therefore opened, became infinite in the open document and
  could no longer be encoded, because the archive encoder refuses non-finite
  numbers; editing another pair rewrote an archived `3.0` as `3`.
- `plan_with_replaced_step` in `features/calculation_bundle/plan.py` cleared
  the archives of every pair when an edit repaired the charge of a shared
  state, although ADR 0018 and `docs/AGENT_CLI.md` say that edits clear the
  archives of affected pairs.

## Decision

A right-side dock exposes structures, atom review, then check/export. Atom
correspondence is edited on the existing canvas, not in a separate window. A
transient event filter consumes mapping clicks without forwarding drawing
gestures; Escape exits it, and overlays are removed on exit, panel hide or
source change. Canvas edits and document switches invalidate the checked
snapshot and disable old draft operations until an explicit reload. Save draft
remains an undoable plan mutation. The source snapshot is compared again before
check/save/export. The reusable form owns pair edits; the dock owns the
active-document binding; `calculation_canvas_mapping` owns the temporary input
mode and its overlays.

Source mapping, expanded geometry validation and researcher confirmation remain
separate. State IDs and component roles are optional detail. Existing plans
remain editable one pair at a time; the scope does not grow into calculation
execution or planning.

`features.calculation_bundle` owns the Qt- and provider-free handoff builder,
so `core` imports only `core` and `domain` modules and `features` only
`features` and `domain` modules. The builder takes one result of the
exact-bytes reader, the bytes it read and the document it parsed and hashed
from them, so that the digest, size, version and operation id in the
observation come from one read, and it refuses a document that carries no
reader digest.
It does not hash the source again: every CLI operation hashes its source once,
in the reader, since #415 (`tests/test_cli_source_digest.py`). It takes the
chemistry backend through a protocol of the two members it calls, with no
default, and the producer version as an argument. CLI dispatch in
`bootstrap.calculation_bundle` supplies RDKit and the Chemvas version, retains
argument and file-boundary checks and writes `machine.json` with the shared CLI
JSON encoder, producing the bytes `pack-step` wrote before. A desktop QProcess
invokes that CLI on an exact private snapshot, keeping geometry work
cancellable and outside the GUI thread. Any edit invalidates the checked
artifact and confirmation.

`core.calculation_handoff_folder` creates a new folder; creating an existing
destination is an error. It publishes the exact source snapshot, the XYZ files
and a README first and the checked `machine.json` bytes unchanged and last, so
a folder without `machine.json` is incomplete. Single-component XYZ rows use
canonical path indices. Multiple components remain separate, with their
existing index maps, rather than invented assemblies. The machine-observation
v1 and elementary-step v2 contracts do not change.

Delete the precomplex geometry validator and placement profiles. The isolated
`domain.document.retired_endpoint_data` reader preserves historical v2 endpoint
JSON without interpreting scientific metadata. It checks the kind and ordinary
JSON encoding and reads numbers as the floats the document reader makes of
them, refusing a number that is not finite as a float when the document opens;
the enclosing document owns file and structure bounds. No calculation code
interprets archived coordinates, selections, profiles or hashes. A plan edit
clears the archives of the edited pair, as the 0.16.0 changelog records, and of
each pair that uses a shared state whose charge the edit repairs; other pairs
and unchanged saves retain them. This preservation exception ends only when the
durable v2 plan reader is retired. A destructive conversion of stored documents
is not part of this decision.

## Verification and limits

- Document and CLI compatibility: `tests/test_document_compatibility.py` reads,
  re-saves and patches the 0.15.0 archive fixture and refuses archive numbers
  beyond the float range when a document opens;
  `tests/test_calculation_step_cli.py` shows that `pack-step` ignores archives
  and that the removed precomplex commands are rejected; and
  `tests/test_architecture_boundaries.py::test_retired_precomplex_has_no_geometry_or_profile_implementation`
  keeps the validator removed.
- Archive invalidation: `tests/test_calculation_plan_edit.py` and
  `tests/test_calculation_step_dialog.py` cover no-op edits, dependency edits,
  shared-charge repair and the spelling of archives kept beside an edit.
- Canvas mapping, overlays and edit invalidation:
  `tests/test_calculation_panel.py`,
  `tests/test_calculation_mapping_highlight.py` and
  `tests/test_calculation_pair_workflow.py`, which also covers worker
  cancellation and launch failure.
- Source binding: `tests/test_cli_source_digest.py` checks that each CLI
  operation reads and hashes its source once, and
  `tests/test_calculation_handoff_folder.py` that the observation records the
  reader's digest with the size and operation id of the bytes read and that
  the builder refuses a document without the reader's digest. The latter also
  covers canonical XYZ order, no-overwrite, cleanup after a failed export,
  publication of the checked bytes and `machine.json` last.
- Real RDKit: `tests/test_calculation_step_rdkit.py` exports single and
  separate components from the desktop, compares the folder's `machine.json`
  with the worker's bytes and reports an implicit hydrogen mismatch; it runs in
  CI's RDKit job.
- Layering: `tests/test_package_dependencies.py` measures that, of Chemvas
  modules, `core` imports only `core` and `domain` and `features` only
  `features` and `domain`, and pins the callers of the calculation operations
  and of the folder publisher.

#488 records a macOS `make check` and native macOS runs of the panel. The
check does not establish quantum convergence, physical endpoint placement or a
valid NEB path; users must review those externally. The builder does not
hash the bytes it is given again, so it cannot tell bytes and a digest taken
from two different reads from one read; `pack-step`, its one caller, passes
the reader's result unchanged. Folder publication is not atomic as a whole: an
export stopped without cleanup, such as by a killed process, can leave a
folder without `machine.json`, which must be removed by hand before exporting
to the same name.
