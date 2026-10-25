# Release validation documents

[한국어](README.ko.md) · [Platform acceptance](../../docs/RELEASE_ACCEPTANCE.md)

Open these five CDXML files in the installed app on every target platform. Work
on copies in a new directory, including a path such as `Chemvas 한글 checks/`.
The originals and [SHA256SUMS](SHA256SUMS) are the baseline; do not save over them.

These are public synthetic drawing cases, not evidence for a reaction or an
experiment. `01-basic` adapts the repository's `first-scheme.cdxml`; `02`–`04`
were composed with Chemvas 0.27.1 and saved as CDXML. The small image in `04` is
a generated blue square and orange circle. `05` is hand-authored native CDXML
without a Chemvas snapshot, **not a file exported by ChemDraw**. Actual ChemDraw
exchange needs separate samples and evidence.

![Representative documents rendered on macOS](preview.png)

The preview is a visual guide, not a cross-platform pixel-equality oracle.

## Expected content and deliberate edits

Counts below are for the originals. Font substitution can change metrics, but
must not hide symbols or change their meaning. A chemically different structure,
missing charge, lost group or changed image is a failure even if the file opens.

| File | Expected original | Edit to exercise in the GUI |
| --- | --- | --- |
| [01-basic.cdxml](01-basic.cdxml) | Two benzene-containing structures, 16 atoms / 16 bonds, one arrow. MnO₂ above and `oxidation` below. | Change the below label to `oxidation check`; move the arrow and verify both labels follow. |
| [02-reactants.cdxml](02-reactants.cdxml) | Three separate benzene structures, 18 atoms / 18 bonds. Captions `1`, `2`, `3` under their own structures, plus sign between the first two, one arrow to the third. | Move a structure and its caption together. Exercise Arrange Scheme with the plus connector; each caption stays with its own structure. |
| [03-notation.cdxml](03-notation.cdxml) | 7 atoms / 4 bonds; one solid wedge to F and one hashed bond to Cl; separate Na⁺ and Cl⁻. Equilibrium arrow with k₁ and k₋₁; note H₂O / ΔG‡ with subscript 2 and superscript ‡. | Move the stereochemical fragment; format the note and arrow labels, then undo/redo. Charge signs and wedge/hash endpoints must remain correct. |
| [04-mixed.cdxml](04-mixed.cdxml) | 3 atoms / 2 bonds. One group containing the structure and the two-line `Group A` / `한글 α + H₂O` note. One embedded 120×60 image, blue square at left and orange circle at right; separate dashed rounded rectangle. | Move the group; structure and note move together, image and frame do not. Resize the image while keeping its proportions; undo/redo. |
| [05-native.cdxml](05-native.cdxml) | 3 atoms / 2 bonds, one double bond to O, two notes and one arrow. `Native sample` is bold blue; `native XML` is black. Native fragment line width and double-bond spacing are retained. | Change `Native sample` to `Native edited`; save a copy and reopen. The text remains editable and blue; native structure styling remains. |

For the Arrange Scheme check on `02`, the blocks use atom IDs 0–5, 6–11 and
12–17 with captions 0, 1 and 2. The connectors are `[["notes", 3], ["arrows", 0]]`.
These are zero-based indices in the original. Follow the
[layout request format](../../docs/SCHEME_LAYOUT.md); inspect a newly saved file
before building a CLI request so its `source_sha256` matches.

## Same manual pass on every platform

1. Open a copy and compare every feature in the table, before any edit.
2. Perform the deliberate edit, Undo and Redo. Record the intended change with a
   screenshot or short description; confirm that unrelated content stayed put.
3. Save as a new `.cdxml`, quit the app, relaunch and reopen that saved document.
   Compare the entire drawing and editability with the recorded intended change.
4. Export SVG, PDF and PNG at **84 mm** and **174 mm**, PNG at **300 DPI**. Inspect
   the output in a separate viewer and insert it at that width in a manuscript.
   Check every charge, script, stereo bond, caption, image and Unicode glyph.
5. Confirm the original checksums are unchanged. Record candidate commit, artifact
   hash, OS/CPU/backend, actual fonts, result and evidence for each document.

These document checks do not substitute for installation, update/removal,
interrupted-session recovery or save-failure tests in the platform acceptance.
A successful layout report covers only its listed collision classes, not chemical
correctness or readability at the final print size.

## CLI corroboration

Run from this directory with an installed `chemvas` command. For a Windows
bundle use its `chemvas-cli.exe`; for other bundles use the provided CLI entry.
Choose a **new** output directory for every run; exports refuse to overwrite.
The same arguments work for each of the five input files.

```sh
mkdir check-output
chemvas inspect-document 01-basic.cdxml
chemvas check-layout 01-basic.cdxml
chemvas render-document 01-basic.cdxml --output check-output/basic-84.svg --width-mm 84 --min-font-pt 6
chemvas render-document 01-basic.cdxml --output check-output/basic-84.pdf --width-mm 84
chemvas render-document 01-basic.cdxml --output check-output/basic-84.png --width-mm 84 --dpi 300 --min-font-pt 6
chemvas render-document 01-basic.cdxml --output check-output/basic-174.svg --width-mm 174 --min-font-pt 6
chemvas render-document 01-basic.cdxml --output check-output/basic-174.pdf --width-mm 174
chemvas render-document 01-basic.cdxml --output check-output/basic-174.png --width-mm 174 --dpi 300 --min-font-pt 6
```

The SVG/PNG commands require at least 6 pt for the visible text covered by the
font report, including scripts. PDF does not support this flag and needs visual
review. This is the fixture set's baseline; use a journal's
stricter requirement when applicable and inspect the rendered glyphs visually.

Qt rounds SVG/PDF page dimensions to whole points. For these two profiles, allow
0.18 mm (about half a point) from the requested width: the current outputs measure
83.961 mm / 238 pt and 173.919 mm / 493 pt. At 300 DPI, PNG width should be 992 or
2055 pixels respectively, within one pixel of rounding. Record the measured size;
export success alone does not establish readable or correctly shaped text.

From a source checkout, the existing file-isolated gate also runs the fixture
inventory, distinctive-content and full-state save/reopen checks:

```sh
bash scripts/check.sh tests/test_release_validation_documents.py
```

This is a selected source test, not certification of any installed bundle. All
release-target installation and native GUI results start as **pending**.
