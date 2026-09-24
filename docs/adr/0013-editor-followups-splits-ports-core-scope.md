# ADR 0013: Editor follow-ups: module splits, window ports, core scope

- Status: Accepted
- Date: 2026-09-24
- Extends: [ADR 0012](0012-flat-editor-runtime-and-ui-packages.md)

## Problem

After ADR 0012 three sources of friction remained. Seven modules were longer
than 1,000 lines, each holding two or three responsibilities that changed for
different reasons. The twelve main-window services received their window
accessors as constructor callbacks, so `bootstrap/main_window_services.py`
re-declared the same `*_for_window` functions forty times and tests built
services from bags of fakes. `core` held four tool-logic modules and the
template-geometry policy beside the history engine and the RDKit backend, so
its name did not say what belonged there.

## Decision

1. Modules over 1,000 lines are split along their responsibility seams, by
   file relocation of whole definitions; no definition changes behavior.
   `domain/document/state.py` keeps serialization and payload assembly;
   `schema.py` holds versions, keys, valid kinds and limits; `state_values.py`
   holds value predicates and normalizers; `state_validation.py` validates
   documents, settings and clipboard payloads. `core/history.py` keeps the
   command base, transaction scope and `CompositeCommand`; `core/model_commands.py`
   holds the concrete model commands, which opt into exact-transaction handling
   through the two class flags instead of an `isinstance` list.
   `ui/transactions/scene_runtime.py` captures; `scene_runtime_restore.py`
   restores. `ui/scene/scene_delete_session.py` holds the delete tool's
   transaction session. `ui/canvas/canvas_note_snapshots.py` holds note
   rollback snapshots. `ui/dialogs/calculation_step_widgets.py` and
   `calculation_plan_actions.py` hold the dialog's widgets and the window entry
   point. `core/rdkit_conversion.py` keeps the conversion helper's public
   surface and mol construction; alias fragments, atom correspondence, 3D
   embedding and stereo assignment live in their own modules as mixins.
2. Window services import `chemvas.ui.window.main_window_ports` directly.
   Constructors take only cross-service collaborators and the two callbacks
   that are late-bound at assembly (context-bar refresh, document chrome
   refresh). Tests patch the port name on the service module. The one
   observable consequence is that the context bar's rotate and bond-length
   controls now run the same window operations as the Edit menu, so they
   cancel an active pointer gesture first, as flip, align and distribute
   already did after ADR 0012.
3. `core` is the Qt-free engine tier: history, the optional RDKit backend,
   molfile and SVG round-trips and document I/O. Tool logic lives with the
   tools in `ui/tools`, template geometry with structure building in
   `ui/molecule`. `core` and `features` stay separate packages in one tier;
   merging them would add re-export `__init__` modules for the feature
   public-API rule without removing a concept.

## Verification and limits

Every slice ran `make check`. Removed constructor parameters and moved
definitions are proven absent by an unfiltered search. The conversion helper's
mixins keep method bodies verbatim; RDKit-backed tests exercise them locally.
No file split introduces a facade: each moved name is imported from its new
module by every caller.
