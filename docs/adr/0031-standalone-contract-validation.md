# ADR 0031: Standalone contract validation

- Status: Superseded by [ADR 0035](0035-retire-rdkit-chemistry-provider.md)
- Date: 2026-10-03

## Problem

Building and testing Chemvas required cloning the external `machine-contracts`
repository into `~/machine_contracts` (or setting `FACTORY_MACHINE_CONTRACT_REPO`),
and CI checked out that repository at a pinned SHA in every job that ran
contract-validating tests. A fresh clone or worktree could not run `make check`
without this prerequisite, and CI depended on a second-repository checkout for
every pull request and push.

The coupling points were:

- `scripts/check.sh` lines 170-177: failed when the external clone was absent.
- `.github/workflows/ci.yml`: two jobs checked out `dhsohn/machine-contracts`.
- `.github/workflows/platform.yml`: set `FACTORY_MACHINE_CONTRACT_REPO` at the
  gate step.
- `tests/calculation_workflow_support.py`: read `FACTORY_MACHINE_CONTRACT_VALIDATOR`
  and failed when unset.
- `CONTRIBUTING.md` / `CONTRIBUTING.ko.md`: documented the clone as a mandatory
  setup step.

## Decision

The contract assets required for Chemvas validation are copied into the
repository as a project-local snapshot under `contracts/machine-observation/`.

The snapshot is scoped to the `chemvas` producer: it carries the envelope schema,
the two `chemistry/elementary-step` payload schemas (v1 and v2), the semantic
validator (exact copy), and a project-scoped derivative of the registry
containing only chemvas routes. Routes and schemas for other producers are
excluded.

Provenance is recorded in `contracts/machine-observation/NOTICE.md` with the
upstream repository URL, the pinned commit SHA
(`38581a7737cd0521bb3d50b59115eefe3c9254ca`), and a file-level mapping between
local and upstream paths. The upstream MIT license is included verbatim.

The gate, CI, and test helper now resolve the validator from the project-local
path unconditionally. No environment variable, external clone, or CI checkout
of `machine-contracts` is required.

Contract changes are owned by this project's maintainers; upstream landing is
not a prerequisite. Local changes must record provenance and type, include
schema/semantic regression coverage, and follow ADR/versioning for public
contract surface changes. Syncing a newer upstream pin is an optional
compatibility path: copy the updated files, then update `NOTICE.md` (commit
SHA), `PROVENANCE.json` (per-file SHA-256 digests), and
`PIN_HASHES`/`REGISTRY_HASH` in `tests/test_contract_compatibility.py`,
preserving original schema/semantic compatibility and full source-pin
provenance for unchanged copied files.

## Verification and limits

- The focused gate (Ruff/format/mypy and tests) passes in a fresh checkout
  with no `~/machine_contracts` directory and no `FACTORY_MACHINE_CONTRACT_REPO`
  environment variable. Full gate and CI have not yet been verified at the time
  of this ADR.
- `tests/test_contract_compatibility.py` validates all chemvas reference
  fixtures against the local validator, tests schema/route rejection semantics,
  duplicate-key rejection, machine-path artifact verification, delivery
  consistency semantics, and proves the validator runs standalone without
  external paths. Per-file SHA-256 digests anchored to the pin commit are
  asserted against `PROVENANCE.json`.
- `tests/test_check_entrypoint.py` verifies the gate finds the local validator
  without `FACTORY_MACHINE_CONTRACT_REPO`.
- The project-scoped registry validates chemvas observations identically to the
  full upstream registry for all chemvas routes and rejects unregistered
  producers. Error message text may differ from upstream (e.g. "payload contract
  is not registered" locally vs. "producer, operation, and payload route is not
  registered" upstream for a payload name registered only upstream); verdict
  equivalence holds, but message text is not frozen.
- Interior objects in the payload schemas remain open for producer-side growth
  without a contract update, matching upstream COMPATIBILITY.md.
- This decision does not cover automated upstream drift detection: comparing the
  local snapshot against a newer upstream commit is a manual step.
