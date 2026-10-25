# Desktop release acceptance

This policy defines what must be true before the first public stable Chemvas
desktop release ships. Accepting it does not mean any platform is ready; release
completion is recorded only in the receipt at the end. Release mechanics:
[RELEASING.md](../RELEASING.md). Document format guarantees:
[DOCUMENT_COMPATIBILITY.md](DOCUMENT_COMPATIBILITY.md). Korean:
[RELEASE_ACCEPTANCE.ko.md](RELEASE_ACCEPTANCE.ko.md).

## Target matrix

| Row | Platform | Architecture | Package |
| --- | --- | --- | --- |
| W1 | Windows 11 25H2 | native x64 | Per-user Inno Setup EXE with GUI and CLI |
| W2 | Windows 11 26H2 | native x64 | Per-user Inno Setup EXE with GUI and CLI |
| M1 | macOS 26 | Apple Silicon arm64 | Standalone `Chemvas.app` in a DMG |
| L1 | Ubuntu 24.04 LTS, GNOME on Wayland | x86_64 | Standalone tar.gz, per-user launcher, desktop and MIME integration |
| L2 | Ubuntu 24.04 LTS, GNOME on X11 | x86_64 | Same package as L1 |

Every package bundles Python; OS system runtime libraries may have documented
prerequisites. All binary artifacts are planned deliverables, and this document
certifies none of them. Unchanged: the existing 0.27.1 PyPI install stays
available, the Python requirement stays `>=3.12`, and no product runtime minimum
changes.

Intel Macs, Windows on ARM, Linux on ARM, and other OS or distribution versions
are not certified, but they are not actively blocked. If a row cannot pass, the
release waits or a scope change is decided and published. Scope is never reduced
silently.

## Rules for every row

- The same acceptance applies to every row. W1 and W2 pass separately, as do L1
  and L2; one passing does not imply the other.
- Record the exact OS build or point release, CPU, display backend, Python, PyQt,
  Qt, Pillow and PyInstaller versions, fonts, candidate git SHA, and artifact SHA256.
- Freeze the candidate identity before testing. Any app change invalidates the
  evidence it affects, and that evidence is rerun.
- A check passes only after it ran on the frozen candidate. The published artifact
  hash must match the tested artifact hash.

## Evidence stages

The stages are kept separate so that no gate depends on its own outcome.

1. **Source tests** run on the candidate git SHA. They prove source behavior, not
   that a frozen package installs or runs.
2. **Candidate acceptance** runs before public release on the built artifacts,
   obtained through a controlled, unannounced download and verified by SHA256.
   Every per-row gate below belongs to this stage.
3. **Public download smoke check** runs after publication on the final public
   downloads. It confirms each published SHA256 matches the accepted artifact and
   that the app installs and launches. A failure is published and handled through
   [RELEASING.md](../RELEASING.md); it never substitutes for candidate acceptance.

## Dependency order

1. Freeze the candidate git SHA and dependency versions.
2. Source tests.
3. Build the artifacts and record their SHA256.
4. Per-platform signing and notarization (accounts may be an external dependency).
5. Candidate acceptance per row: clean install, fixtures, safety, manuscript output.
6. Third-party inventory, notice, and redistribution review of the actual bundle.
7. Ship decision; publish exactly the accepted artifacts.
8. Public download smoke check and public report.

## Source tests

- Run `make check` locally on each native OS (Windows via Git Bash) over the full test suite and record
  line and branch coverage separately. This does not require 100% coverage.
- CI keeps the quality, package-smoke, and secret-scan jobs; no new OS CI is added.
- Headless or WSL runs do not prove the native GUI.

## Signing and OS protection

- Windows (W1, W2): sign the installer; record warning and signature behavior.
- macOS (M1): sign and notarize; record quarantine, signing, and notarization
  behavior for a downloaded DMG.
- Linux (L1, L2): no notarization; users verify the published SHA256.
- Resolve each behavior with a documented, supported install flow. Instructions
  never ask users to disable OS security protections.
- A row waiting on signing or notarization accounts stays pending.

## Clean install

Use a fresh user account or VM with no separately installed Python, no source
checkout, and no developer PATH entries.

1. Get the artifact through the controlled download and verify its SHA256.
2. Install it and launch Chemvas from the normal OS entry point.
3. Open a document through the file association, including a path with Unicode
   characters and spaces.
4. In the GUI: edit, undo, redo, save, quit, reopen, export.
5. Update over an earlier build; documents and settings are retained.
6. Uninstall; user documents remain and only Chemvas-owned integration is removed.

## Fixtures

Five public synthetic fixtures, their commands, and the expected-result oracle
are in [../examples/release-validation/README.md](../examples/release-validation/README.md).

| Fixture | Expected content |
| --- | --- |
| `01-basic.cdxml` | Basic arrow with an MnO2 label using a subscript |
| `02-reactants.cdxml` | Three structures, a plus connector, separate captions 1, 2, 3 |
| `03-notation.cdxml` | Charges, wedge and hash bonds, superscript and subscript |
| `04-mixed.cdxml` | Group, rich-text note, image, shape |
| `05-native.cdxml` | Native-only styled fragment and text that must be preserved |

`05-native.cdxml` is synthetic, hand-authored native CDXML without a Chemvas
snapshot; it is not actual ChemDraw output. The fixtures confirm the expected
editing state and output; they do not validate reaction chemistry. Real ChemDraw
import, export, and round-trip validation is separate evidence and is pending.
Real samples are handled as copies and never committed without permission.

## Safety checks

Use disposable documents in an isolated scratch directory. For full-disk tests,
use a disposable VM or a size-limited test volume; do not fill the host's normal
data volume. Source evidence comes from
[test_cdxml_working_documents.py](../tests/test_cdxml_working_documents.py) and
[test_save_recovery_lifecycle.py](../tests/test_save_recovery_lifecycle.py).
Source tests do not replace the manual reproduction, done in isolation with the
installed app on each row, which is still required.

- Save failure: force a failed save (read-only folder, locked file, full disk).
  Record the original file's SHA256 before and after; it passes only if the
  original bytes are identical.
- Interrupted session: kill the process mid-edit; relaunch offers recovery and no
  document is corrupted.
- External edits: a change made by another program to an open file is detected
  before Chemvas overwrites it.

CLI validation does not prove GUI undo or recovery.

## Manuscript output

- Export SVG, PDF, and PNG at 84 mm and 174 mm widths, and PNG at 300 dpi.
- Check document state semantically, then rendered symbols and dimensions.
- Insert the outputs into a real manuscript for visual review by someone
  independent of the change. Pixel equality across operating systems is not
  promised; editing exports in external editors is a separate support scope.

## Ship criteria and reporting

Ship only with zero data loss, chemical-meaning changes, open failures, wrong
output, installation failures, and essential interaction failures. New features
wait for a later release. Review the actual bundle's dependency inventory, license notices and redistribution
conditions and record the outcome; this review is pending. Each
check is published as passed, failed, pending, or skipped, with a reason. A
skipped required gate is not a pass.

## Receipt

Policy baseline: 2026-10-25, first stable desktop release targets.
Release completion: pending. Candidate git SHA: pending. Whole-OS acceptance: pending.
Shared: CI pending; bundle inventory and notice review pending; ChemDraw evidence pending.

| Row | Environment | SHA256 | make check | Install | OS security | Fixtures | Safety | Output | Public smoke | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W1 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| W2 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| M1 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| L1 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| L2 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
