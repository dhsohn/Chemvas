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
