# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- The README hero image and example now show `examples/template2.chemvas`
  (the C–P bond cleavage scheme); fixed a title typo in that document
  ("Cleavege" → "Cleavage").
- Restructured `README.md` / `README.ko.md` into a short landing page (identity,
  statement of need, quickstart, capability table, docs index). The detailed
  user documentation moved to `docs/REFERENCE.md` and the headless/agent
  contracts to `docs/AGENT_CLI.md`, both without content changes. The docs-sync
  guards now pin the file-format example and tool hotkeys to `docs/REFERENCE.md`
  and additionally pin the READMEs' prose mention of the current document
  version.
- The CI job that installs RDKit now runs every RDKit-gated test file — the
  two calculation integration modules, the molfile round trips, and the whole
  adapter file — instead of selecting name-prefixed tests inside one file.
  Measured in a no-RDKit environment mirroring the main CI job, 36 tests gate
  on a real RDKit and only 11 carried the selected prefix, so 25 ran in no CI
  job at all. A new guard pins the workflow's file list to the gates in the
  test tree, in both directions. The main job in turn no longer runs the two
  modules whose module-level gate skips every test without RDKit — those runs
  executed zero tests — and the same guard pins that exclusion list too, so a
  file with ungated tests cannot be excluded by mistake.
- Multi-part atom labels now anchor the attachment-side token at the atom and
  reverse their displayed groups when necessary (`CF3` → `F3C`, `OTs` → `TsO`,
  `Ph3P` → `PPh3`). This keeps attached bond lines at full length without
  changing the label stored in the document.

### Fixed
- The **Equilibrium** arrow now draws the conventional harpoon pair (⇌): one
  barb per line, both on the outside of the pair, with the forward arrow on
  top. Each line previously carried a full arrow head (⇄), which denotes two
  separate opposing reactions rather than an equilibrium. Documents saved
  earlier re-render with the corrected arrow; the stored file format and the
  arrow's `equilibrium` kind are unchanged.
- External JSON inputs now reject duplicate object keys and non-standard numeric
  constants instead of silently accepting a parser-dependent interpretation.
  This applies consistently to Chemvas documents, Calculation Plans, graph
  patches, precomplex requests, editable SVG metadata, and clipboard payloads.
- Autosave no longer replaces a complete recovery snapshot with a warning-bearing
  partial snapshot, such as one that would omit a temporarily inconsistent
  Calculation Plan. The last good snapshot remains recoverable, and a persistent
  status-bar warning stays visible until a later autosave succeeds cleanly.
- Bold double bonds in rings now thicken inward like bold single bonds, so
  adjacent strips meet in sharp mitred corners instead of leaving a clipped
  corner or white wedge.
- The abbreviation labels `Ts` (tosyl) and `Ac` (acetyl) are also the element
  symbols for tennessine and actinium, and three conversion paths resolved them
  as those elements instead of as abbreviations. All of them now treat the
  labels the way they treat every other abbreviation.
  - MOL export wrote them into the atom block as elements rather than taking
    the RDKit expansion path, so one drawing exported different chemistry to
    `.mol` than to `.xyz`. A molfile whose atom symbol is `Ts` or `Ac` is also
    rejected on import now, instead of being read back as the abbreviation.
  - Molecule Info reported a formula, molecular weight, SMILES, and InChI
    computed from tennessine or actinium: a drawn methyl tosylate came back as
    `CH3OTs` at 323.03 rather than `C8H10O3S` at 186.23. Those identifiers now
    stay blank, as they already did for `Ph`, `Me`, and every other
    abbreviation.
  - SMILES insertion placed an atom the rest of the app then read as the
    abbreviation: typing `C[Ac]` drew what Chemvas treats as an acetyl group.
    A SMILES asking for either element is now refused with a message naming the
    symbol, isotope-qualified forms such as `[227Ac]` included. Every other
    element, and every isotope of one, still imports.
- **Suggest by structure** closed Chemvas when the drawing contained an atom
  RDKit cannot sanitize — a neutral nitrogen still carrying four bonds because
  its charge has not been added yet, a carbon that briefly holds five, and
  similar work-in-progress states. The window disappeared without a message,
  taking every atom correspondence mapped in that dialog with it. The
  suggestion now runs on the connectivity as drawn; the structure's real
  problem is still reported where it always was, by the 3D preview and by
  `.xyz` and calculation-step export.
- **Suggest by structure** also reported every failure as "RDKit found no
  shared substructure beyond what is already mapped" — a chemistry claim about
  the drawing that was false whenever the tool, not the chemistry, was the
  problem. Without RDKit installed the button stayed enabled and gave that
  same answer (the 0.2.0 notes said the button is disabled in that case; it
  never was), an endpoint whose components are all context-only got it too,
  and a substructure search that stopped early discarded an already-computed
  mapping and reported it as no shared substructure — on a symmetric
  host–guest pair, about 4 clicks in 10. Each case now says what happened:
  a missing RDKit names the `chemvas[rdkit]` extra to install, a stopped
  search says to try again, an empty endpoint is named, and only a genuinely
  empty comparison keeps the no-shared-substructure sentence.

### Removed
- **Per-shape arrow icon renderer**: `MainWindowArrowIconRenderer` painted the
  arrow previews, presets, and the width/head controls until the toolbar-icon
  unification moved all of them to the shared SVG design set. That change
  dropped every call into the class but kept constructing it, so a second
  source of arrow icon geometry stayed in the tree and drifted — it still drew
  the equilibrium arrow with two full heads after the canvas moved to harpoons.
  The module, its construction, and its tests are gone, and the module now sits
  on the list production code may not import again. No icon changes appearance.

## [0.3.0] - 2026-08-13

### Changed
- **Current-only document contract**: Chemvas now reads and writes document
  version 7 only, with compact bond arrays and Calculation Plan v2 when a plan
  is present. Earlier document versions and Calculation Plan v1 payloads are
  rejected instead of being upgraded or read through compatibility branches.
- **Current-only precomplex contract**: precomplex generation accepts request
  format v2 with `chemvas-rigid-precomplex-placement/2` only. The frozen v1
  request/profile reproduction path and its partly unverified radius table have
  been removed.
- **Canonical desktop paths**: saved Chemvas drawings use `.chemvas` across
  startup arguments, OS file-open events, File Open, Open Recent, clean-session
  restoration, Save, and Save As; `.svg` and `.mol` remain explicit import
  inputs. Stale unsupported recent/session paths are ignored. Current internal
  crash autosaves can recover their drawing state, but an unsupported original
  path is cleared and the recovered canvas opens unbound and unsaved.

### Removed
- Removed deprecated export facades, history aliases, selection-style wrappers,
  bracket/bold compatibility aliases, and legacy version/profile constants so
  retired contracts cannot silently return.

## [0.2.0] - 2026-08-13

### Added
- **Reviewed precomplex ensembles and document version 6**: Calculation Plan v2
  can persist bounded deterministic rigid-placement candidates for two-component
  reactant and product endpoints, including exact XYZ, environment, contact,
  validation, and generation provenance. `generate-precomplex` creates the
  candidates, `inspect-precomplex` reports them, and `select-precomplex` records
  an explicit reviewer selection. `pack-step` regenerates the ensemble and
  rejects stale or unreproducible selections before publishing a reviewed
  endpoint pair; the coordinates remain initial guesses for downstream quantum
  optimization and scientific review.
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

### Changed
- **Canonical Chemvas document extension**: the desktop Open and Save As
  dialogs and startup argument dispatch now advertise and recognize Chemvas
  documents only as `.chemvas`, not the old `.json` filename alias. Rename any
  Chemvas documents that still end in `.json` to `.chemvas` before upgrading;
  JSON request, inspection, patch, and machine-artifact files used by headless
  commands are unaffected.
- **Cited, immutable precomplex radius profile**: new request format v2 requires
  `chemvas-rigid-precomplex-placement/2`, whose complete supported-element
  radius table uses Cordero (2008) Table 2 covalent radii and Alvarez (2013)
  Table 1 van der Waals radii with exact dataset, DOI, selector, and table-hash
  provenance. Frozen request/profile v1 remains byte-reproducible for existing
  documents. Generation, inspection, deterministic regeneration, endpoint-pair
  validation, and `machine.json` now route and report the persisted profile;
  mixed profiles or altered provenance fail closed. The scores remain geometric
  heuristics requiring researcher review and downstream optimization.
- **Canvas atom-id labels now color by mapping state**: while the Calculation
  dialog is open, an atom's id label takes the blue reactant or orange product
  tint only once that atom is actually mapped; every unmapped atom stays gray.
  Mapping progress is visible on the drawing at a glance.
- **Mapping rings removed from the canvas**: the blue/orange rings that framed
  the selected correspondence pair (drawn on row selection and while hovering
  dropdown candidates) are gone — they read as clutter over the structure.
  The mapping-state label colors above carry that information instead.
- **Mapping markers on the canvas lost their R/P letters**: while picking an
  atom correspondence, the rings around the selected reactant and product
  atoms no longer float an "R"/"P" letter beside the atom — the letters sat
  awkwardly over the drawing. Solid blue still means reactant and dashed
  orange still means product.
- **Mapping UI grays out what cannot be mapped**: in the Calculation dialog's
  atom correspondence, a reactant row with no same-element product candidate
  reads muted until the counterpart component joins the product endpoint; a
  product candidate already mapped by another row shows muted in the other
  dropdowns (picking it still just flags the duplicate); and atoms of
  components that sit out of the step entirely now get gray id labels on the
  canvas instead of no label.
- **Locked endpoints in the Calculation dialog look locked**: when including a
  component as the step's reactant (or product) disables its opposite
  endpoint, the locked inclusion and role dropdowns are now visibly muted
  (gray background, faint text) instead of only being unclickable, and both
  carry the explanation tooltip.

### Fixed
- **Colouring a ring that contains a dotted double bond did nothing**: picking a
  colour on a ring — clicking its fill with the colour tool, or recolouring a
  selection that holds the ring but not that bond's own line — failed silently
  when any bond in the ring used the dotted double style. Nothing was recoloured
  and the attempt still consumed a step of undo history. A dotted double bond is
  drawn as two graphics items and recolouring the ring correctly restyles both,
  but an internal check counted the second item as an unrelated object being
  changed and aborted the whole operation. Rings recolour normally now, at any
  bond style.
- **Terminal spam when opening menus under Wayland/WSLg**: Qt's Wayland backend
  prints `This plugin supports grabbing the mouse only for popup windows` to
  the terminal every time a menu opens. The startup stderr filter — previously
  macOS-only — now also runs on Linux and drops this known-harmless line.
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

[Unreleased]: https://github.com/dhsohn/Chemvas/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/dhsohn/Chemvas/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/dhsohn/Chemvas/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dhsohn/Chemvas/releases/tag/v0.1.0
