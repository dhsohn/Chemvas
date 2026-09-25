# Chemvas reference

[한국어](REFERENCE.ko.md)

Detailed reference guide for Chemvas covering application startup, drawing tools, document formats, figure export, and keyboard shortcuts. For a quick start, see the [README](../README.md); for headless automation, see the [Agent CLI guide](AGENT_CLI.md).

## Running

```bash
python app/main.py    # development tree
chemvas               # after install
chemvas --help        # root CLI help without starting Qt
chemvas --version     # package version without starting Qt
```

- **Drawing**: Select a tool from the toolbar and click/drag on the canvas.
- **SMILES**: Enter a SMILES string in the field below the toolbar, click **Insert** (or press Enter), preview on the canvas, and click to place (`Esc` to cancel).
- **Templates**: Select a ring or structure template and click on the canvas to insert.
- **Sample Files**: Open pre-built examples via **File ▸ Open** from [`examples/`](../examples/) (see [examples README](../examples/README.md)).
- **New Canvas (`Ctrl+N`)**: Opens a fresh canvas inheriting page size, orientation, bond length, and styling from the active document.

## Drawing features

![Draw a structure: drag bonds, press 2 on a bond, type o on an atom, fuse a ring](images/walkthrough-drawing.gif)

![Arrows and labels: draw arrows, double-click to label, draw a reaction profile with snapping lines](images/walkthrough-arrows.gif)

![Select, move, rotate, align: move, rotate knob, flip, align middle, distribute](images/walkthrough-editing.gif)

- **Bonds**
  - **Types**: Single, Double, Triple, Bold, Wedge, and Hash.
  - **Bold editing**: Clicking a bond or dragging along it preserves its order and double-bond alignment. Crossed unspecified double bonds cannot be changed with Bold.
  - **Snapping**: 30° angle snapping with standardized default bond lengths.
  - **Shortcuts**: Hover over a bond and press `1` (single), `2` (double), `3` (triple), `w` (wedge), `h` (hash), or `d` (dashed).
  - **Length Adjustment**: Changing bond length rescales the molecular framework, ring fills, and bound marks proportionally around the molecule center.

- **Rings & templates**
  - **Quick Insertion**: Benzene, cycloalkanes (3- to 8-membered), and chair conformations.
  - **Ring Fusion**: Drag from an existing bond or press `a` (benzene) / `4`–`8` over a bond to fuse a ring.
  - **Ring Fill**: Select a completed ring cycle and open the Ring Fill palette to apply colored fills.

- **Arrows**
  - **Styles**: Reaction arrows, equilibrium (balanced or biased), resonance, curved, dashed, and circular arc arrows (90°, 180°, 270°; hold `Shift` to invert arc direction).
  - **Settings**: Arrow width and arrowhead size are configurable across the document with real-time preview and full Undo/Redo.
  - **Endpoint Snapping**: Arrow and line endpoints snap to nearby endpoints within 12 pixels for seamless alignment.

- **Arrow labels**
  - **Editing**: Double-click an arrow or line to edit conditions above and below.
  - **Formatting**: Use `_` for subscripts (`MnO_2` → MnO₂) and `^` for superscripts (`\Delta G^\ddagger`). Use braces `{}` for multi-character groups (e.g., `K_{2}CO_{3}`).
  - **Multiline**: Supports multiline text with real-time preview. Labels automatically inherit document font settings and move with the arrow.

- **Lines**
  - Draw non-bond lines (solid, dashed, wavy, bold) for energy-level profiles or connectors.
  - Hold `Shift` while dragging to constrain angles to 15° increments. Clicking without dragging places a standard horizontal level.

- **Brackets & annotations**
  - Square, round, and curly brackets, plus dagger (`†`) and double dagger (`‡`) markers.
  - Select and drag bracket strokes to reposition them.

- **Orbitals**
  - Supports s, p, sp, sp2, sp3, d, and MO bonding/antibonding representations.
  - Click a selected orbital to access scale and rotation handles. Toggle orbital shading via Phase On/Off.

- **Notes (Text)**
  - Rich-text notes with customizable font family, size (6–96 pt), weight, color, alignment, and sub/superscripts.
  - **Note Appearance**: Configure background fill, border color, opacity, padding, and line spacing globally via **Edit ▸ Note Appearance…**.

- **Atom labels**
  - Supported aliases: `Me`, `Et`, `OH`, `NH2`, `SH`, `Ph`, `PPh3`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `tBu`, `i-Pr`, `CF3`, `OTs`, `Ts`, `OMs`, `Ms`, `OTf`, `Tf`, `Ns`, `OAc`, `Ac`.
  - Neutral OH, NH2, and SH linked via a single bond support automated chemical property resolution.

- **Charge marks**
  - Hover over an atom and press `+` or `-` to increment/decrement formal charge.
  - Bound marks can be dragged or nudged for optimal visual clarity while remaining chemically bound to their parent atom.
  - Right-click a mark and choose **Reassign to atom…** to reassign it to another atom.
  - Charge and radical marks maintain independent color settings from their parent atoms.

- **Coloring**
  - Select a color swatch before painting. Atoms, bonds, notes, and charge marks can each be colored independently.

- **Grid & snapping**
  - Cycle through **None → Hex → Square** via the status bar.
  - Grid spacing is calibrated to half a standard bond length. Arrow endpoints snap intelligently to existing endpoints and grid points.

- **Visual feedback**
  - **Angle & Length Guides**: Interactive badges display bond angles and lengths while sketching.
  - **Valence Checking**: Toggle **View ▸ Valence Checking** to highlight questionable valences for common main-group elements (H, B, C, N, O, F).

- **Editing & transformation**
  - **Selection**: Click individual atoms/bonds or drag a marquee box. Group/ungroup elements using `Ctrl+G` / `Ctrl+Shift+G`.
  - **Transformation**: Flip horizontally (`Ctrl+Shift+H`), flip vertically (`Ctrl+Shift+V`), or rotate (`Alt+Up/Down` for 15°, `Alt+Left/Right` for 1°).
  - **Eraser**: Click or drag over elements to delete. Deleting all bonds connected to an unlabeled carbon cleanly removes the residual atom.
  - **Alignment**: Align structures (left, center, right, top, middle, bottom) and distribute them evenly via the **Edit** menu.

## The `.chemvas` file format

Chemvas saves documents as human-readable JSON files storing molecular models, annotations, arrows, and view settings:

```json
{ "type": "chemvas", "version": 8, "schema": 1, "min_reader": "0.18.0", "state": { /* ... */ } }
```

- **Current Version**: Version 8, schema 1 (introduced in Chemvas 0.18.0+).
- **Backward Compatibility**: Fully opens valid version 7 files. See [document compatibility policy](DOCUMENT_COMPATIBILITY.md).
- **Safety**: Unsaved changes are never overwritten without confirmation.

## Autosave & recovery

- **Continuous Snapshots**: Automatically saves snapshots to the user application data directory every few seconds without touching your working files.
- **Crash Recovery**: Choose **File ▸ Recover Unsaved Work…** to open interrupted work as new unsaved copies. Startup does not automatically reopen documents. Recovery files remain until the copies have been autosaved successfully; unreadable recovery files are retained with a warning.
- **Save or Discard**: Save recovered copies to keep them. Work explicitly discarded during a completed clean exit is removed from recovery.
- **Session Safety**: Unsaved tabs display a `●` indicator. The File menu maintains an **Open Recent** list for rapid access.

## Figure export

Export publication-grade figures in plain SVG, PDF, PNG, or TIFF formats:

- **Vector Outlines**: Atom and arrow labels are rendered as vector glyph outlines in SVG and PDF, ensuring perfect typography across all platforms without requiring local font installations.
- **Physical Column Presets**: Match standard publication column widths (e.g., 84 mm for 1-column, 174 mm for 2-column) at explicit target DPIs (up to 600 DPI).
- **Editable Chemvas SVG**: Check **Editable Chemvas SVG** to embed full `.chemvas` document data inside the SVG file, allowing the figure to be reopened and edited in Chemvas anytime.
- **Lossless TIFF**: Exports with lossless LZW compression and full transparency support.

## Chemistry I/O

Features marked *(RDKit)* require the optional backend (`pip install "chemvas[rdkit]"`).

![Chemistry I/O: open a molfile, Molecule Info, export MOL and 3D XYZ](images/walkthrough-chemistry.gif)

### SMILES import *(RDKit)*

- Enter SMILES strings in the context bar to place structures on the canvas.
- Preserves tetrahedral stereochemistry (`@`/`@@`) with wedge/hash bonds.
- Unspecified double-bond stereochemistry imports as crossed `double_either` bonds.
- The input text is used for insertion; it is not stored in document history or restored when opening a drawing.

### MOL interchange

- Import and export standard MDL Molfiles (`.mol`, V2000).
- Basic MOL export works without RDKit; expanding complex abbreviations requires the RDKit backend.
- Full fidelity for charge, radical, and `double_either` stereochemical flags.

### Molecule Info inspector *(RDKit)*

![Molecule Info dock with aspirin on a macOS canvas](images/editor-inspector.png)

Open the inspector via **View ▸ Molecule Info** or the cube toolbar icon:
- **Interactive 3D Preview**: Drag to rotate, scroll to zoom.
- **Molecular Properties**: Formula, exact molecular weight, atom count, and ring count.
- **One-Click Identifiers**: Copy canonical SMILES, InChI, and InChIKey directly to your clipboard.
- **3D XYZ Export**: Export 3D coordinates generated via energy minimization.

### 2D→3D `.xyz` export *(RDKit)*

- Converts 2D structures into clean 3D Cartesian coordinates (`.xyz`).
- Automatically expands supported abbreviation groups (e.g., `OTs`, `Boc`, `Ph`) into complete atom-level fragments.
- Respects wedge/hash stereocenters during 3D conformation generation.

## Keyboard shortcuts

Select tools from the canvas or edit hovered atoms/bonds with the shortcuts below.

- **Canvas & Tools**: Select `Space`, Bond `X`, Atom `A`, Text `T`, Arrow `E`, Benzene `J`, Brackets `Shift+T`, Orbitals `Shift+G`, Charge/Radical `Shift+E`, Perspective `Alt+D`
- **Atom Editing (hover over atom)**: Change element via [Atom-label hotkey map](#atom-label-hotkey-map), charge `+`/`-`, edit label `Enter`, sprout chains `0`–`9` (`9` = gem-dimethyl)
- **Bond Editing (hover over bond)**: Single `1`, Double `2`, Triple `3`, Bold `b`, Wedge `w`, Hash `h`, Dashed `d`, double-bond alignment `l`/`c`/`r`, Benzene fusion `a`, Ring fusion `4`–`8`
- **Transformations**: Flip Horizontal `Ctrl+Shift+H`, Flip Vertical `Ctrl+Shift+V`, Rotate `Alt+Up/Down` (15°) / `Alt+Left/Right` (1°), Nudge `Shift+Arrows` (10 pt)
- **Alignment**: **Edit ▸ Align** (Left, Center, Right, Top, Middle, Bottom) and **Edit ▸ Distribute** (Horizontally, Vertically)
- **General**: Save `Ctrl+S`, Open `Ctrl+O`, Select All `Ctrl+A`, Group `Ctrl+G`, Ungroup `Ctrl+Shift+G`, Undo `Ctrl+Z`, Redo `Ctrl+Y`, Delete `Delete`/`Backspace`

### Atom-label hotkey map

Hover over an atom and press a key to quickly replace its element or group:

| Key | Label | With Shift → label |
| --- | --- | --- |
| `a` | — (sprout benzene) | `Ac` |
| `b` | `Br` | `B` |
| `c` | `C` | `Cl` |
| `d` | `D` | — |
| `e` | `Et` | `CO2Me` |
| `f` | `F` | `CF3` |
| `h` | `H` | `Cbz` |
| `i` | `I` | — |
| `k` | `SO2` | `t-Bu` |
| `l` | `Cl` | `Li` |
| `m` | `Me` | `MgBr` |
| `n` | `N` | `NO2` |
| `o` | `O` | `OMe` |
| `p` | `P` | `Ph` |
| `q` | `O` | `Fmoc` |
| `r` | `R` | — |
| `s` | `S` | `Si` |
| `w` | `N` | — |
| `x` | `X` | — |
| `y` | — | `Boc` |
| `z` | — (sprout) | `N3` |

### Shortcut compatibility

Keybindings are designed to feel natural to ChemDraw users, allowing familiar drawing muscle memory to transfer seamlessly.

## Roadmap / not yet supported

- **SDF (multi-molecule) interchange**: Multi-molecule import/export.
- **Pre-packaged Binaries**: Standalone installers (Chemvas is currently distributed via PyPI: `pip install chemvas`).
- **Reaction-scheme 3D generation**: Richer multi-step 3D modeling and template libraries.
