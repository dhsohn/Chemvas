# ADR 0061: Run platform validation locally

- Status: Accepted
- Date: 2026-10-22

## Context

The user requested removal of all GitHub OS test suites because their duration
made iteration and release impractical.

## Decision

Remove the Linux Python test matrix and the separate macOS and Windows workflows.
Retain GitHub quality (Ruff, formatting and mypy), wheel smoke and secret scanning.
Keep full local `make check`, isolated test processes, coverage collection and
host-native interaction tests. Release preparation records local validation;
GitHub platform suites are no longer release gates. Required-check configuration
must replace obsolete test contexts with `quality` when this workflow is deployed.

## Verification and limits

The CI contract test rejects reintroduced matrix/suite jobs and missing quick
checks; documentation tests verify matching contributor instructions. Local
validation on one host does not prove untested operating systems work. This is
an explicitly accepted reduction in automated cross-platform coverage, not a
removal of supported platforms or their local tests.
