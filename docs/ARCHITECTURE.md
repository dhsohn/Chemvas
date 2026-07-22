# Architecture

## Current Implementation Map (Non-Normative)

This section describes the code as it exists during migration. The target
package boundaries and dependency direction are defined by
[ADR 0001](adr/0001-feature-oriented-modularization.md); new features should
follow the ADR instead of copying the flat `core` / `ui` layout below.
- CanvasView (`app/chemvas/ui/canvas_view.py`): input handling, tool dispatch, selection state, and coordinating model/render/history updates. It should not own low-level drawing primitives.
- MoleculeModel (`app/chemvas/domain/document/model.py`): pure atom/bond data and IDs. No Qt dependencies.
- RDKitAdapter (`app/chemvas/core/rdkit_adapter.py`): optional chemistry backend for SMILES import, property calculation, 3D coordinate generation, alias expansion, and preview scene building. UI code should treat it as a best-effort service, not a required startup dependency.
- Renderer (`app/chemvas/core/renderer.py`): style, pens/brushes, font settings.
- HistoryCommand (`app/chemvas/core/history.py`): delta-based undo/redo. Multi-entity operations are grouped with `CompositeCommand`, which applies its child delta commands in order on redo and in reverse on undo.
- BondRenderer (`app/chemvas/ui/bond_renderer.py`): bond QGraphicsItem creation/updates and geometry helpers, driven by CanvasView context.
- Graphics items (`app/chemvas/ui/graphics_items.py`): non-selectable QGraphicsItem wrappers.
- Label layout (`app/chemvas/features/annotations`): pure, Qt-free parsing of a raw atom-label string into typographic runs (subscripts) plus their placement. It is the single source of truth for both on-screen and outlined export typography.
- Figure export (`app/chemvas/features/export`): the feature package owns its public API, Qt-free dialog/plan rules, scene scoping, and SVG/PDF/raster renderers. External callers import only `chemvas.features.export`; renderer modules are private implementation details. The pure plan computes the padded source rect / physical output size in points. The Qt service collects visible content items, excludes transient overlays, uses item-specific export bounds when available, outlines labels, and renders to SVG, PDF, PNG, or TIFF. `unit_scale` or `target_width_pt` gives deterministic physical sizing independent of zoom; `scope` and `background` choose the exported content and backdrop.
- Template previews (`app/chemvas/features/insertion`, `app/chemvas/ui/insert_template_service.py`): the insertion public API owns preview planning and geometry, including aromatic inner segments for benzene. `InsertTemplateService` and the shared `preview_scene_*` modules are the single runtime/rendering path; the former benzene-specific preview service and state have been removed.
- Hover (`app/chemvas/features/hover`, `app/chemvas/ui/hover.py`): the feature public API owns the Qt-free transient state and update policy. One per-canvas `HoverController` owns Qt orchestration, while `hover_rendering.py` owns graphics-item helpers. `canvas_hover_state.py` remains a one-function runtime-state leaf to keep the eager import graph acyclic. `CanvasRuntimeServices.hover` exposes the controller directly; the former hover access/ports/bundle and four-service stack have been removed.
- Domain document (`app/chemvas/domain/document`): owns the Qt-free molecule model plus versioned document/clipboard serialization and validation policies. The former `chemvas.core.model` and `document_state` paths have been removed.
- Migrated feature policies (`app/chemvas/features/{export,session,annotations,rendering,insertion,selection,hover}`): each package exposes one public API for its cohesive planning/geometry/state contracts. The former flat compatibility modules have been removed and `test_package_dependencies.py` prevents their return.
- Main-window composition: `chemvas.shell.main_window` owns the thin Qt shell; `chemvas.bootstrap` owns runtime/service assembly, window registration, document opening, and application startup. Qt file-open events enter through `chemvas.adapters.qt`.

## Transitional Legacy UI Discipline (ports / access / state / services)
The `app/chemvas/ui` package retains small role modules where they separate real legacy responsibilities. The goal is that `CanvasView` and `MainWindow` stay thin Qt shells (no god object), every service is constructible headlessly, and all dependencies are explicit.

These rules remain migration constraints for code that still lives in the flat
legacy package. They are not a template that every new feature must reproduce:
new feature packages create role modules only when the boundary is useful.

- **State modules** (`*_state.py`): unmigrated concerns use one dataclass plus a `<name>_state_for(canvas)` accessor. Those accessors go through `ensure_canvas_state(canvas, name, factory)` (`chemvas.ui.canvas_state_lookup.py`), which uses a single name for lookup and attach. On real canvases state lives in the eagerly-built, strict `CanvasRuntimeState` container (`chemvas.ui.canvas_runtime_state.py`); an unknown field fails loudly instead of creating a shadow copy. Plain-object attachment is limited to headless legacy collaborators and is removed when the final legacy state accessor moves to a canonical feature runtime. A handful of states (`model`, `renderer`, `bond_renderer`, `rdkit`) are deliberately stored as direct canvas attributes with `runtime_field=False`. Migrated hover state is owned by `chemvas.features.hover`; its thin UI leaf reads the required runtime field directly and never attaches or falls back. `test_state_accessor_names_match_runtime_state_container` enforces the remaining `ensure_canvas_state` names.
- **Access modules** (`*_access.py`): free functions (`foo_for(canvas)`) wrapping one operation. They must not reach into `canvas.services` directly; service lookup is delegated to the matching ports module.
- **Ports modules** (`*_ports.py`): the only modules that resolve the service container (`canvas_services_for` / `window` private storage). Everything else receives collaborators via injection or calls a port. Production ports read only the grouped `CanvasRuntimeServices` API (with single runtimes such as `atom_label_service` stored directly). Flat service aliases and duck-typed production adapters are removed; focused tests build partial canonical runtimes with `tests/runtime_services.py`.
- **Services and controllers**: constructed once per canvas in `chemvas.ui.canvas_service_composer.py` with explicit keyword injection — no service locator inside services, no `=None` collaborator defaults that hide a missing wire. The composer stores cohesive legacy groups as bundles in `CanvasRuntimeServices`; a feature with one runtime, such as hover, is stored directly instead of receiving a one-member bundle.
- **core is UI-free, with one recorded Qt migration debt**: `app/chemvas/core` must not import `ui` at module level (a lazily resolved protocol implementation is the one sanctioned exception, see `chemvas.core.history.py`). `chemvas.core.renderer.py` is the only existing direct Qt dependency; it is frozen as transitional debt and will move to the Qt adapter during the namespace migration. New core-to-Qt dependencies are forbidden.

These rules are enforced by `tests/test_architecture_boundaries.py`. New rules
must be dependency contracts or general pattern bans. Some legacy checks still
pin removed names or implementation locations; each feature migration replaces
those checks with package/public-API contracts before retiring them.

Known trade-offs of this discipline (accepted deliberately): a real indirection tax (~20% of ui LOC is wiring) and weak static typing at the canvas seam (`canvas: Any`). When an invariant spans several of these small modules (e.g. the derived graph index), the consistency contract must be written down in one owner module — see `chemvas.ui.graph_index_operations.py` and `CanvasGraphService.bond_id_between_with_repair` for the pattern.

## Feature Qt Migration Inventory

The target boundary keeps concrete Qt integration in `chemvas.adapters`, but the
ongoing namespace migration still has direct Qt imports in a fixed set of feature
implementation modules. `FEATURE_QT_MIGRATION_ALLOWLIST` in
`tests/test_package_dependencies.py` is the executable inventory: new modules may
not join it, and each adapter migration removes its module from the set. When the
set becomes empty, replace the inventory check with an unconditional ban on Qt
imports from `chemvas.features`.

## Transaction and Recovery Ownership

- `chemvas.domain.transactions` owns framework-free restore outcomes, hostile-descriptor-safe bound attribute ports, retry/error preservation, and the exact history stack authority snapshot.
- `chemvas.ui.transactions` owns Qt-aware command payload, object graph, scene-item attach, and scene-rect savepoints. The former flat snapshot modules are deleted, and an architecture ratchet prevents their return.
- Transaction behavior is intentionally not collapsed into one generic context manager. Reversible mutations restore an absolute snapshot, document replacement restores the previous document or fails closed, long drags use savepoint-style authority, and scene reset converges to empty after Qt item destruction. Shared primitives are reused only where those semantics agree.

## Data/Render Flow
Tools -> CanvasView -> MoleculeModel mutation -> Renderer/BondRenderer -> QGraphicsScene updates -> HistoryCommand push.

3D flow: export command or preview refresh -> current molecule / active atom-bond selection -> MoleculeModel subgraph + atom mark annotations -> RDKitAdapter conversion graph build -> RDKit 3D embedding -> `.xyz` writer or preview scene.

## Composite Grouping
When an operation touches multiple entity types at once (ex: atom creation plus bond creation), CanvasView groups the individual delta commands into a single `CompositeCommand` so the whole operation undoes/redoes atomically.

## 3D Conversion Constraints
- Export scope is limited to chemical graph data. Arrows, bracket annotations, free text, and other scene-only annotations must be ignored when building the export payload.
- RDKit stays optional. If it is unavailable, the export action should fail with a clear message rather than introducing a hard dependency into app startup.
- Canvas charge/radical marks should be normalized into per-atom annotations before conversion so formal charge and radical electrons survive into RDKit.
- Supported aliases (`Me`, `Et`, `OH`, `Ph`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `i-Pr`) should be expanded into explicit fragments at conversion time. Unsupported abbreviations must still fail loudly instead of guessing.
- Wedge/hash bonds should be translated into RDKit bond directions on single bonds only. Invalid stereo usage should fail with a precise message.
- `.xyz` is coordinate-only. Bond order and reaction semantics are not preserved in the output format and should not be treated as round-trippable state.
- The preview window should reuse the same conversion path as `.xyz` export to avoid divergence between what the user sees and what gets exported.
- The 3D preview opens as a separate modeless window from the toolbar. It uses the selected-structure conversion path, owns the `Export 3D XYZ` action for the selected molecule, and shows an empty preview when no chemical structure is selected.
- Each open canvas tab is an independent document with its own file path and clean/dirty digest. `.chemvas` loading accepts only the canonical single-canvas payload.
- `.chemvas` documents are versioned (current: v4; v1–v3 stay loadable). v4 stores bonds as a compact array: deleted-slot tombstones (`null` entries in pre-v4 files) are runtime bookkeeping and never reach the document. Bond identity is runtime-scoped — no document section references bonds by position or id (atoms carry explicit ids because marks, ring fills, groups, and perspective state reference them).

## Refactoring Sequence

The active modularization sequence, completion criteria, and dependency rules
are maintained in [ADR 0001](adr/0001-feature-oriented-modularization.md).
