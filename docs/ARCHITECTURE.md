# Architecture

## Current Implementation Map (Non-Normative)

This section describes the code as it exists during migration. The target
package boundaries and dependency direction are defined by
[ADR 0001](adr/0001-feature-oriented-modularization.md); new features should
follow the ADR instead of copying the flat `core` / `ui` layout below.
- CanvasView (`app/chemvas/ui/canvas_view.py`): input handling, tool dispatch, selection state, and coordinating model/render/history updates. It should not own low-level drawing primitives.
- MoleculeModel (`app/chemvas/domain/document/model.py`): pure atom/bond data and IDs. No Qt dependencies.
- RDKitAdapter (`app/chemvas/core/rdkit_adapter.py`): optional chemistry backend for SMILES import, property calculation, 3D coordinate generation, alias expansion, and preview scene building. UI code should treat it as a best-effort service, not a required startup dependency.
- Renderer (`app/chemvas/adapters/qt/renderer.py`): Qt pens/brushes and fonts,
  driven by the pure `chemvas.features.rendering.acs1996_style` policy.
- HistoryCommand (`app/chemvas/core/history.py`): delta-based undo/redo. Multi-entity operations are grouped with `CompositeCommand`, which applies its child delta commands in order on redo and in reverse on undo.
- BondRenderer (`app/chemvas/ui/bond_renderer.py`): bond QGraphicsItem creation/updates and geometry helpers, driven by CanvasView context.
- Graphics items (`app/chemvas/ui/graphics_items.py`): non-selectable QGraphicsItem wrappers.
- Label layout (`app/chemvas/features/annotations`): pure, Qt-free parsing of a raw atom-label string into typographic runs (subscripts) plus their placement. It is the single source of truth for both on-screen and outlined export typography.
- Figure export (`app/chemvas/features/export`): the feature package owns its public API, Qt-free dialog/plan rules, scene scoping, and SVG/PDF/raster renderers. External callers import only `chemvas.features.export`; renderer modules are private implementation details. The pure plan computes the padded source rect / physical output size in points. The Qt service collects visible content items, excludes transient overlays, uses item-specific export bounds when available, outlines labels, and renders to SVG, PDF, PNG, or TIFF. `unit_scale` or `target_width_pt` gives deterministic physical sizing independent of zoom; `scope` and `background` choose the exported content and backdrop.
- Template previews (`app/chemvas/features/insertion`, `app/chemvas/ui/insert_template_service.py`): the insertion public API owns preview planning and geometry, including aromatic inner segments for benzene. `InsertTemplateService` and the shared `preview_scene_*` modules are the single runtime/rendering path; the former benzene-specific preview service and state have been removed.
- Bond previews (`app/chemvas/features/rendering/bond_preview.py`, `app/chemvas/ui/bond_preview_renderer.py`): the feature policy computes plain-double preview segments without Qt values, and one Qt renderer builds, updates, attaches, and clears preview items through the concrete `BondRenderer`. The legacy canvas access remains only as the two active callers' adapter; resolver dataclasses, per-call lambda wiring, and separate geometry/scene-item role modules have been removed.
- Hover (`app/chemvas/features/hover`, `app/chemvas/ui/hover.py`): the feature public API owns the Qt-free transient state and update policy. One per-canvas `HoverController` owns Qt orchestration, while `hover_rendering.py` owns graphics-item helpers. `canvas_hover_state.py` remains a one-function runtime-state leaf to keep the eager import graph acyclic. `CanvasRuntimeServices.hover` exposes the controller directly; the former hover access/ports/bundle and four-service stack have been removed.
- Domain document (`app/chemvas/domain/document`): owns the Qt-free molecule model plus versioned document/clipboard serialization and validation policies. The former `chemvas.core.model` and `document_state` paths have been removed.
- Calculation plans and artifacts (`app/chemvas/domain/document/calculation_plan.py`, `app/chemvas/features/calculation_bundle`, `app/chemvas/bootstrap/calculation_bundle.py`): the document domain owns the strict v1 plan schema; the Qt-free feature API owns connected-component selection, semantic charge validation, endpoint-specific roles, correspondence readiness, bond changes, and the deterministic path precheck. The Calculation dialog projects included atoms into one ID-based mapping table, preserves partial drafts and explicit unmapped choices, and delegates the final candidate to that same feature/domain validation path. `calculation_mapping_highlight.py` owns the dialog-scoped, non-selectable R/P canvas overlays; it never enters document serialization, selection state, or history and is cleared on every dialog exit. Bootstrap owns `.chemvas` I/O, optional legacy RDKit composition, deterministic single-file step serialization, reactant-identity-ordered path endpoint generation, and atomic non-overwriting publication. `application.main` dispatches `inspect`, `pack`, `attach-plan`, `inspect-plan`, and `pack-step` before importing Qt, while an argument-free invocation keeps the desktop startup path.
- Agent document patches (`app/chemvas/features/document_patch`, `app/chemvas/bootstrap/document_patch.py`): the Qt/provider-free feature API owns deterministic full-graph inspection, strict Graph Patch v1 validation, copy-based ordered mutation, dependent coordinate movement, and final document/Calculation Plan gates. Bootstrap reads and hashes the exact source bytes, rejects duplicate/non-standard JSON, encodes the candidate deterministically, and publishes through the shared atomic non-overwriting file creator. `inspect-document` and `apply-patch` are dispatched before Qt; no natural-language model or chemistry inference runs inside Chemvas.
- Headless document rendering (`app/chemvas/bootstrap/document_render.py`): bootstrap validates the bounded file/output contract before lazily composing an invisible `QApplication` and `CanvasView`. The loaded state uses `CanvasDocumentSessionService.plan_figure_export` for a no-paint resource preflight, then the same whole-sheet figure-export path used by the GUI renders SVG/PNG to private temporary storage. Only bounded output is atomically published without replacement; the source and output hashes, point/pixel dimensions, and document version form render report v1. Desktop windows, session recovery, RDKit loading, editable SVG payloads, PDF, and TIFF are outside this command.
- Migrated feature policies (`app/chemvas/features/{export,session,annotations,rendering,insertion,selection,hover}`): each package exposes one public API for its cohesive planning/geometry/state contracts. The former flat compatibility modules have been removed and `test_package_dependencies.py` prevents their return.
- Main-window composition: `chemvas.shell.main_window` owns the thin Qt shell; `chemvas.bootstrap` owns runtime/service assembly, window registration, document opening, and application startup. Qt file-open events enter through `chemvas.adapters.qt`.

## Transitional Legacy UI Discipline (ports / access / state / services)
The `app/chemvas/ui` package retains small role modules where they separate real legacy responsibilities. The goal is that `CanvasView` and `MainWindow` stay thin Qt shells (no god object), every service is constructible headlessly, and all dependencies are explicit.

These rules remain migration constraints for code that still lives in the flat
legacy package. They are not a template that every new feature must reproduce:
new feature packages create role modules only when the boundary is useful.

- **State modules** (`*_state.py`): unmigrated concerns use one dataclass plus a `<name>_state_for(canvas)` accessor. Those accessors go through `ensure_canvas_state(canvas, name, factory)` (`chemvas.ui.canvas_state_lookup.py`), which uses a single name for lookup and attach. On real canvases state lives in the eagerly-built, strict `CanvasRuntimeState` container (`chemvas.ui.canvas_runtime_state.py`); an unknown field fails loudly instead of creating a shadow copy. Plain-object attachment is limited to headless legacy collaborators and is removed when the final legacy state accessor moves to a canonical feature runtime. Only `model` remains an intentionally direct state with `runtime_field=False`. `renderer`, `rdkit`, and `bond_renderer` are setup-owned direct collaborators, resolved through their access modules without lazy creation or fallback. Migrated hover state is owned by `chemvas.features.hover`; its thin UI leaf reads the required runtime field directly and never attaches or falls back. Input-view keeps its real state dataclass in `input_view_state.py` with lookup in the canonical `input_view_access.py`, while callback state keeps its dataclass and getter together; both getters read required runtime fields directly and never attach or fall back. Architecture tests enforce these direct-runtime exceptions and the remaining `ensure_canvas_state` names.
- **Access modules** (`*_access.py`): free functions (`foo_for(canvas)`) wrapping one operation. They must not reach into `canvas.services` directly; service lookup is delegated to the matching ports module.
- **Ports modules** (`*_ports.py`): the only modules that resolve the service container (`canvas_services_for` / `window` private storage). Everything else receives collaborators via injection or calls a port. Production ports read only the canonical `CanvasRuntimeServices` API. Cohesive legacy groups remain grouped, while single runtimes such as `graph_service`, `tool_controller`, `hover`, and `atom_label_service` are stored directly. Flat service aliases and duck-typed production adapters are removed; focused tests build partial canonical runtimes with `tests/runtime_services.py`.
- **Services and controllers**: constructed once per canvas in `chemvas.ui.canvas_services.py` with explicit keyword injection — no service locator inside services, no `=None` collaborator defaults that hide a missing wire. Assembly stores cohesive legacy groups as bundles in `CanvasRuntimeServices`; a single runtime is stored directly instead of receiving a one-member bundle. The obsolete graph/tool wrapper bundles and the builder-injection composer layer have been removed.
- **core is UI- and Qt-free**: `app/chemvas/core` must not import `ui` at module level (a lazily resolved protocol implementation is the one sanctioned exception, see `chemvas.core.history.py`) or import Qt. Concrete Qt rendering lives in `chemvas.adapters.qt.renderer`; new core-to-Qt dependencies are forbidden.

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

- `CanvasHistoryService` is the sole owner of undo/redo stack policy and of the immutable `HistoryStackSnapshot` value. Exact top-level undo/redo operations capture one document savepoint; nested commands defer to that operation.
- `chemvas.ui.transactions.document.DocumentSavepoint` is the public owner of whole-document capture, restore, verification, and release. It composes the lower-level object-graph, scene-runtime, and scene-rect primitives in the same package. `history_commands` owns command classes, not a private snapshot toolkit.
- `chemvas.domain.transactions` owns only framework-free `RestoreOutcome` validation, recovery-note attachment, and the one-shot restore helper.
- A restore is applied once and verified once. If exact restoration cannot be established, history applies ADR 0002's conservative fail-closed stack policy and leaves durable recovery to autosave/session restore. The removed retry, authority-channel, compatibility-probing, and parallel stack-snapshot layers must not return.

## Data/Render Flow
Tools -> CanvasView -> MoleculeModel mutation -> Renderer/BondRenderer -> QGraphicsScene updates -> HistoryCommand push.

3D flow: export command or preview refresh -> current molecule / active atom-bond selection -> MoleculeModel subgraph + atom mark annotations -> RDKitAdapter conversion graph build -> RDKit 3D embedding -> `.xyz` writer or preview scene.

Calculation flow: headless `inspect` -> validated `.chemvas` state -> stable connected-component inventory; `attach-plan` or the Calculation dialog -> v5 document with reusable states, endpoint-specific roles, and an explicit included-atom mapping table; mapping row/product focus -> transient blue-solid R and orange-dashed P canvas overlays -> dialog exit cleanup; `inspect-plan` -> mapping/readiness plus path precheck; `pack-step` -> complete explicit source mapping -> paired state selections and charge/multiplicity gates -> RDKit provenance for both endpoints -> generated-atom correspondence and bond changes -> one atomic `chemvas-elementary-step` v1 JSON publication -> for equal electronic states with one included component per endpoint, an inline product XYZ reordered into reactant identity order plus canonical 0-based reaction-center indices. The GUI offers only same-element product choices and suggests exact shared atom IDs once, without mechanistic inference. Draft plans may be stored with partial mappings, but `pack-step` fails closed until the included source and generated atoms form complete bijections. Multi-component steps and electronic-state-changing steps publish one blocked artifact with structured reasons and no endpoint pair; Chemvas does not infer a precomplex, rigid alignment, or optimized geometry.

Agent-edit flow: `inspect-document` -> exact source SHA-256 plus stable atom/bond inventory -> untrusted Graph Patch v1 -> strict schema/hash gate -> ordered mutations on a deep copy -> structural and semantic Calculation Plan validation -> deterministic candidate hash -> dry-run report or one atomic non-overwriting `.chemvas` publication. The input file version and out-of-scope scene state are preserved; any failed operation or stale plan produces no output.

Headless render flow: `render-document` -> exact source read/hash and record-count gate -> validated state applied to an invisible canvas -> canonical whole-sheet export plan -> point/pixel resource gate -> private SVG/PNG render -> output byte gate -> one atomic non-overwriting publication -> hash-and-dimension JSON report. Qt is lazy but required for painting; RDKit and the desktop session-recovery service are not started.

## Composite Grouping
When an operation touches multiple entity types at once (ex: atom creation plus bond creation), CanvasView groups the individual delta commands into a single `CompositeCommand` so the whole operation undoes/redoes atomically.

## 3D Conversion Constraints
- Export scope is limited to chemical graph data. Arrows, bracket annotations, free text, and other scene-only annotations must be ignored when building the export payload.
- RDKit stays optional. If it is unavailable, the export action should fail with a clear message rather than introducing a hard dependency into app startup.
- Canvas charge/radical marks should be normalized into per-atom annotations before conversion so formal charge and radical electrons survive into RDKit.
- Supported aliases (`Me`, `Et`, `OH`, `Ph`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `i-Pr`) should be expanded into explicit fragments at conversion time. Unsupported abbreviations must still fail loudly instead of guessing.
- Wedge/hash bonds should be translated into RDKit bond directions on single bonds only. Invalid stereo usage should fail with a precise message.
- `.xyz` is coordinate-only. Bond order and reaction semantics are not preserved in the output format and should not be treated as round-trippable state.
- Calculation Bundle v1 keeps the exact source document, a MOL graph, XYZ geometry, atom provenance, and hashes together for the single-species `pack` command. Calculation Plan v1 stores explicit states, `included`/`context_only` membership, endpoint-specific roles, and source atom correspondence; it does not infer them. The `chemvas-elementary-step` v1 artifact is one JSON file with inline provenance, mapping, bond changes, readiness, and a conditional identity-ordered endpoint pair. It states that multi-component interaction geometry is not guaranteed and requires downstream quantum optimization and researcher review.
- The preview window should reuse the same conversion path as `.xyz` export to avoid divergence between what the user sees and what gets exported.
- The 3D preview opens as a separate modeless window from **View ▸ Molecule Info**. It uses the selected-structure conversion path, owns the `Export 3D XYZ` action for the selected molecule, and shows an empty preview when no chemical structure is selected.
- Each open canvas tab is an independent document with its own file path and clean/dirty digest. `.chemvas` loading accepts only the canonical single-canvas payload.
- `.chemvas` documents are versioned (current: v5; v1–v4 stay loadable). v4 made bond arrays compact; v5 adds the optional `calculation_plan`. Deleted-slot tombstones (`null` entries in pre-v4 files) remain runtime bookkeeping and never reach new documents. Bond identity is runtime-scoped — the calculation plan references stable atom ids and complete connected-component atom-id sets, not bond positions.

## Refactoring Sequence

The active modularization sequence, completion criteria, and dependency rules
are maintained in [ADR 0001](adr/0001-feature-oriented-modularization.md).
The transaction/history rollback ownership, threat model, and fail-closed
recovery semantics are decided in
[ADR 0002](adr/0002-single-rollback-kernel.md).
