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

> **Give each test file its own pytest process.** Qt keeps global application
> state that does not fully reset between test modules, so a single shared
> process passes tests that CI would fail. `scripts/run_test_files.sh` is the one
> place that rule lives: `make check` and both CI jobs call it, and it runs
> several of those processes at once — concurrency between processes, never two
> files in one. To narrow the run to the files you touched, pass them to the
> gate directly:
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

The rules themselves are normative in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the ports / access / state /
service discipline for the flat `app/chemvas/ui` package, what `core` may
import, and how transaction and recovery ownership is divided (Korean mirror:
[`docs/ARCHITECTURE.ko.md`](docs/ARCHITECTURE.ko.md)). The target package
boundaries and dependency direction are decided in
[`ADR 0001`](docs/adr/0001-feature-oriented-modularization.md). Read both before
moving code; what follows is the contributor's-eye view.

**Those boundaries are enforced by
[`tests/test_architecture_boundaries.py`](tests/test_architecture_boundaries.py)
and [`tests/test_package_dependencies.py`](tests/test_package_dependencies.py).**
They scan the source with AST + regex and fail if a forbidden pattern reappears.
If you try to "simplify" by collapsing these modules or reaching into internals,
they will tell you no.

### The module roles, by example

Using the atom-label feature as a worked example:

| Suffix | Role | Example |
| --- | --- | --- |
| `*_ports` | The single canonical way to resolve a service/collaborator from a canvas or window. | [`canvas_service_ports.py`](app/chemvas/ui/canvas_service_ports.py): `atom_label_service_for_access(canvas)` → `canvas_services_for(canvas).atom_label_service` |
| `*_access` | Caller-facing free functions. Other modules call these instead of touching attributes. | [`atom_label_access.py`](app/chemvas/ui/atom_label_access.py): `add_or_update_atom_label(canvas, atom_id, text)` |
| `*_service` | The actual implementation/logic. Receives its collaborators as **injected ports**. | `atom_label_service.py` |
| `*_state` | Owns runtime state in a dedicated object instead of as private attrs on the window/canvas. | `main_window_state.py` (`MainWindowState`) |
| `*_logic` | Pure, Qt-free helpers (parsing, geometry, layout) that are easy to unit-test. | `chemvas.features.annotations` label layout API |
| `*_controller` | A coordinator class (`FooController` in `foo_controller.py`) that owns the interaction flow for one area of the canvas or window, holding the canvas plus injected collaborators. One deliberate exception lives elsewhere: `HoverController` in `ui/hover.py` owns Qt hover orchestration next to the hover feature seam (see `docs/ARCHITECTURE.md`). | `scene_delete_controller.py` (`SceneDeleteController`) |
| `*_tool` / `*_tools` | Implementations of the pointer-tool hierarchy rooted at `chemvas.ui.tool_base.Tool`. Every implementation of that hierarchy lives in a `*_tool.py` (one tool) or `*_tools.py` (a family, possibly with an intermediate base as in `preview_tools.py`) module. | `bond_tool.py` (`BondTool`) |
| `*_bundle` | A dataclass that groups services constructed together and stored or passed as one field, usually next to its `build_*` factory. | `canvas_input_service_bundle.py` (`CanvasInputServiceBundle`) |
| `*_renderer` / `*_rendering` | Qt painting and graphics-item drawing helpers: a renderer class, or a module of drawing functions. | `bond_renderer.py`, `hover_rendering.py` |

The first five rows are the injected-port discipline; the boundary tests
enforce much of it (the Qt-free `*_logic` rule is checked per module, not by
a repo-wide gate). The last four rows document the vocabulary the codebase
already uses consistently — keep new modules consistent with it, but no
automated gate checks those suffixes.

A focused test that needs only part of the runtime builds that part rather than
hanging state or services off a double by hand:

```python
canvas = SimpleNamespace(
    runtime_state=canvas_runtime_state(graph_state=CanvasGraphState()),
)
```

`tests/runtime_state.canvas_runtime_state(**states)` checks the field names
against the real `CanvasRuntimeState`, and `tests/runtime_services.py` does the
same for a partial `CanvasRuntimeServices`.

### What the boundary tests will stop you doing

- **No reaching into private members.** Don't write `canvas._foo`,
  `getattr(canvas, "_foo")`, or `setattr(canvas, "_foo", ...)` from production code.
- **Go through accessors, not state attributes.** Don't read canvas state like
  `canvas.hover_atom_id`, `canvas.atom_items`, `canvas.active_bond_order`, etc.
  directly — use the corresponding `*_access` helper.
- **Services take injected ports.** A service must not reach through `window.canvas`,
  `window.services`, or `window.canvas_tabs`. Collaborators are passed in (look at how
  `chemvas.bootstrap.main_window_services` wires them) so each service is testable in isolation.
- **`window.canvas` / `window.canvas_tabs` stay off the shell surface.** Outside
  `app/chemvas/shell/main_window.py`, use the canvas/tab reference ports.
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

## Pull requests

- Keep PRs focused; one logical change per PR.
- Make sure `ruff`, `mypy`, and the affected tests pass locally.
- Add or update tests for behavior changes.
- Describe what changed, why, and how you verified it; link any related issue.
  The PR template's `Motivation` / `Changes` / `Verification` sections are there
  for exactly that.
- Update `CHANGELOG.md` under `## [Unreleased]` when your change is user-visible.

## Reporting bugs & requesting features

Use the GitHub issue templates. For bugs, include your OS, Python version, whether
RDKit is installed, and steps to reproduce. For a drawing glitch, a screenshot or a
small `.chemvas` file helps a lot.
