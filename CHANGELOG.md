# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
- Moved the SMILES quick-insert field from the tool-options bar up to the main top
  toolbar, so it stays visible regardless of the active tool. The field stretches to
  fill the space between the drawing tools and the file/history buttons (up to a
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
  the loose one-shot command buttons beside them (flip, rotate, undo, redo).

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
