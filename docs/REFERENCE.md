# Chemvas reference

User-facing detail for Chemvas: running the app, drawing features, the document
format, export behavior, and shortcuts. The landing overview is the
[README](../README.md); headless and agent contracts are in
[AGENT_CLI.md](AGENT_CLI.md).

## Running

```bash
python app/main.py    # development tree
chemvas               # after install
chemvas --help        # root CLI help without starting Qt
chemvas --version     # package version without starting Qt
```

Pick a tool from the top toolbar and click/drag on the canvas to draw. Enter a
SMILES string in the top input and press **Insert** to enter placement mode: move
the mouse to preview, click to insert, `Esc` to cancel. Templates work the same
preview-and-click way.

Open a sample document from [`examples/`](../examples/) via **File ▸ Open** —
the [examples README](../examples/README.md) describes what each one contains.

## Drawing features

- **Bonds** — single / double / triple, bold, wedge & hash; 30° angle snapping and
  a consistent default bond length.
- **Rings & templates** — benzene, cycloalkanes, chair/boat conformers placed by
  live preview and click-to-insert.
- **Arrows** — reaction, equilibrium, resonance, curved, and dashed arrows with
  adjustable width and head scale.
- **Brackets & annotations** — square / round / curly brackets, dagger (`†`) and
  double dagger (`‡`) annotation objects.
- **Atom labels** — elements, charges, radicals, and common alias labels
  (`Me`, `Et`, `OH`, `Ph`, `PPh3`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `tBu`,
  `i-Pr`, `CF3`, `OTs`, `Ts`, `OMs`, `Ms`, `OTf`, `Tf`, `Ns`, `OAc`, `Ac`).
- **Editing** — select / move, an eraser tool (click or drag to erase),
  horizontal & vertical flip, perspective rotation, and delta-based undo/redo.
- **Desktop menus** — standard File / Edit / View menus, including a
  **Canvas Size** dialog for the sheet size and orientation.
- **ChemDraw-compatible shortcuts** — a substantial subset
  (see [Keyboard shortcuts](#keyboard-shortcuts)).

## The `.chemvas` file format

File ▸ Save / Open works with `.chemvas` files — a JSON-based format holding the
molecule model, annotations, arrows, bracket annotations, and settings:

```json
{ "type": "chemvas", "version": 7, "state": { /* ... */ } }
```

Version 7 is the only supported document contract. It can carry an optional
Calculation Plan v2 with bounded precomplex candidates, exact XYZ provenance,
and explicit endpoint review selections. Earlier document versions and
Calculation Plan v1 payloads are rejected.

Chemvas drawings must use the `.chemvas` suffix. Desktop startup arguments, OS
file-open events, **File ▸ Open**, **Open Recent**, and clean-session reopening
all reject or ignore `.json` drawing paths; **Save** and **Save As** publish
drawings only as `.chemvas`. JSON request, patch, report, and machine-artifact
files used by headless commands remain separate protocols and are unaffected.

## Autosave & recovery

Chemvas snapshots every open document to a per-user app-data folder every few
seconds — nothing is written next to your own files. If the app is killed or
crashes, the next launch restores those documents (unsaved ones flagged with a
`●` and a status-bar note); a clean quit simply reopens whatever files were
open. Snapshots are pruned once a session has been restored or closed cleanly.
Stale recent-file and clean-session entries for unsupported drawing paths are
ignored. A current internal crash autosave can still recover the drawing data,
but an unsupported original path is discarded and the recovered canvas opens
unbound as an unsaved document.

Autosave never replaces a complete recovery snapshot with one whose capture
reported a warning. It keeps the last good snapshot and shows a persistent
status-bar warning instead; the warning clears only after a later autosave
succeeds without warnings.

Unsaved tabs show a `●` marker, the File menu keeps an **Open Recent** list, and
reopening an already-open file switches to its window instead of duplicating it.

## Figure export

Plain SVG / PDF / PNG / TIFF with outlined glyphs (so screen, vector, and raster
output never diverge) and deterministic physical sizing (bond-length or
84 / 174 mm column fit), independent of zoom.

Figure export defaults to plain SVG without Chemvas source metadata. Choose
**Editable Chemvas SVG** only when you want the SVG to carry the original
document payload for round-tripping back into Chemvas.

## Chemistry I/O

RDKit is an optional backend — Chemvas runs without it. The features marked
*(RDKit)* need `pip install "chemvas[rdkit]"`.

### SMILES import *(RDKit)*

Type a SMILES string in the top input, preview it under the cursor, and click to
place it on the canvas. `Ts` and `Ac` name the tosyl and acetyl abbreviations on
the canvas, so a SMILES asking for tennessine or actinium is refused rather than
drawn as the abbreviation.

### MOL interchange

Open MDL Molfiles (`.mol`, V2000) as new documents and export the selected
structure as `.mol`. Import and plain-element export need no RDKit; abbreviation
labels require optional RDKit expansion. `Ts` and `Ac` are the tosyl and acetyl
abbreviations on the canvas rather than tennessine and actinium, so a molfile
that uses either symbol for the element is rejected on import. Property records
are limited to `M  CHG` / `M  RAD`, wedge/hash stereo to single bonds, and the
counts-line chiral flag to zero. Singlet `M  RAD` code 1 is rejected until the
annotation model can preserve spin multiplicity.

### Molecule Info window *(RDKit)*

**View ▸ Molecule Info** opens a separate window with a 3D preview (drag to
rotate, scroll to zoom), the molecular formula and weight, and one-click copy of
the canonical SMILES, InChI, and InChIKey for the current selection. The
`Export 3D XYZ` button exports the selected molecule.

### 2D→3D `.xyz` export *(RDKit)*

Convert the current molecule or atom/bond selection into 3D coordinates:

- Export scope is the current chemical graph or the current atom/bond selection.
  Arrows, bracket annotations, and free text are **not** included in `.xyz`.
- `+`/`-`/radical marks become formal charges / radical electrons; wedge/hash bonds
  on single bonds become RDKit stereochemistry hints.
- Alias labels expand into explicit fragments (e.g. `OTs` → the full
  `-O-S(=O)(=O)-C6H4-CH3` tosylate). Each alias attaches through a single bond;
  `Ns` is the para (4-nitrobenzenesulfonyl) isomer. Carbon-bound `PPh3` is
  accepted only through exactly one ordinary covalent single bond and expands as
  phosphonium `C-[P+](Ph)3`; standalone, non-carbon, multiple, non-single, styled,
  or explicitly charge/radical-annotated uses fail closed.
- Unsupported labels, mis-connected aliases, and invalid wedge/hash use fail with an
  explicit error message instead of guessing.
- `.xyz` stores element symbols and 3D coordinates only — it is **not** a full
  round-trip of bond orders, stereochemistry, or reaction semantics.

## Keyboard shortcuts

Chemvas supports a major subset of ChemDraw-compatible shortcuts.

- **Empty canvas (tool hotkeys):** Select/Marquee `Space`, Bond `X`, Atom `A`,
  Text `T`, Arrow `E`, Benzene `J`, Brackets `Shift+T`, Orbitals `Shift+G`,
  Chemical symbols `Shift+E`, Perspective `Alt+D`
- **Atom hotkeys (hover over an atom):** element/alias labels
  `c n o s p f h b i l m e r x d` and `Shift+f/p/a/b/s/n/e/z/m/l/o/q/h/y`, charge `+`/`-`,
  edit label `Enter`, sprout `0/1/2/3/a/4/5/6/7/8/9/z/v/u` (`9` = gem-dimethyl)
- **Bond hotkeys (hover over a bond):** Single `1`, Double `2`, Triple `3`,
  Bold `b`/`Shift+B`, Wedge `w`, Hash `h`/`Shift+H`, Dashed `d`/`Shift+D`,
  double-bond position `l`/`c`/`r`, Benzene fusion `a`,
  Ring fusion `4/5/6/7/8`, Chair fusion `9/0`
- **Objects:** Flip Horizontal `Ctrl+Shift+H`, Flip Vertical `Ctrl+Shift+V`,
  Rotate selection `Alt+Up/Down` (15°) and `Alt+Left/Right` (1°),
  Nudge selection `Shift+Arrows` (10 pt)
- **View:** Actual size `F5`, Fit to window `F6`, Magnify `F7`, Reduce `F8`
- **File / edit:** Save / Open / Undo / Redo (platform defaults), `Ctrl+A` (select
  all, switches to the Select tool), `Ctrl+C` (copy selection — PNG plus SVG/PDF
  vector clipboard flavors), `Ctrl+X` (cut selection), `Ctrl+V` (paste the copied
  selection), `Ctrl+G` / `Ctrl+Shift+G` (group / ungroup selection),
  `Delete`/`Backspace` (delete selection, or edit/delete the hovered atom/bond),
  `Esc` (cancel template / SMILES insertion)

## Roadmap / not yet supported

These are known gaps, not bugs — contributions welcome:

- **SDF (multi-molecule) interchange:** import and export. Single-molecule
  `.mol` import/export, SMILES export ("copy as SMILES"), and InChI / InChIKey
  have landed.
- **Distribution:** one-file desktop binaries (Chemvas is already on PyPI —
  `pip install chemvas`).
- **Multi-molecule / reaction-scheme 3D export** and richer template libraries.
- **Deliberately out of scope for now:** printing (export a PDF instead),
  persistent preferences (every document starts from the ACS 1996 defaults),
  pasting external clipboard content, and drag-and-drop file open.
