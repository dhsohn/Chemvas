# ADR 0012: Flat editor runtime and `ui` subpackages

- Status: Accepted
- Date: 2026-09-24
- Extends: [ADR 0005](0005-responsibility-based-editor-boundaries.md)

## Problem

ADR 0005 declared the `access`, `ports`, `state`, `service` and `bundle`
conventions optional, but the code still carried 85 such modules (about 8,100
lines) and the architecture tests still required them. Of the 596 top-level
functions in the access, ports and state modules, 328 were single-statement
forwarders, and 21 modules consisted of nothing else. One collaborator could be
reached four ways: `canvas.services.history_service`,
`canvas_services_for(canvas).history_service`,
`history_service_for_access(canvas)` and `history_service_for_window(window)`.

`tests/test_architecture_boundaries.py` held 246 tests over 6,159 lines; 44 of
them were inventories of removed module names, seven forbade instantiating a
service anywhere but its bundle module, and one hard-coded four access modules
as the only places allowed to read `canvas.renderer`. Removing a forwarder
therefore failed a test that existed only to keep it.

The package diagram in `docs/ARCHITECTURE.md` did not match the import graph.
It drew `ui --> adapters`, an edge with zero imports that a test forbids, and
omitted three real upward edges: `core -> features.insertion` (the `Molecule3D*`
value types), `ui -> bootstrap` (the window registry) and
`ui.annotations -> ui` (29 imports). `ui` held 273 flat modules and 62% of the
production code.

## Decision

1. Architecture tests assert contracts, not inventories. Tests that assert a
   module name is absent, that a helper must be routed through a named access
   or bundle module, or that a class may only be instantiated in one file are
   removed. The remaining suite keeps domain and core Qt-free, the eager import
   graph acyclic, feature public APIs, single state ownership, private-member
   isolation and the rollback and recovery owners of ADRs 0002 to 0004.
2. `CanvasRuntimeServices` is flat. Every runtime the canvas assembles is a
   direct field; the eight `*ServiceBundle` dataclasses and their builder
   modules are removed and their construction moves into
   `chemvas.ui.canvas_services`.
3. Each canvas-owned collaborator has one spelling. Runtimes are read as
   `canvas.services.<name>`, state as `canvas.runtime_state.<name>`, and the
   objects canvas setup creates as `canvas.model`, `canvas.renderer`,
   `canvas.rdkit`, `canvas.render_context` and `canvas.bond_renderer`.
   `CanvasView` declares these attributes. Modules whose only content was a
   forwarder to one of those spellings are removed; a `*_state` module keeps
   its dataclass and loses its `*_state_for` accessor.
4. `domain` owns the Qt-free chemistry value types (`Molecule3DAtom`,
   `Molecule3DBond`, `Molecule3DScene`, `MoleculeIdentifiers`, `RDKitResult`).
   `shell` owns the application window registry. After both moves the import
   graph has no upward edge: `bootstrap -> editor -> policy -> domain`, where
   the editor tier is `ui`, `ui.annotations`, `ui.transactions` and `shell`, and
   the policy tier is `features` and `core`.
5. Window-level operations have one implementation. The `*_for_window`
   functions duplicated between `chemvas.ui.main_window_ports` and closures in
   `chemvas.bootstrap.main_window_services` are unified so that menu, shortcut
   and context-bar entry points run the same code.
6. `ui` is grouped into subpackages by responsibility, following the existing
   name prefixes (`canvas`, `scene`, `main_window`, `selection`, `bond`,
   `structure`, `preview_3d`, and so on). Moves are file relocations with import
   updates; they do not change behavior, public feature APIs, the CLI, or the
   document format.

## Verification and limits

Every slice runs `make check`. Removed names are proven absent by an unfiltered
search of the whole checkout, including tests, docs and CI configuration. The
package diagram is regenerated from the measured import graph and checked
against it. Behavioral workflow tests (editing, cancellation, Undo/Redo,
recovery from failed edits, document persistence) are preserved; only
wiring-only assertions are removed.

This ADR does not split the modules over 1,000 lines
(`domain/document/state.py`, `ui/transactions/scene_runtime.py`,
`core/rdkit_conversion.py`, `core/history.py`, `scene_delete_controller.py`,
`canvas_note_controller.py`, `calculation_step_dialog.py`); that is separate
work with its own measurement. It also leaves `core` and `features` as two
packages in one tier rather than merging them.
