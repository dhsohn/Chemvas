# ADR 0015: Owners for model and scene-item access, Qt-free `features`

- Status: Accepted
- Date: 2026-09-24
- Extends: [ADR 0012](0012-flat-editor-runtime-and-ui-packages.md), [ADR 0014](0014-one-spelling-for-canvas-and-window-state.md)

## Problem

After ADR 0014 two modules still stood between callers and the objects they
read. `chemvas.ui.canvas.canvas_model_access` held eighteen functions of the
form `atom_for_id(canvas, atom_id)` that did nothing but index
`canvas.model`, and 43 modules imported them; `canvas_scene_items_state`
held sixteen functions of the form `ring_items_for(canvas)` over
`canvas.runtime_state`, imported by 33 modules and 70 test files. Both were
the last places where a canvas-owned value had a second spelling, and the
model helpers were Qt-free logic living in `ui`.

`features` was documented as "Qt-free unless noted", and eleven of its
modules imported PyQt6: the selection centre, handle and outline helpers, the
whole export renderer, two insertion geometry modules and the shape path
builder. `core` had become Qt-free in ADR 0013; `features` had not, so the
policy tier in the package diagram carried a footnote instead of a rule.

Ten function bodies were duplicated across modules (`_validate_source` and
`_sha256` three times each in `bootstrap`, the pool-reset loop in four
places, the snap-on-press override in two tools, the ring-fill factory in two
build services, and so on).

## Decision

1. Model access belongs to `MoleculeModel`. The helpers become methods:
   `atom_for_id`, `set_atom`, `pop_atom`, `ensure_next_atom_id_after`,
   `created_atom_ids_from`, `bond_for_id`, `bond_ids_from`, `has_bond_slot`,
   `set_bond`, `clear_bond`, `trim_bonds`, `atom_annotation_for`,
   `set_atom_annotation`, `clear_atom_annotation`, `center` and
   `scale_about`. Callers write `canvas.model.atom_for_id(atom_id)`. The two
   helpers that touched Qt or marks stay with their single caller: the ring
   polygon rescale in the geometry controller, the mark-driven annotation sync
   in the mark scene service. The render context's private `bond_for_id`, a
   third spelling, is removed.
2. Scene-item collections belong to `SceneRenderState`, the state that owns
   both the document collections and the projection dicts. The functions
   become methods (`scene_items(name)`, `document_collection(name)`,
   `append_scene_item`, `remove_scene_item`, `clear_scene_items`,
   `restore_scene_item_order`, `ring_items()`, `note_items()`, ...), read as
   `canvas.runtime_state.ring_items()`. `require_scene_record_id` and the two
   collection tables stay in `canvas_scene_items_state` next to the
   projection dataclass. Tests that need a runtime state get a real
   `SceneRenderState` subclass from `tests/runtime_state.py`, so the methods
   work on the double.
3. `features` is Qt-free, and `test_package_dependencies` asserts it for the
   whole layer. The eleven Qt-using modules move to the `ui` subpackage that
   uses them (`ui.selection`, `ui.export`, `ui.insert`, `ui.molecule`,
   `ui.annotations`) and keep the strict mypy profile they had; the feature
   packages stop re-exporting them, and `features.insertion` loses its lazy
   `__getattr__`. The one annotation-only Qt import (`rotation.py`) becomes a
   two-method `Point2D` protocol.
4. Duplicated bodies have one home. `bootstrap.document_cli_shared` gains
   `validate_source_document` and `sha256_hex`; `preview_scene_renderer.clear_scene_items`
   returns the empty pool and replaces `clear_smiles_preview`,
   `clear_bond_preview_items` and `clear_handle_items`; `PreviewDragTool`
   gets a `snap_start_point` class flag instead of two identical
   `on_mouse_press` overrides; `bond_pair_key` is public in
   `domain.document.state_values` and the two feature copies import it.
   Forwarders that callers bind as callbacks (the scene controllers' state
   getters, the build service's `has_atom`) stay, as ADR 0014 already ruled.

Each of the four decisions lands as its own change with its own `make check`,
in the order 3, 1, 2, 4, so a file move, a mechanical rewrite and a
behaviour-neutral cleanup can be reviewed and reverted separately.

## Verification and limits

The removed names are proven absent by an unfiltered search of the checkout.
Tests that patched a removed seam patch the owner (`type(canvas.runtime_state)`
for a method, the mark scene service's `sync_marks_for_atom`); tests that
faked the model with a namespace use `MoleculeModel`.
The runtime-state double in `tests/runtime_state.py` used to be a namespace
that raised on any field a test had not supplied; as a `SceneRenderState`
subclass it now carries real default drawing-state fields and `None` for the
editor-only ones, so a test that forgets a field sees an empty state instead
of an error. That precision is traded for methods that work on the double.

Not done here: the small state dataclasses (`CanvasGroupState`,
`SheetSetupState`, ...) were candidates for merging into the runtime state
module, but each module also holds two to eight operations on its state, and
the container module imports half of `ui`, so merging would create import
cycles for no gain in clarity. They stay as they are. The `MainWindow`
boundary types (`services`, `runtime_state`, `tab_references` returning
`Any` since ADR 0012) and the 21 state-writing forwarders inlined in
ADR 0014 are the subject of the next decision, not this one.
