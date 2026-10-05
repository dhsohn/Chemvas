# ADR 0035: Retire the RDKit chemistry provider

- Status: Accepted
- Date: 2026-10-05
- Recorded: 2026-10-05
- Supersedes: [ADR 0019](0019-reaction-pair-handoff-and-opaque-endpoint-archives.md), [ADR 0031](0031-standalone-contract-validation.md)
- Partly supersedes: [ADR 0029](0029-browser-adapter.md), [ADR 0034](0034-qt-only-distribution.md)

## Problem

Chemvas 0.24.0 shipped optional RDKit editing: SMILES insertion, Molecule Info,
a 3D preview, 3D XYZ export, reaction mapping, and a calculation handoff that
wrote `machine.json`. ADR 0031 kept the observation schemas for that handoff in
`contracts/machine-observation/`. ADR 0034 kept optional RDKit data in the
frozen bundle. The user guides that shipped with that removal still told
people to install a chemistry extra and to run the handoff commands.

The removal itself is commit `932c0607e16e9192f69625bc430a3a628a3961af` on
`handoff/grok-chemvas-20261005` (parent `04ed9e26fbb848268026cc1ea21987032d8616ef`).
That commit did not add this record. Its message left documentation, provider
adoption, and release acceptance pending.

## Decision

1. **No chemistry backend.** Chemvas does not depend on RDKit. There is no
   `rdkit` extra. SMILES insertion, Molecule Info, the 3D preview, 3D XYZ
   export, reaction mapping, and calculation handoff commands are not product
   features. Abbreviation labels stay as drawn labels. MOL export does not
   expand them.

2. **No observation provider.** Chemvas does not write `machine.json` and does
   not ship `contracts/machine-observation/`. `make check` does not validate
   that snapshot. This repository does not record a replacement provider, a
   core version, or an execution approval for any other project.

3. **What remains.** Native drawing, history, figure and CDXML export, the
   headless document commands, and the V2000 MOL subset remain. A legacy
   calculation plan already stored in a document is still read. Save refuses
   when keeping the drawing would drop that plan. The experimental browser
   adapter stays a source-checkout surface for later Leaf integration, as ADR
   0034 decided, and is not a chemistry provider or a web product release.

4. **Version.** The unreleased candidate is `0.25.0.dev0`. Publishing a release
   is a separate step: it requires a numeric `major.minor.patch` version,
   because the Windows bundle spec rejects any other form, and it is not part
   of this decision.

## Verification and limits

- The removal commit records a macOS `make check` of that source, without
  RDKit: 16,434 tests and 994 subtests passed, 29 platform or interpreter
  skips, 95.69% line coverage and 88.53% branch coverage. It also records
  Cocoa checks of drawing, Undo/Redo, save/reopen, CDXML, legacy plan
  preservation, and refused overwrite. Those results belong to that commit.
  They are not evidence for later documentation edits, and this record does
  not re-run them.
- This ADR does not claim a new canvas recording. Guides that still showed
  the removed features were corrected in text against the current commands
  and modules. The old chemistry walkthrough image is not current product
  evidence.
- Downstream projects that pinned an earlier Chemvas provider are unchanged
  by this file. Adoption, if any, is their decision.
