# Contributing to Chemvas

Thanks for your interest in Chemvas! This guide covers local setup, how to run the
checks, and — most importantly — the **architecture conventions** the codebase
follows. Please read the architecture section before moving code around: the module
layout is deliberate and enforced by a test, so a well-meant "cleanup" will fail CI.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

Requires **Python 3.12+**.

```bash
git clone https://github.com/dhsohn/Chemvas.git
cd Chemvas
python -m venv .venv && source .venv/bin/activate   # optional but recommended
python -m pip install -e ".[dev]"                    # dev tooling
python -m pip install -e ".[dev,rdkit]"              # also enable RDKit features
```

The shared `machine.json` contract validator is a second development checkout
used by `make check`:

```bash
git clone https://github.com/dhsohn/machine-contracts.git ~/machine_contracts
```

Set `FACTORY_MACHINE_CONTRACT_REPO` if that checkout lives elsewhere. `make
check` uses an activated virtual environment first, then the repository's
`.venv`, and finally `python3`; set `PYTHON_BIN` to choose an interpreter
explicitly.

Run the app from the development tree:

```bash
python app/main.py
```

## Running the checks

One command runs the primary local gate — lint, formatting, mypy, the full test
suite, and the `machine.json` conformance check — before opening a PR:

```bash
make check
```

The individual gates, for reference:

```bash
python -m ruff check .     # lint + import sorting
python -m ruff format --check .  # deterministic formatting
python -m mypy             # all production code; migrated owner packages are strict
```

Tests use PyQt6 and run headlessly via the `offscreen` platform plugin. During
development, run the file(s) you touched:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_<area>.py
```

> **Run the suite one file at a time.** Qt keeps global application state that does
> not fully reset between test modules, so CI runs each `test_*.py` file in its own
> pytest process. `make check` does the same; to narrow the loop to the files you
> touched, pass them to the script directly:
>
> ```bash
> bash scripts/check.sh tests/test_<area>.py
> ```

New behavior should come with a test. Most modules have a matching
`tests/test_<module>.py`.

Keep each test module single-style. When extending an existing module, follow
that file's current `unittest` or plain-pytest style. New standalone test modules
use plain pytest functions. Do not convert unrelated tests solely to change
style.

CI additionally runs the optional-RDKit smoke and wheel packaging smoke. Those
two environment-specific jobs are not part of `make check`.

## Architecture conventions (read this before restructuring)

Chemvas is migrating from the flat `app/chemvas/core` and `app/chemvas/ui`
packages to the feature-oriented boundaries in
[`ADR 0001`](docs/adr/0001-feature-oriented-modularization.md). Existing UI code
still uses small `*_ports`, `*_access`, `*_state`, `*_service`,
`*_controller`, and `*_logic` modules to keep `CanvasView` and `MainWindow`
thin. Treat that convention as a constraint for legacy code, not as a template
that every new feature must reproduce.

**These boundaries are enforced by [`tests/test_architecture_boundaries.py`](tests/test_architecture_boundaries.py).**
It scans the source with AST + regex and fails if forbidden patterns reappear. If
you try to "simplify" by collapsing these modules or reaching into internals, that
test will tell you no.

### The module roles

Using the atom-label feature as a worked example:

| Suffix | Role | Example |
| --- | --- | --- |
| `*_ports` | The single canonical way to resolve a service/collaborator from a canvas or window. | [`canvas_service_ports.py`](app/chemvas/ui/canvas_service_ports.py): `atom_label_service_for_access(canvas)` → `canvas_services_for(canvas).atom_label_service` |
| `*_access` | Caller-facing free functions. Other modules call these instead of touching attributes. | [`atom_label_access.py`](app/chemvas/ui/atom_label_access.py): `add_or_update_atom_label(canvas, atom_id, text)` |
| `*_service` | The actual implementation/logic. Receives its collaborators as **injected ports**. | `atom_label_service.py` |
| `*_state` | Owns runtime state in a dedicated object instead of as private attrs on the window/canvas. | `main_window_state.py` (`MainWindowState`) |
| `*_logic` | Pure, Qt-free helpers (parsing, geometry, layout) that are easy to unit-test. | `chemvas.features.annotations` label layout API |

### The rules the boundary test enforces

- **No reaching into private members.** Don't write `canvas._foo`,
  `getattr(canvas, "_foo")`, or `setattr(canvas, "_foo", ...)` from production code.
- **Go through accessors, not state attributes.** Don't read canvas state like
  `canvas.hover_atom_id`, `canvas.atom_items`, `canvas.active_bond_order`, etc.
  directly — use the corresponding `*_access` helper.
- **Services take injected ports.** A service must not reach through `window.canvas`,
  `window.services`, or `window.canvas_tabs`. Collaborators are passed in (look at how
  `chemvas.bootstrap.main_window_services` wires them) so each service is testable in isolation.
- **`window.canvas` / `window.canvas_tabs` stay off the shell surface.** Outside
  that file, use the canvas/tab reference ports.
- **Removed facades stay removed.** The boundary test lists many old god-object method
  names (e.g. `set_bond_style`, `export_figure`, `bind_active_canvas`) that must not be
  reintroduced on `MainWindow`. Add behavior to the appropriate service instead.

### Adding or migrating a feature

1. Put Qt-free domain rules in `chemvas.domain` and feature orchestration in a
   package under `chemvas.features`.
2. Define small feature-owned protocols for storage, RDKit, or Qt integration;
   concrete implementations live under `chemvas.adapters`.
3. Expose cross-feature behavior from the feature package public API. Do not
   import another feature's internal module.
4. Create `state.py`, `ports.py`, `service.py`, or `qt.py` only when that role is
   a real boundary; one operation does not require a wrapper chain by default.
5. Wire concrete adapters in `chemvas.bootstrap` and keep the application shell
   under `chemvas.shell`.
6. Run both `tests/test_package_dependencies.py` and
   `tests/test_architecture_boundaries.py`.

When migrating legacy code, preserve its existing access rules until the whole
feature owns a public API and the corresponding legacy architecture checks can
be retired.

Production service lookup accepts only `CanvasRuntimeServices`; it does not adapt
flat or duck-typed service bags. Focused legacy UI tests use the test-only builder
in `tests/runtime_services.py` when they need a partial runtime.

State works the same way. A `<name>_state_for(canvas)` accessor reads its field off
`canvas.runtime_state` and does not create state on the canvas on first access.
`SheetSetupState` is the sole owner of sheet size, orientation, and rect; those values
are not mirrored onto the canvas. One hold-out, `document_metadata_state_for`, still
goes through the older `canvas_state_object` path and may attach;
`NON_RUNTIME_STATE_ACCESSORS` in the boundary test records it. A double therefore
needs its own partial container —
build it with `tests/runtime_state.canvas_runtime_state(**states)`, which checks the
names against the real `CanvasRuntimeState`:

```python
canvas = SimpleNamespace(
    runtime_state=canvas_runtime_state(graph_state=CanvasGraphState()),
)
```

### Core vs UI

- `app/chemvas/core/` is transitional chemistry/model/IO code. It must not import
  the UI or Qt. Concrete renderer integration belongs in `chemvas.adapters.qt`;
  do not add framework dependencies to core.
- `app/chemvas/ui/` is the PyQt6 layer described above.
- `app/chemvas/shell/main_window.py` owns the thin Qt window; runtime/service
  assembly, document opening, and startup live in `app/chemvas/bootstrap/`.
- **RDKit is optional.** It must never become a hard import at app startup. Features
  that need it should degrade gracefully (or fail with a clear message) when it's
  absent — see `chemvas.core.rdkit_adapter` (recorded transitional adapter debt).

## Pull requests

- Keep PRs focused; one logical change per PR.
- Make sure `ruff`, `mypy`, and the affected tests pass locally.
- Add or update tests for behavior changes.
- Describe what changed and why; link any related issue.
- Update `CHANGELOG.md` under `## [Unreleased]` when your change is user-visible.

## Reporting bugs & requesting features

Use the GitHub issue templates. For bugs, include your OS, Python version, whether
RDKit is installed, and steps to reproduce. For a drawing glitch, a screenshot or a
small `.chemvas` file helps a lot.
