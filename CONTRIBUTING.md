# Contributing to Chemvas

Thanks for your interest in Chemvas! This guide covers local setup, how to run the
checks, and — most importantly — the **architecture conventions** the codebase
follows. Please read the architecture section before moving code around: the module
layout is deliberate and enforced by a test, so a well-meant "cleanup" will fail CI.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

Requires **Python 3.13+**.

```bash
git clone https://github.com/dhsohn/Chemvas.git
cd Chemvas
python -m venv .venv && source .venv/bin/activate   # optional but recommended
python -m pip install -e ".[dev]"                    # dev tooling
python -m pip install -e ".[dev,rdkit]"              # also enable RDKit features
```

Run the app from the development tree:

```bash
python app/main.py
```

## Running the checks

CI runs three gates; run the same ones locally before opening a PR.

```bash
python -m ruff check .     # lint + import sorting
python -m mypy             # type check (covers app/core and app/ui)
```

Tests use PyQt6 and run headlessly via the `offscreen` platform plugin. During
development, run the file(s) you touched:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_<area>.py
```

> **Run the suite one file at a time.** Qt keeps global application state that does
> not fully reset between test modules, so CI runs each `test_*.py` file in its own
> pytest process. To mirror CI locally:
>
> ```bash
> QT_QPA_PLATFORM=offscreen bash -c '
>   for f in $(find tests -maxdepth 1 -name "test_*.py" | sort); do
>     python -m pytest "$f" || exit 1
>   done
> '
> ```

New behavior should come with a test. Most modules have a matching
`tests/test_<module>.py`.

## Architecture conventions (read this before restructuring)

Chemvas's `app/ui` layer is split into **many small, single-purpose modules** with
suffixes like `*_ports`, `*_access`, `*_state`, `*_service`, `*_controller`, and
`*_logic`. This is **intentional**, not accumulated cruft. The goal is to keep
`CanvasView` and `MainWindow` from becoming god objects: state lives in dedicated
state objects, behavior lives in services, and everything is reached through
explicit accessor functions rather than by poking attributes.

**These boundaries are enforced by [`tests/test_architecture_boundaries.py`](tests/test_architecture_boundaries.py).**
It scans the source with AST + regex and fails if forbidden patterns reappear. If
you try to "simplify" by collapsing these modules or reaching into internals, that
test will tell you no.

### The module roles

Using the atom-label feature as a worked example:

| Suffix | Role | Example |
| --- | --- | --- |
| `*_ports` | The single canonical way to resolve a service/collaborator from a canvas or window. | [`atom_label_ports.py`](app/ui/atom_label_ports.py): `atom_label_service_for_access(canvas)` → `canvas_services_for(canvas).atom_label_service` |
| `*_access` | Caller-facing free functions. Other modules call these instead of touching attributes. | [`atom_label_access.py`](app/ui/atom_label_access.py): `add_or_update_atom_label(canvas, atom_id, text)` |
| `*_service` | The actual implementation/logic. Receives its collaborators as **injected ports**. | `atom_label_service.py` |
| `*_state` | Owns runtime state in a dedicated object instead of as private attrs on the window/canvas. | `main_window_state.py` (`MainWindowState`) |
| `*_logic` | Pure, Qt-free helpers (parsing, geometry, layout) that are easy to unit-test. | `label_layout_logic.py` |

### The rules the boundary test enforces

- **No reaching into private members.** Don't write `canvas._foo`,
  `getattr(canvas, "_foo")`, or `setattr(canvas, "_foo", ...)` from production code.
- **Go through accessors, not state attributes.** Don't read canvas state like
  `canvas.hover_atom_id`, `canvas.atom_items`, `canvas.active_bond_order`, etc.
  directly — use the corresponding `*_access` helper.
- **Services take injected ports.** A service must not reach through `window.canvas`,
  `window.services`, or `window.canvas_tabs`. Collaborators are passed in (look at how
  `main_window_services.py` wires them) so each service is testable in isolation.
- **`window.canvas` / `window.canvas_tabs` are private to `main_window.py`.** Outside
  that file, use the canvas/tab reference ports.
- **Removed facades stay removed.** The boundary test lists many old god-object method
  names (e.g. `set_bond_style`, `export_figure`, `bind_active_canvas`) that must not be
  reintroduced on `MainWindow`. Add behavior to the appropriate service instead.

### Adding a feature, the Chemvas way

1. Put pure logic in a `*_logic.py` module with unit tests — no Qt imports.
2. Put behavior that touches the scene/model in a `*_service.py`, taking its
   collaborators as constructor arguments.
3. If callers need to reach it, expose a `*_access.py` function (and a `*_ports.py`
   resolver if it hangs off the canvas/window service bundle).
4. Wire it once in the relevant `*_services.py` / `*_bundle.py`.
5. Run `tests/test_architecture_boundaries.py` — if it fails, you've crossed a
   boundary; follow the assertion message rather than working around it.

When in doubt, copy the shape of an existing nearby cluster (the atom-label or
selection clusters are good references).

### Core vs UI

- `app/core/` is Qt-free chemistry/model/IO logic (`model.py`, `history.py`,
  `renderer.py`, `rdkit_adapter.py`, `document_io.py`, …). Keep it free of PyQt
  imports so it stays unit-testable.
- `app/ui/` is the PyQt6 layer described above.
- **RDKit is optional.** It must never become a hard import at app startup. Features
  that need it should degrade gracefully (or fail with a clear message) when it's
  absent — see `rdkit_adapter.py`.

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
