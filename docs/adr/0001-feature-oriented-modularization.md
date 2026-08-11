# ADR 0001: Feature-oriented modularization

- Status: Accepted
- Date: 2026-07-18

## Context

Chemvas currently ships 408 production Python modules. The flat `app/chemvas/ui`
package owns most production code while mixing two opposite failure modes:
small routing modules that add indirection and multi-thousand-line transaction
implementations that own too many failure-recovery responsibilities.

The existing `state/access/ports/service` conventions successfully kept
`CanvasView` and `MainWindow` small, but they are applied uniformly instead of
at feature boundaries. The public wheel also exposes `core`, `ui`, and
`chemvas` as three unrelated top-level packages. The migration must preserve
document compatibility, optional RDKit startup, Qt failure containment, and
exact undo/redo rollback behavior.

## Decision

All production code will move under the `chemvas` namespace. `app/` remains the
source root; renaming it to `src/` would be cosmetic and is not part of this
refactor.

The target package shape is:

```text
chemvas/
  bootstrap/       application construction and startup
  domain/          Qt-free molecule, document, geometry, and command models
  features/        vertical feature packages with explicit public APIs
  adapters/        Qt, RDKit, and storage implementations of feature ports
  shell/           main-window composition and application chrome
```

Feature packages may contain `state.py`, `ports.py`, `service.py`, or `qt.py`
when those roles are needed. A role does not automatically require its own
module. Cross-feature imports use a feature's public API and must not reach
into its internals.

The allowed dependency direction is:

```text
bootstrap/shell -> features -> domain
bootstrap       -> adapters -> feature ports
```

`domain` must not import Qt, RDKit, storage, adapters, shell, or another UI
surface. The composition root is the only place allowed to know concrete
adapter implementations.

## Migration sequence

1. Establish formatting, packaging, dependency, and characterization gates.
2. Move `core` and `ui` under the `chemvas` namespace with temporary shims.
3. Use figure export as the first vertical feature slice.
4. Replace the global canvas service bag with typed feature runtimes.
5. Extract one transaction/snapshot/rollback kernel.
6. Move document/session, rendering/annotations, insertion/RDKit,
   selection/tools, and finally the main-window shell.
7. Remove compatibility shims and enable stricter typing for migrated packages.

Every slice moves its tests with its implementation, preserves an acyclic eager
import graph, and is followed by lint, type, focused tests, the architecture
suite, and milestone-level full-suite/package verification.

### Recorded migration slices

- Hover is the first runtime-consolidation slice. `chemvas.features.hover` owns
  the Qt-free transient state and planning policy; one `chemvas.ui.hover`
  controller owns orchestration and `chemvas.ui.hover_rendering` owns Qt item
  helpers. `CanvasRuntimeServices.hover` references that controller directly.
- The former hover access, ports, refresh, bundle, interaction, scene, bond
  preview, and mark preview roles were removed rather than retained as
  compatibility paths. A thin `chemvas.ui.canvas_hover_state` accessor remains
  as an import-cycle leaf and reads only the strict runtime-state field.
- Benzene preview now uses the canonical insertion template policy and shared
  scene renderer. Its separate access, scene-access, service, renderer, and
  transient state were removed instead of being retained as compatibility paths.
- Canvas service lookup now accepts only the canonical `CanvasRuntimeServices`.
  Flat aliases and the production fixture adapter were removed; focused legacy UI
  tests build partial canonical runtimes in `tests/runtime_services.py`.
- The unused `StructureInsertService` and auxiliary bundle, the unused rotation
  preview controller/state, and the remaining selection/transform/service-name
  compatibility facades were removed with their internal-wiring tests.
- The one-member graph and tool bundles were removed. `CanvasRuntimeServices`
  stores `graph_service` and `tool_controller` directly, while their collaborators
  continue to receive the same instances through explicit constructor injection.
- Bond preview now keeps one Qt-free segment policy, one Qt item renderer, and a
  thin adapter for the two legacy canvas callers. Resolver dataclasses, fourteen
  per-call lambdas, silent preview-only renderer fallbacks, and separate geometry
  and scene-item role modules were removed.
- Renderer, optional-RDKit, and bond-renderer objects are direct canvas
  collaborators created once by canvas setup and read through their canonical
  access modules. Their lazy state wrappers and test-only setter seams were
  removed; missing collaborators now fail instead of creating shadow instances.
- Input-view keeps its concrete transform/zoom state in `InputViewState`, but its
  canonical access module now reads the strict runtime field directly. The former
  state-module accessor and plain-canvas lazy shadow-state seam were removed.
- Canvas callbacks remain one concrete runtime state, but their accessor now reads
  only the required `CanvasRuntimeState.callback_state` field. Plain-canvas lazy
  attachment was removed so tool, error, zoom, and selection observers cannot
  diverge onto a shadow state.
- Direct feature-to-Qt dependencies are frozen by the shrinking
  `FEATURE_QT_MIGRATION_ALLOWLIST` in `tests/test_package_dependencies.py`. A
  migration slice removes its entry when its concrete Qt implementation moves to
  `chemvas.adapters`; no new entries are allowed, and an empty set ends the
  exception.
- The three bond-glyph geometry modules left the allowlist by returning plain
  coordinates instead of Qt shapes: `bond_dotted` yields dot centres,
  `bond_stereo` a wedge triangle, and `bond_geometry` the strip corners.
  `BondRenderer` builds the `QPainterPath`/`QPolygonF` from them, which is where
  the Qt return types were already declared, so no port or adapter layer was
  added. `BondLineGeometryService` now holds no Qt shape types at all, which its
  own boundary check (`test_bond_line_geometry_delegates_special_glyph_geometry`)
  requires.
- The canvas model is created by canvas setup instead of appearing on first
  access. `model_for` reads `canvas.model`, so `ensure_canvas_state` no longer
  carries a `runtime_field` switch and every remaining accessor resolves against
  the strict runtime container. Setup also builds that container before writing
  the sheet state, which previously landed on the bare canvas and left a second,
  never-read `SheetSetupState` beside the live one.
- Step 4 is complete: all twenty remaining state accessors now read
  `canvas.runtime_state.<field>` directly, and `ensure_canvas_state` is deleted
  along with the `STRICT_STATE_CONTAINER` marker that existed only for it — a
  `slots=True` container raises on a wrong field by itself. Focused tests build a
  partial container with `tests/runtime_state.canvas_runtime_state`, which
  validates field names against the real one. One check,
  `test_state_accessors_read_the_runtime_container_directly`, replaces the
  per-state ones. `canvas_state_object` survives for `sheet_setup_state_for`,
  `document_metadata_state_for`, and the transaction kernel; those, and the two
  private copies of the same lookup in `transactions/`, are a separate seam.

## Consequences

- Large all-at-once moves are rejected in favor of behavior-preserving slices.
- Formatter-only changes remain separate from behavioral changes.
- Existing access wrappers may remain temporarily, but new one-function wrapper
  chains require a real boundary justification.
- `Any` is tolerated at unmigrated Qt seams; migrated public APIs use concrete
  types or small protocols and may not add new unbounded `Any` surfaces.
- Architecture tests transition from removed-name checks toward allowed package
  dependencies and feature public-API contracts.

## Completion criteria

- The wheel exposes only the `chemvas` top-level package.
- No eager production import cycles exist.
- `domain` has no Qt/RDKit/UI dependencies.
- Transaction capture, commit, rollback, and recovery policy have one owner.
- Feature internals are not imported across feature boundaries.
- Ruff lint/format, mypy, process-isolated tests, RDKit smoke tests, and wheel
  smoke tests pass.
