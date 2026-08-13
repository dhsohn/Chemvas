## Motivation

<!-- The problem this change exists to solve, and how you found it. -->

## Changes

<!-- What changed. Describe the behavior, and tie each change back to the motivation. -->

## Verification

<!-- The commands you ran and what you observed. Say what you could not check, and any risk you are leaving in place. -->

## Related issue

<!-- e.g. Closes #123 -->

## Checklist

- [ ] `python -m ruff check .` passes
- [ ] `python -m mypy` passes
- [ ] Affected tests pass (`QT_QPA_PLATFORM=offscreen python -m pytest tests/test_<area>.py`)
- [ ] Added/updated tests for the change
- [ ] Did not cross an architecture boundary (`tests/test_architecture_boundaries.py` still passes) — see [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] Updated `CHANGELOG.md` (under `Unreleased`) if user-visible
- [ ] Updated docs/README if behavior or usage changed

## Notes for reviewers

<!-- Anything you want a reviewer to look at closely, screenshots for UI changes, etc. -->
