# Contributing to Chemvas

[한국어](CONTRIBUTING.ko.md)

Thank you for your interest in Chemvas! This guide covers setting up your development environment, running verification tests, and understanding our architectural conventions.

Please review our architecture guidelines before modifying modules: package boundaries are strictly enforced by automated tests.

All contributors are expected to adhere to our [Code of Conduct](CODE_OF_CONDUCT.md).

## Development Setup

Requires **Python 3.12+**.

Chemvas can be developed and verified on macOS, Linux, and Windows (native or WSL).

```bash
git clone https://github.com/dhsohn/Chemvas.git
cd Chemvas
python -m venv .venv && source .venv/bin/activate   # optional but recommended
python -m pip install -e ".[dev]"                    # dev tooling
python -m pip install -e ".[dev,rdkit]"              # also enable RDKit features
```

The shared `machine.json` contract validator is required for full validation:

```bash
git clone https://github.com/dhsohn/machine-contracts.git ~/machine_contracts
```

If cloned to a custom location, set `FACTORY_MACHINE_CONTRACT_REPO` to point to that directory.

Launch the app from source:

```bash
python app/main.py
```

## Running Checks

Run the complete local validation gate (lint, formatting, mypy, test suite, and contract validation) before submitting a PR:

```bash
make check
```

Individual checks can be run manually:

```bash
python -m ruff check .     # lint + import sorting
python -m ruff format --check .  # deterministic formatting
python -m mypy             # all production code; migrated owner packages are strict
```

To run only the tests related to your changes:

```bash
bash scripts/check.sh tests/test_<area>.py
```

> **Process Isolation**: Qt maintains global application state that does not fully reset between test modules. Always run tests using `scripts/check.sh` or `scripts/run_test_files.sh`, which isolates each test file in its own process:
>
> ```bash
> bash scripts/check.sh tests/test_<area>.py
> ```

## Architecture Conventions

The architecture rules are detailed in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (Korean: [`docs/ARCHITECTURE.ko.md`](docs/ARCHITECTURE.ko.md)) and [`ADR 0001`](docs/adr/0001-feature-oriented-modularization.md).

Package boundaries are enforced by [`tests/test_architecture_boundaries.py`](tests/test_architecture_boundaries.py) and [`tests/test_package_dependencies.py`](tests/test_package_dependencies.py).

### Module Roles and Suffixes

| Suffix | Role | Example |
| --- | --- | --- |
| `*_ports` | Canonical way to resolve collaborators/services from a canvas or window | [`canvas_service_ports.py`](app/chemvas/ui/canvas_service_ports.py) |
| `*_access` | Caller-facing free functions; modules call these instead of accessing state attributes | [`atom_label_access.py`](app/chemvas/ui/atom_label_access.py) |
| `*_service` | Business logic implementation; receives collaborators via injected ports | `atom_label_service.py` |
| `*_state` | Runtime state dataclass; avoids storing loose attributes on UI widgets | `main_window_state.py` |
| `*_logic` | Pure, Qt-free helper functions (parsing, geometry, math) | `chemvas.features.annotations` |
| `*_controller` | Interaction coordinator for a specific functional area | `scene_delete_controller.py` |
| `*_tool` | Canvas tool implementation inheriting from `chemvas.ui.tool_base.Tool` | `bond_tool.py` |
| `*_bundle` | Dataclass grouping related services constructed together | `canvas_input_service_bundle.py` |
| `*_renderer` | Qt painting and graphics-item drawing helpers | `bond_renderer.py` |

For testing components in isolation, construct only the required state slices:

```python
canvas = SimpleNamespace(
    runtime_state=canvas_runtime_state(graph_state=CanvasGraphState()),
)
```

### Key Architectural Constraints

- **No Private Attribute Access**: Do not access `canvas._foo` or use dynamic attribute access on internal members.
- **Use Accessors**: Read canvas state via `*_access` helpers rather than directly accessing attributes.
- **Dependency Injection**: Services receive collaborators explicitly via constructor arguments or ports rather than reaching through global singletons.
- **Feature Packages**: Place pure chemistry domain logic in `chemvas.domain` and user-facing feature orchestration in `chemvas.features`.

## Pull Requests

- Keep PRs focused on a single logical change.
- Verify that `make check` passes cleanly.
- Add regression tests for any new behavior or bug fix.
- Follow the PR template and clearly explain the motivation, changes, and verification steps.
- Update `CHANGELOG.md` under `## [Unreleased]` for user-visible changes.

## Bug Reports & Feature Requests

Please use our GitHub Issue templates. When reporting bugs, specify your OS, Python version, whether RDKit is installed, and reproducible steps.
