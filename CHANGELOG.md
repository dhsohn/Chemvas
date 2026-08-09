# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed
- **Single-species `pack` command**: the Calculation Bundle v1 directory export
  (`source.chemvas`, `structure.mol`, `geometry.xyz`, `atom_map.json`,
  `manifest.json`) had no remaining consumer. Machine handoff of geometries now
  happens exclusively through the elementary-step `machine.json` written by
  `pack-step`; `inspect` remains the headless structure inventory.

### Added
- **Single-file elementary-step artifact**: `inspect-plan` reports stable
  source-mapping, electronic-state, and component-count blockers, while
  `pack-step` atomically writes one non-overwriting `machine.json` using
  `factory/machine-observation` v1 with a `chemistry/elementary-step` v1 payload.
  The payload inlines source and RDKit provenance, atom correspondence, bond
  changes, and for a qualifying single-component step, exact reactant/product
  XYZ in one reactant atom-identity order with canonical 0-based reaction-center
  indices. Readiness and exact blocking codes live in the common `handoff`
  field; the former step-specific envelope, multi-directory bundle, and separate
  endpoint files are removed.
- **Headless document rendering**: `chemvas render-document` now renders a
  bounded `.chemvas` drawing to a new SVG or PNG through the canonical figure
  exporter without opening a desktop window or loading RDKit. It preserves the
  source, refuses replacement and symlink targets, atomically publishes only a
  complete output, and reports exact source/output hashes plus point/pixel
  dimensions as deterministic JSON.
- **Canvas mapping highlights**: selecting an atom-correspondence row or
  browsing its product choices temporarily marks reactant and product atoms on
  the drawing with distinct R/P colors and line styles. The dialog owns and
  removes these non-selectable overlays without changing the document,
  selection, history, or dirty state.
- **GUI atom correspondence editor**: the Calculation dialog now maps each
  included reactant atom to a same-element product atom by stable Chemvas ID,
  preserves explicit unmapped partial drafts, reports mapped/total readiness,
  and rejects duplicate product assignments before the existing `pack-step`
  gate. Exact atom IDs shared by both endpoints are suggested without inferring
  a mechanism.
- **Agent-safe graph patches**: `chemvas inspect-document` exposes stable atom IDs,
  exact source hashes, and the complete graph without Qt; `chemvas apply-patch`
  dry-runs or atomically publishes a new non-overwriting document after strict
  versioned JSON, document, and Calculation Plan validation. The bounded v1
  operation set edits atoms and bonds without invoking a language model or
  inferring chemistry.
- **macOS application name**: the menu bar now reads **Chemvas** instead of the
  interpreter or script name. Run from source or from a `pip install`, the
  process has no `Info.plist`, so Qt fell back to the basename of `argv[0]` and
  macOS to the process name; Chemvas now supplies `CFBundleName` itself before
  the `QApplication` is built. A real `.app` bundle already names itself and is
  left alone.
- **Menu bar**: standard **File / Edit / View** menus (alongside the existing
  Help menu) expose New Canvas, Open / Open Recent, Save / Save As, exports,
  Undo / Redo, clipboard and selection commands, flips and rotation, zoom
  controls, and the Molecule Info window — with the platform shortcuts shown
  where they apply.
- **Canvas Size dialog**: File ▸ Canvas Size… changes the sheet size and
  orientation of the active document.
- **Eraser tool**: click or drag to erase atoms, bonds, and annotations; one
  drag records a single undo step.
- **MOL import**: File ▸ Open reads MDL Molfiles (`.mol`, V2000) into a new
  untitled document, no RDKit required. Property records are limited to
  `M  CHG` / `M  RAD`, and wedge/hash stereo to single bonds. Malformed or
  unsupported files are rejected with a specific error instead of a
  best-effort guess; nonzero counts-line chiral flags and singlet radical code
  1 are currently rejected rather than silently losing spin/stereo semantics.
- **Copy InChI**: the Molecule Info window now offers the full InChI string
  alongside the existing SMILES and InChIKey copy buttons.
- **Autosave & crash recovery**: open documents are snapshotted to a per-user
  app-data folder every few seconds. After an abnormal exit the next launch
  restores the unsaved work — flagged unsaved with a `●` and a status-bar note —
  while a clean quit reopens whatever files were open, so the last session comes
  back automatically. Snapshots are pruned once a session is restored or closed
  cleanly, and a still-running instance's session is never touched.
- **Open Recent**: the File menu lists recently opened/saved documents (entries
  whose file has disappeared are pruned) with a **Clear Recent Files** action.
- **Unsaved indicator**: a modified document shows a `●` dot on its tab and the
  platform's native modified marker in the window title, cleared on save.
- **Duplicate-open guard**: opening a file that is already open switches to its
  window instead of creating a second, independently-editable copy.

### Changed
- Slimmed the top toolbar down to drawing controls: the Save / Open / New
  Canvas / Molecule Info / Undo / Redo buttons and the file dropdown moved into
  the new menu bar, leaving the tool well, flip/rotate, and the SMILES
  quick-insert field. All keyboard shortcuts are unchanged.
- Copying a selection (`Ctrl+C`) now also places SVG and PDF vector flavors on
  the clipboard next to the PNG, so vector-aware apps (Illustrator, Office)
  paste vectors.
- Unified one-sided Bold double bonds with the ordinary double-bond positioning
  model: right-click now offers **Inward**, **Centered**, and **Outward** without
  dropping the Bold style, and `l` / `c` / `r` preserve it as well.
- Moved the SMILES quick-insert field from the tool-options bar up to the main top
  toolbar, so it stays visible regardless of the active tool. The field stretches to
  fill the space after the drawing and transform controls (up to a
  maximum width so it does not sprawl on wide monitors) and shrinks on narrow windows
  instead of pushing buttons into the overflow menu.
- Renamed the SMILES insert button from **Render** to **Insert**, so its label matches
  what it does — placing the typed structure on the canvas.
- Redrew the **Atom** tool icon as a periodic-table glyph (previously an `A`
  letterform) to signal "choose a specific element" and to keep it visually distinct
  from the **Text** annotation tool's `T`.
- Gave the status-bar zoom **Fit** control a subtle border and hover state so it reads
  as a button rather than plain text, matching the `−` / `+` controls beside it.
- Grouped the pick-one **mode tools** (select, bond, ring, arrow, …) inside a subtle
  painted "well" on the top toolbar, so they read as one set — visually distinct from
  the loose one-shot command buttons beside them (flip and rotate).

### Fixed
- Windows headless document rendering now uses the native Qt platform without
  showing a window, preventing labels from turning into boxes when `offscreen`
  is selected only after the process has started.
- `chemvas --help`, `chemvas -h`, and `chemvas --version` now return root CLI
  metadata without starting Qt; the help identifies desktop startup, supported
  root options, and every dispatched headless subcommand.
- Cleared transient hover indicators before Perspective rotation captures its
  scene snapshot, preventing a false scene-mutation failure at release. Failed
  press, preview, or finalization callbacks are also contained at the PyQt6
  boundary and reported in the status bar instead of aborting the app.
- A left-click that successfully retries an interrupted Perspective rotation
  commit is now consumed instead of immediately starting another rotation;
  button-free mouse movement can no longer extend a stranded drag either.
- Perspective rotation now accepts the expected selection-state republication
  that occurs when a selected ring is restored through its atom graphics, so
  releasing the left mouse button commits instead of reporting a false global
  authority change.

## [0.1.0] - 2026-07-13

### Added
- 2D drawing canvas: bonds (single/double/triple, bold, wedge, hash) with 30° angle
  snapping and a consistent default bond length.
- Ring and conformer templates (benzene, cycloalkanes, chair/boat) with live
  preview and click-to-insert.
- Arrows: reaction, equilibrium, resonance, curved, and dashed, with adjustable
  width and head scale.
- Bracket annotations (square/round/curly) plus dagger (`†`) and double dagger (`‡`)
  objects.
- Atom labels with charges, radicals, and common alias labels
  (`Me`, `Et`, `OH`, `Ph`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `i-Pr`).
- Free **Text** annotation tool (`T`), separate from the **Atom** tool (`A`): place
  captions/labels independent of the molecule graph, edited inline on the canvas.
  Its option bar offers size, bold/italic, super-/subscript, and left/center/right
  alignment, and the toolbar Text button has a font-family dropdown; text color is set
  with the existing Color tool. Rich formatting is preserved in `.chemvas` documents
  and figure exports.
- SMILES import with cursor preview and click-to-place (requires RDKit).
- Molecule Info window with interactive 3D preview and molecular formula/weight
  (requires RDKit).
- Canonical SMILES, InChI, and InChIKey computation for the current structure;
  the Molecule Info window gained **Copy SMILES** / **Copy InChIKey** buttons that
  place the value on the clipboard (requires RDKit).
- **Export MOL** (File menu): write the **selected** structure to an MDL Molfile
  (`.mol`, V2000), preserving 2D coordinates, bond orders, and wedge/hash stereo.
  Plain-element
  structures need no RDKit; abbreviation labels (`Ph`, `CF3`, `tBu`, …) are expanded
  into explicit atoms via RDKit when it is installed.
- Figure export to SVG / PDF / PNG / TIFF with outlined glyphs and deterministic
  physical sizing (bond-length or 84/174 mm column fit).
- 2D→3D `.xyz` export of the current molecule or atom/bond selection, carrying
  charges/radicals and wedge/hash stereo (requires RDKit).
- Editing: select/move, horizontal & vertical flip, perspective rotation, and
  delta-based undo/redo.
- ChemDraw-compatible keyboard shortcut subset: atom/bond hover hotkeys
  (labels, sprouts incl. gem-dimethyl `9`, dashed `d`/`Shift+D` and double-bond
  position `l`/`c`/`r` bond styles), generic tool hotkeys (`Shift+T` brackets,
  `Shift+G` orbitals, `Shift+E` chemical symbols), selection rotate/nudge via
  `Alt`/`Shift`+arrows (also moves/rotates selected arrows, notes, brackets,
  orbitals, and shapes), view keys `F5`–`F8`, and `Ctrl+X` cut.
- **Select All** (`Ctrl+A`): selects every object on the canvas (structures,
  arrows, brackets, shapes, orbitals, marks, and text notes) and switches to the
  Select tool.
- **Group / Ungroup** (`Ctrl+G` / `Ctrl+Shift+G`): ChemDraw-style object groups.
  A selected group is outlined by a single dashed bounding box, and clicking
  anywhere inside the box drags the whole group. Selecting any member (click,
  shift-click, or marquee) extends the selection to
  the whole group so grouped fragments, arrows, and annotations move and delete
  together. Grouping is undoable, absorbs overlapping groups, and group
  membership is persisted in `.chemvas` documents (file format version 3;
  older files still load).
- `.chemvas` JSON document save/load (`{"type":"chemvas","version":4,...}`;
  older version 1–3 files still load).
- ACS 1996 default style and color palette.
- **Application icon and OS identity**: a benzene-hexagon app icon in the window,
  Dock, and taskbar, plus the application name and version reported to the OS.
- **About Chemvas** dialog, reached from a **Help** menu (the native application
  menu on macOS): shows the version, MIT license, RDKit availability, and the
  Qt/Python versions in use.
- Desktop packaging: a PyInstaller spec, a macOS `.app` that registers the
  `.chemvas` document type (double-clicking a file opens it in Chemvas), and a
  Linux `.desktop` entry with an `application/x-chemvas` MIME type.

[Unreleased]: https://github.com/dhsohn/Chemvas/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dhsohn/Chemvas/releases/tag/v0.1.0
