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

The current rules are recorded in [ADR 0005](docs/adr/0005-responsibility-based-editor-boundaries.md). [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) describes the implementation and its boundaries.

### Organize around responsibilities

- Maintain cohesion within feature workflows. Split a module only when justified by a distinct responsibility, dependency boundary, or reusable implementation. Do not mechanically introduce `state`, `access`, `ports`, `service`, or `bundle` layers.
- Pass canvas-scoped collaborators directly and call their methods. Controllers and tools may use their owned public state and Qt APIs directly. Use accessors or protocols only for concrete boundaries—such as resolving the active document, converting representations, or restricting operations. Do not create wrapper layers solely for forwarding.
- Maintain a single owner for each state and mutation rule. Other modules interact via the owner's public operations; do not duplicate state, access private members, or bypass transactions, invalidation, or lifecycle management.
- Resolve dynamic dependencies (e.g., active documents, replaceable models) at invocation time; do not retain references beyond their lifecycle.
- Keep document data models, validation, and chemistry rules Qt-free in `domain` and `core`. Desktop interaction and rendering implementations (`ui`, `shell`, `adapters`, desktop feature modules) may use Qt and concrete adapters directly. Preserve headless feature API contracts and optional RDKit behavior.
- Use public APIs across package boundaries and keep eager imports acyclic.

### Review and test boundaries

When proposing structural changes, identify the migrating responsibility, the resulting owner, and eliminated indirection paths. Aim to minimize the indirection and cognitive load required to understand a feature.

Architectural tests verify dependency direction, single state ownership, and recovery guarantees. They do not enforce static inventories of forwarding helpers or accessors for every field. When refactoring responsibilities, update structural tests alongside implementation while preserving behavioral tests. New boundary tests must verify both compliant cases and violation rejections.

Editing changes must preserve the affected user workflows, including cancellation, Undo/Redo, recovery from failed edits, and document persistence. Preserve behavioral workflow tests even when removing wiring-only assertions. The checks live in [`tests/test_architecture_boundaries.py`](tests/test_architecture_boundaries.py), [`tests/test_package_dependencies.py`](tests/test_package_dependencies.py), and the relevant workflow tests.

## Pull Requests

- Keep PRs focused on a single logical change.
- Verify that `make check` passes cleanly.
- Add regression tests for any new behavior or bug fix.
- Follow the PR template and clearly explain the motivation, changes, and verification steps.
- Update `CHANGELOG.md` under `## [Unreleased]` for user-visible changes.

## Bug Reports & Feature Requests

Please use our GitHub Issue templates. When reporting bugs, specify your OS, Python version, whether RDKit is installed, and reproducible steps.
