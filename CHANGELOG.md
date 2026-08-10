# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Context-validated attached `PPh3` alias expansion**: a `PPh3` atom label
  connected to carbon by one ordinary covalent single bond now expands into an
  explicit four-coordinate `[P+](Ph)3` fragment for 3D `.xyz` conversion,
  Molecule Info, and elementary-step geometry. Standalone, metal-coordinate,
  non-single, styled, and explicitly re-annotated contexts fail closed.
- **Structural atom-mapping suggestions**: the Calculation dialog's atom
  correspondence editor gains a **Suggest by structure** button that fills
  unmapped reactant atoms from the maximum common substructure of the included
  reactant and product (RDKit). Bond orders are matched loosely, so atoms whose
  bonds only change order — a typical reaction center such as C-O → C=O — are
  suggested too; only atoms whose connectivity actually breaks or forms are left
  for you. It only fills gaps — it never overwrites a mapping you set, keeps the
  same-element rule, and reuses no product atom. The button is disabled when
  RDKit is unavailable.
- **Atom-id labels on the canvas**: while the Calculation dialog is open, every
  included atom is labelled with its stable Chemvas id on the drawing (reactant
  atoms tinted blue, product atoms orange), so a correspondence-table row can be
  matched to a spot on the structure at a glance. The labels are transient
  overlays that never change the document or selection.
- **Sulfonate and acyl alias labels**: `OTs`, `Ts`, `OMs`, `Ms`, `OTf`, `Tf`,
  `Ns`, `OAc`, and `Ac` now expand into explicit fragments for 3D `.xyz`
  conversion, Molecule Info, and elementary-step geometry, instead of being
  rejected as a single opaque pseudo-atom. `Ns` is the para
  (4-nitrobenzenesulfonyl) isomer.
- **Role-aware endpoint locking in the Calculation dialog**: once a drawn
  component is included as a step's reactant (or product), the same
  component's opposite endpoint is disabled, so a consumed species cannot be
  assigned to both sides by mistake. The lock is role-aware — catalysts and
  spectators stay editable on both endpoints — and only disables the other
  side; it never clears an existing selection, so changing the role back
  restores it.

### Fixed
- **Molecule Info title hidden behind the header buttons**: unless the window
  was stretched wide, the SMILES/InChI/InChIKey/Export 3D buttons reached over
  the painted "Molecule Info" heading and covered it. The buttons are now sized
  to their labels, which leaves the full title visible at the window's default
  width, and on narrower windows the title and subtitle elide at the button row
  instead of running underneath it.
- **Atom-correspondence dropdown could not be scrolled**: when a structure has
  many same-element atoms, the product-atom dropdown in the Calculation dialog
  showed every candidate in one over-tall popup with no scrollbar, so the lower
  atoms ran off-screen and the mouse wheel had nothing to scroll. The popup is
  now capped to a visible window with a working scrollbar.
- **Crash while using the Calculation dialog with an IME**: clicking a table
  cell in **Calculation ▸ Edit States and Steps...** while an input-method
  composition (e.g. Korean) was active could crash the whole app on Wayland,
  including WSLg. Qt reacts to a composition event by starting or focusing a
  cell editor — for cells hosting the embedded combo boxes it focuses the
  combo before even consulting the edit triggers — and the Wayland text
  input re-delivers the composition event on every such focus change, so
  the two recursed until the stack overflowed. The dialog tables take no
  text input at all: direct cell editing is now disabled and both tables
  ignore composition events outright, for item and widget cells alike.
  Unsaved work from a crashed session was already restored by autosave
  recovery.

### Removed
- **Painted "well" behind the modal tool buttons**: the top toolbar no longer
  draws the inset tray that grouped the pick-one mode tools apart from the
  flip/rotate command buttons. The decoration read poorly in practice, so the
  toolbar is back to a flat bar; buttons, actions, and shortcuts are unchanged.
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
