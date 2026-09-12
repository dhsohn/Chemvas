# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Give charge and radical marks independent display colors, preserved through
  history, native documents, clipboard selections and editable SVG. Native v7
  and clipboard v2 accept optional hex mark colors; older releases without this
  field reject explicitly colored marks. Existing uncolored documents still load.
- Complete the English/Korean agent authoring reference with settings, scene
  fields, request v2 and tested composition → template → patch examples. Clarify
  private output permissions, stereo/geometry/mapping limits and profile-2
  sampling semantics without changing the machine handoff contract or profile.
- Make GUI Group include whole connected molecules; explicitly regrouping an
  older partial group repairs its membership without migrating documents on load.
  Keep direct ungrouped atom movement available for local drawing corrections.
- Lead the English README with the editable desktop-to-agent-to-desktop workflow.
  Remove the duplicate static reaction-scheme image from both READMEs, keeping
  the walkthrough GIF.

### Fixed

- Apply document text font/color changes to existing arrow labels immediately,
  keeping their appearance consistent through Undo, reopening and figure export
  while preserving explicit arrow colors and individually formatted note text.
- Show selected charge/radical marks' chemical owners with transient guides and
  a distance warning; moving a mark retains its owner. Add explicit right-click
  reassignment with a highlighted atom chooser, preserving position/color and
  recording both atoms' electronic states in one Undo/Redo edit.
- Reopen documents and recover unsaved snapshots made with the minimum arrow
  head size (0.1) or note line spacing (0.8). Compare decimal settings bounds
  consistently while retaining strict rejection of invalid or lossy numbers.
- Require an explicit Color-tool swatch before painting, show the chosen swatch,
  and support coloring bound and free charge/radical marks without recoloring
  their atoms. Explain why coloring an implicit carbon has no visible effect.
- Fit the initial 3D preview to depth-adjusted atom footprints and clip molecule
  painting to its viewport, keeping the title, formula and molecular weight
  clear during zoom and rotation.
- Preserve current bond selection through bond-edit Undo/Redo so subsequent
  MOL and selected-molecule conversions retain the selected chemistry.
- Keep atom-bound charge/radical marks attached and restyled during bond-length
  changes, with exact geometry restoration through history. Reflect loaded
  lengths above 200 px and fractional values without accidental focus commits.
  Independent annotations retain their existing absolute-placement behavior.
- Apply Single, Double and Triple Bond-bar choices directly to existing bonds,
  preserving no-op history, and explain unsupported dotted-double overlays.
- Open Ring Fill as a palette with Select active, keeping the toolbar and
  status consistent instead of leaving a previous destructive tool armed.
- Select or erase a foreground note instead of reaching through it to a bond
  or invisible carbon hit target; keep visible structure and handle priority.
- Apply Save's calculation-plan draft consent to whole-document editable SVG.
  Preserve copied groups in selection editable SVG and disclose that partial
  exports omit the Calculation Plan and reopen using the original sheet settings.
- Preserve existing calculation-step and surviving-state order when editing,
  appending only new IDs. Reviewed geometry still binds the whole plan, so an
  unrelated step edit can still make a review stale.
- Report the first rejected precomplex placement's measured clash/contact
  details and distinguish missing candidates from candidates awaiting review.
  Keep candidate generation, ranking and blocked handoff behavior unchanged.
- Support multiline arrow labels across editing, preview and figure exports.
  Preserve nonblank raw text, edge line breaks and no-op Redo history; keep long
  previews scrollable and block over-limit input without silently truncating it.
- Avoid redundant autosave hashes for clean saved and recovered-unsaved
  documents. Keep strict snapshots and recovery checks; full-state collection
  and ordinary dirty/edit hashing remain.
- Apply Text commands consistently to an editing range or whole selected notes,
  including marquee selections. Adjust mixed font sizes per run, keep text
  selections across font-menu popups, and set the new-note font default when
  no note is selected. Explain Text commands that have no selected target.
- Expose document-wide Note Appearance controls for fill, border, padding and
  line spacing. Keep existing/new/reopened notes consistent and preserve exact
  prior rich text through Undo/Redo and failed style/history changes.
- Choose an individual image in Image Properties when several images are
  selected or grouped, without breaking the group or changing other panels.
- Fit atom-label exports to painted glyphs instead of text layout boxes, keeping
  normal label picking, charge/radical placement and calculation ID positions.
  Notes and arrow labels retain their existing layout bounds.
- Ask before saving a drawing whose reviewed precomplex pair is stale or invalid.
  Cancelling preserves the drawing and destination; saving keeps an editable
  draft and its review data without claiming calculation readiness.
- Compress TIFF exports with lossless LZW while preserving pixel values,
  transparency and output DPI.
- Copy induced bonds, complete ring fills and atom-bound marks with atom/bond
  selections, matching native clipboard content and selection figure exports.
  Keep Qt text-selection frames out of copied images and visibly explain invalid
  native clipboard data without falling through to an unrelated image flavor.
- Tie molecule-identifier copy feedback to the button's lifetime and restart it
  on repeated clicks, avoiding callbacks into a closed 3D information window.
- Coalesce selection-outline work during Select All and Undo/Redo. Reuse current
  atom-label clipping geometry across movement while checking changed text,
  font, transforms and stroke width; document validation remains uncached.
- Fuse rings onto the unoccupied side of concave chair edges, including rotated
  and reversed-winding drawings. Include visible caption-box fills and borders
  in Arrange Scheme spacing so boxes clear structures and neighbouring captions.
- Explain unsupported image imports with PNG/JPEG conversion advice and retain
  the offending image entry number in composition errors.
- Avoid decoding existing embedded images again when inserting or pasting new
  images. Keep strict incoming-image validation and aggregate resource limits.
- Restore initial canvas focus and Tab traversal after note editing; show focus
  on styled context/status buttons and enable keyboard reset/exact zoom entry.
- Update group membership with structure additions and member deletion, retaining
  the surviving group and restoring membership through Undo/Redo. Guide users to
  regroup before connecting different groups, and explain why Group needs more
  than a single molecule.
- Cancel pending pointer edits before Undo/Redo, Cut/Delete, Paste, grouping and
  object-edit shortcuts, preserving the selected tool and focused text editing.
  A late mouse release cannot publish a discarded gesture or erase Redo.
- Preserve other molecules' drawing depth when a Perspective gesture changes
  the projection frame; restore the complete coordinate inventory on Undo/Redo
  and cancellation, and retain it through save/reopen.
- Allow explicit graph patches to repair invalid alias attachments in a
  structurally valid drawing. Inspection remains strict, and the complete result
  must pass document, electronic annotation and Calculation Plan validation.
- Restore exact atom and scene-item geometry for Select/Move drag Undo/Redo,
  including bound charge positions and ring fills, without dirty float residue.
  Direct atom/bond drags update ring fills immediately.
- Keep SMILES insertion previews visible across high-DPI canvas viewports by
  distinguishing logical widget dimensions from physical image dimensions.
- Apply document-wide arrow width/head and orbital phase changes immediately,
  with exact Undo/Redo and synchronized decimal controls. Make sheet orientation
  undoable and keep off-sheet objects reachable after changes and reopening.
- Preserve blank paragraphs and natural-width multiline note alignment; paint
  note boxes behind text. Expose orbital resize handles and molecular-orbital
  controls, and allow the first drag to move TS brackets. Disambiguate recent
  filenames, deduplicate symlink aliases and promote already-open documents.
- Rotate notes, images, shapes and brackets around the common selection pivot
  while keeping their contents upright; flip complete selections around one
  pivot. Restore exact document/selection/history on grouping or transform failure.
- Refuse perspective rotation of affected wedge/hash components before mutation,
  and remove newly created perspective caches on first-gesture Undo or cancellation.
- Find occupied ring sides and selected ring fills from graph cycles, including
  SMILES imports without decorative fills. Keep fill/history failures atomic and
  allow native CLI regular-ring fusion on plain double bonds. Avoid local chair
  sprout crossings, correct right 270-degree arcs and near-vertical label sides,
  and distinguish clicks from small pointer wobble for Line/Arrow gestures.
- Keep an arranged region near its original location, with relative wrap budgets;
  identify unsupported image groups using the dialog's row/group numbers.
- Use fixed 96 logical DPI for desktop and CLI scene fonts. Reject dimensions
  that round below one output point/pixel and exclude completely unpainted shapes
  from export bounds without removing them from editable documents.
- Reject unknown startup options before Qt, while retaining supported Qt window
  options. Diagnose invalid native fields, Unicode, oversized mark text and PNG
  trailing data at shared input boundaries. Display arrow-label length limits.
- Use one assigned graph for SMILES/InChI, preserve supported bridgehead-N stereo,
  and reject lossy tetrahedral SMILES depictions or unconsumed wedge/hash stereo
  instead of silently changing interpretation. Distinguish aromatic sanitation
  failures and report conversion failures using Chemvas atom IDs.
- Require complete force-field parameters for 3D generation. Canonicalize paired
  component/conformer order in precomplex provenance, preflight supported endpoint
  topology, and expose exact-geometry duplicate counts in inspection only.
  Geometry convergence remains distinct from scientific acceptance.
- Show and enable copying molecule identifiers before slow 3D work completes,
  retaining stale-request/cancellation guards. Place initial charge marks away
  from incident bonds and unify actionable missing-RDKit installation messages.
- Separate atom-label picking from document margins so nearby bonds and attached
  charge marks remain editable. Charge shortcuts cancel an opposite mark or
  place a non-overlapping new mark; Mark preview and click share their binding.
- Record exact selection geometry for nudge/alignment Undo/Redo and preserve
  existing perspective depth through 2D transforms. Batch selection refreshes
  during movement and paste. Preserve exact independent-mark offsets on drag
  Undo, and restore the existing savepoint when a drag returns to its origin.
- Resolve all Quit prompts before closing windows and preserve the final complete
  session list. Keep restored untitled names distinct, retain the recovery notice
  through startup, and reuse blank drawings for File Open / Open Recent. Warn
  about abandoned snapshots in alternate app-data locations without consuming them.
  Decline new OS file opens during Quit; imported nonempty drawings are not reused
  as blank windows. After all close prompts are accepted, remember saved paths
  without requiring a new snapshot of discarded drafts or stale calculation plans.
- Enforce figure-export size budgets for default and column presets as well as
  explicit limits. Keep embedded PNG/JPEG text metadata out of rendered SVG
  images while preserving the original bytes in editable documents. Use custom
  PDF page sizes and fit painting to their rounded dimensions.
- Keep bond ends outside the open interiors of atom-label glyphs such as C, N,
  and H without using the labels' picking padding as drawing geometry.
- Preserve overlapping atoms when opening, pasting, or inserting SMILES, so an
  imperfect agent-produced drawing remains editable instead of losing atoms or
  failing to open. Undo/Redo preserves the inserted and original graphs.
- Confirm before saving over a file changed externally, or over the original
  path of a recovered drawing with no verified saved-file baseline. Preserve
  unreadable recovery snapshots for investigation and open additional dirty
  recoveries of one path as unbound copies.
- Make calculation-plan edits undoable and failure-atomic. Opening the editor
  no longer replaces a topologically stale plan; shared-state charge corrections
  are supported, no-op edits preserve order and reviews, identical endpoint IDs
  are rejected, and mapping-table construction avoids repeated document scans.
  Saving an inconsistent or stale plan now asks before writing or omitting it.
- Preserve projected depth when Graph Patch moves an atom; remove only ring
  fills invalidated by a removed cycle edge. Trim created/updated element labels
  and reject composition control points on non-curved arrows.
- Regenerate wedge/hash directions after abbreviation-expansion layout, preserve
  remaining implicit hydrogens on partially explicit heteroatoms, and normalize
  redundant MOL valence fields only when RDKit confirms an unchanged molecule.
  Racemic CXSMILES flags, all supported dotted contacts (including outer double
  variants) at chemical-conversion boundaries, and
  unsupported multiple-bond abbreviation attachments are rejected explicitly.

## [0.12.0] - 2026-09-11

### Added

- Korean versions of the user and contributor guides: the reference, CLI,
  scheme-layout, publication and image-objects guides, the media, examples and
  packaging READMEs, and CONTRIBUTING, RELEASING and the code of conduct now
  each have a `.ko.md` twin linked from the top of the page, with the same
  figures, GIFs and diagrams and with every command and example kept verbatim;
  the Korean README points at the Korean guides.
- Figures and diagrams in the guides: the CLI guide opens with a flowchart of
  how the commands chain and shows the composition, template-insertion and
  Graph Patch examples rendered; the scheme-layout guide shows arrange, align-y
  and wrapping before and after, plus an Arrange Scheme walkthrough GIF; the
  publication recipe shows its three output figures; the image-objects guide
  opens with an Insert Image / Image Properties walkthrough GIF; the
  architecture guide gains a layer diagram and a render-flow diagram.
  `scripts/render_doc_figures.py` regenerates the figures from the documented
  commands.
- Four short walkthrough GIFs in the reference guide, captured from the
  application: drawing a structure, arrows and labels, select/move/rotate/align,
  and chemistry I/O. `scripts/capture_walkthroughs.py` regenerates them on the
  harness the first-scheme capture now shares.

### Changed

- Shorten both READMEs to a front page: what Chemvas is, install, the first
  reaction scheme, three script commands and where the documentation lives.
  The feature narrative and the CLI option walkthrough now live only in the
  linked guides.
- Close the blank gaps between the top toolbar's button groups (after
  Brackets and after Orbital); the tool buttons now form one continuous row.
- `OH`, `NH2`, and `SH` labels must carry exactly one single bond (wedge or
  hash allowed) and no charge or radical mark. A document that breaks this
  rule is now rejected by `inspect`, `inspect-document`, `compose-document`,
  `insert-template`, `apply-patch`, `attach-plan`, `pack-step`, and the
  Calculation dialog, where 0.11.0 accepted it. Use an element label for a
  charged or radical atom.
- Recapture the first-scheme walkthrough GIF, still and example exports
  against the current interface, where the SMILES field sits on the Ring
  tool's options bar; the walkthrough script chooses that tool first. The
  example drawing itself is unchanged; its SVG and PNG are re-exported with the
  current bond-to-label clearance.

### Fixed

- Preview an inserted SMILES structure as it will actually be drawn. The
  hover ghost is now the real canvas rendering of the converted model at half
  opacity, so ring double bonds sit inside the ring, heteroatoms show their
  labels and bonds stop short of them; previously the ghost drew every atom
  as a dot and every double bond as two full-length parallel lines.
- Show the structures of a reopened document that also contains embedded
  images on the first paint of a native window; on macOS they could stay
  invisible until the selection changed. Images are now restored before the
  molecular graphics.
- Remember the last confirmed Export Figure format within each window; cancelling
  the options dialog leaves the previous format selected for the next export.
- Keep the status-bar drawing hint current: restore it when a toolbar status
  tip or timed message clears, and refresh it when keyboard shortcuts or
  Select All change the active tool.
- Calculate Molecule Info identifiers for neutral terminal `OH`, `NH2`, and `SH`
  labels. `NH2` and `SH` join the alias table, so the 3D preview, XYZ export,
  and calculation handoff accept them as well; the attachment rule these three
  labels now enforce is listed under Changed.
- Export Figure writes the chosen format under a matching file extension. A
  name typed with a different format's extension (`figure.pdf` while the dialog
  is set to SVG) is retargeted to the format being written instead of leaving
  the other format's bytes under a misleading name; replacing an existing file
  under the corrected name is confirmed first. Extensions that name no export
  format are still left alone.
- Explain a failed Export Figure write in the dialog: a missing folder, a permission
  refusal, or a full disk are described in place of the raw errno text and the
  temporary staging path the user never chose.
- Correct the reference guide's SMILES entry instructions to use the Ring
  options bar, and drop the first-scheme guide's note that PyPI 0.8.1 lacked
  the arrow-label outlining fix.

### Removed

- The preview-geometry API of the SMILES insertion feature, superseded by the
  rendered preview picture: `SmilesPreviewGeometry`, `SmilesPreviewPlan`,
  `SmilesPreviewSnapshot`, `build_smiles_preview_geometry`,
  `build_smiles_preview_snapshot`, `plan_smiles_preview_update`, and
  `snapshot_smiles_preview_geometry` from `chemvas.features.insertion`;
  `smiles_preview_snapshot` and `apply_smiles_preview_geometry` from
  `chemvas.ui.preview_scene_renderer`; `apply_smiles_preview_geometry_for`
  from `chemvas.ui.preview_scene_access`; the `smiles_preview_snapshot`
  methods of `InsertController` and `InsertSmilesService`; and the
  `smiles_preview_bond_items` and `smiles_preview_atom_items` fields of
  `CanvasInsertState`, replaced by `smiles_preview_picture`.
  `clear_smiles_preview` and `clear_smiles_preview_for` now return an empty
  list, the replacement item pool, instead of the old three-tuple; the
  removed items are not handed back.
- `TOOLBAR_GROUP_GAP_PX` from `chemvas.ui.main_window_panel_toolbar`, together
  with the toolbar group gaps it sized.

## [0.11.0] - 2026-09-10

### Added

- Embed original PNG and JPEG images using **File ▸ Insert Image…**, clipboard
  paste, or `compose-document`. Move images with the selection tool and edit
  their size, original aspect ratio lock, and opacity in
  **Edit ▸ Image Properties…**. Native documents and editable SVG retain the
  source bytes; figure exports include the complete raster. The document format
  stays version 7: a drawing without images opens in any Chemvas as before, but
  a drawing that contains an image is rejected by Chemvas 0.10.2 and earlier.
  See [image objects](docs/IMAGE_OBJECTS.md) for limits.
- Turn a selection by dragging the rotation handle above its frame. The frame
  appears around two or more selected atoms or a rotatable arrow, line, or
  orbital; hold Shift to snap the sweep to 15° steps. The selection turns about
  the same centre as **Edit ▸ Rotate…**, the drag undoes as one step, and
  Escape cancels it.
- Export one document to a single-page vector PDF with `render-document`.
  It reuses the desktop PDF exporter, keeps the physical size, leaves the
  source untouched, and refuses to overwrite an existing output. `--dpi` sets
  the PDF paint resolution; PDF bytes are not reproducible across runs because
  Qt writes identifiers and timestamps into the metadata. `--min-font-pt`
  remains SVG and PNG only.
- Add **File ▸ Close Window** with the platform's standard shortcut (Command-W
  on macOS), keeping the existing save, cancel and shutdown handling.

### Changed

- Group the status bar's zoom controls into one outlined pill.
- Fold the rarely used arrow kinds (favoured equilibria, inhibition and the
  three arcs) into one menu button on the Arrow options bar that shows the
  kind picked last, so the everyday kinds get room.
- Move the SMILES field and its Insert button from the top toolbar to the
  Ring tool's options bar, beside the ring templates; Insert is now an
  outlined button like the bar's other actions.
- Move flip, rotate, align and distribute into the Select tool's options bar,
  which also opens for the Perspective tool and for **Edit ▸ Rotate…**, which
  now switches to the Select tool; the top toolbar now holds only drawing
  tools. Tools without options leave the bar empty instead of showing a hint.
- Redraw the toolbar icons in one line language: the atom tool is an A, the
  text tool a T, the ring tool a benzene hexagon, the orbital tool an upright
  p orbital, the mark tool a plus over a minus, and the line tool a segment
  with its two ends. Icons render larger (20 px in the toolbar, 18 px in the
  options bar) and the active tool keeps its tinted, outlined pill.
- Set the top toolbar's button groups apart with a gap instead of a
  divider line.
- Draw every selection as one thin outline in the accent colour instead of a
  translucent fill: bonds get a band that follows them, labelled and lone
  atoms a rounded box or ring, arrows, marks, shapes and orbitals an outline
  around their shape, and notes a solid box. The drawing keeps its own
  colours while selected; arrows and shapes are no longer recoloured or
  thickened. Group boxes stay dashed.
- Handles are hollow circles that keep their size on screen at any zoom
  (edge-midpoint resize handles are smaller than corner and endpoint handles).
  A handle that has taken another item's endpoint is still shown filled.
- Tint the hover ring with the selection accent instead of grey.
- Raise the `.chemvas` document limit from 8 MiB to 96 MiB for
  `compose-document`, `render-document`, `check-layout`, `arrange-scheme` and
  clipboard payloads, so embedded images fit; editable SVG accepts a 256 MiB
  file with a 96 MiB native payload. Desktop **File ▸ Open…** and session
  restore, which had no size cap before, now apply the same 96 MiB limit.

### Fixed

- Explain failed height limits with the measured output height and desktop
  controls while preserving existing files and command-line diagnostics.
- Measure PDF height limits against the native page geometry, including
  whole-point rounding and standard-paper matching.
- Keep unchecked checkboxes visible against the desktop dialog background,
  including when an export option is unavailable.
- Explain failed minimum-font export checks with measured sizes and corrective
  actions in the desktop dialog while preserving command-line diagnostics.
- Report unrecognized command names before starting Qt. Reject unrecognized
  desktop arguments after Qt consumes its options, before opening a window or
  restoring a session.
- Show Chemvas in the macOS application menu when launched through the standard
  framework Python bundle. Preserve names supplied by other application bundles.

### Removed

- `SelectionHighlightStyler` and `selection_highlight_styler_for`
  (`chemvas.ui.selection_highlight_styler`), `selection_highlight_styler_for_access`,
  the `set_selection_highlight`, `clear_selection_highlight` and
  `apply_selection_style` methods of `CanvasHandleController`, and the
  `selected_highlight_items_for`, `set_selected_highlight_items_for` and
  `selection_stroke_delta_for` accessors with the `selected_items` and
  `stroke_delta` selection-style fields: selections are outlined, no longer
  restyled.
- `SMILES_RENDER_BUTTON_STYLE` from `chemvas.shell.theme` and
  `chemvas.shell.toolbar_styles`; Insert uses the options bar's action style.
- `build_rotate_page` and the `rotate` options page, replaced by
  `build_select_page`. `build_template_page` now requires `begin_smiles_insert`;
  `build_panel_toolbar` drops its `create_toolbar_button`, transform controller
  and insert controller arguments, `MainWindowUIAssemblyService` drops the
  latter two; `create_handle_item` drops `size` and returns an ellipse item.

## [0.10.2] - 2026-09-09

### Added

- Add a local Windows x64 installer build with per-user installation, a Start
  menu shortcut, and `.chemvas` Open with registration. Preserve existing
  default-app choices and saved drawings on uninstall.
- Bundle a console companion, `chemvas-cli.exe`, alongside the windowed desktop
  executable. Direct console commands sent to the windowed executable to the
  companion with a visible notice. Public signed installers are not released yet.

### Fixed

- Keep equilibrium-arrow shafts compact relative to their stroke width and
  bond spacing. Match the equilibrium toolbar icons to the canvas geometry.

## [0.10.1] - 2026-09-09

### Added

- Check native sheet containment without pairwise collision work using
  `check-layout --sheet-only`. Reports explicitly distinguish boundary-only
  results from collision checks and retain document-size and record limits.
- Bind the publication examples' layout checks and exports to the same saved
  drawing bytes, retaining the layout report hash in each figure manifest.

### Fixed

- Include visible molecular structures, arrow bodies, marks, ring fills,
  orbitals and TS brackets in the shared sheet-boundary diagnostics. Keep normal
  Save/Open and all native coordinates unchanged; physical export sizing does
  not stand in for a drawing that fits its editable sheet.

## [0.10.0] - 2026-09-09

This release adds explicit comparison-layout controls and corrects abbreviation
attachment placement. The `.chemvas` document format remains version 7.

### Added

- Choose named note roles in Arrange Scheme instead of guessing captions from
  their positions. Compare explicitly named row groups and optionally place
  caption stacks close to their individual structure blocks.
- Apply an explicit color to chosen reaction arrows and their attached labels
  through the shared GUI/CLI layout path, retaining other drawing styles.
- Provide a small-format, native comparison example with complete reaction rows
  and explicit labels, without inferring chemistry or deleting content to fit.

### Fixed

- Keep the attachment glyph of reversible abbreviations such as OMe/MeO on the
  bonded atom for vertical and steeply angled bonds, rather than centering the
  whole label. Preserve typed order for a vertical bond and reuse directional
  display reversal for left/right approaches without changing the stored label.
- Include attached arrow-label ink in layout collision diagnostics and their
  pre-Qt work budget. Report diagnostic coverage separately from publication
  readability and semantic design review.

## [0.9.0] - 2026-09-09

This release adds explicit scheme layout and print-size controls for publication
figures. The `.chemvas` document format remains version 7.

### Added

- Arrange explicit structure/caption blocks with `layout-document`, using native
  painted text bounds, aligned caption baselines and persistent GUI groups.
  Optional row-width budgets wrap complete blocks and continuation arrows.
- Arrange existing structure/caption groups from **Edit ▸ Arrange Scheme…**, with
  explicit row/order/arrow choices, optional wrapping and single-step undo/redo.
- Align molecular drawings only with `layout-document` mode `align-y`, preserving
  X coordinates, notes and groups. Explicit parts and reference blocks control
  independent fragments and the molecular reference.
- Insert native regular-ring, benzene, chair and boat templates through
  source-pinned `insert-template`, with dry-run and non-overwriting output.
- Set a specified ordinary terminal bond angle with Graph Patch
  `set_terminal_angle`, preserving bond length and rejecting unsupported stereo.
- Request physical export widths and optional height limits in the CLI and
  **Export Figure**. Check final printed glyph sizes, including scripts, for
  whole-canvas SVG/PNG without changing the source fonts.
- Detect visible atom-label–nonincident-bond and attached-charge–bond ink
  overlaps, including charge contact with its own incident bond.
- Provide a reproducible publication recipe with native ring metadata, real
  scripts, common nominal print scale and measured SVG/PNG font reports.

### Fixed

- Scale bond-to-label clearance with the actual painted pen width and leave a
  proportional visible gap, including ordinary, parallel, wedge and hashed bonds.
- Use native rich-text glyph geometry for note SVG and PNG exports, including
  mixed point/pixel fonts and scripts, with pixel-resolved list markers.
  Preserve the editable note HTML and fonts in the document.
- Choose fresh stereobond hatch counts from the label-trimmed visible stem to
  reduce crowding at compact figure scales. Canvas and export use the same count.

## [0.8.4] - 2026-09-08

### Added

- Report visible atom-label overlaps with notes or other labels and painted
  arrow-to-structure crossings in layout diagnostics, with bounded preflight work.
- Compose native TS brackets and bounded mixed-format note runs, including
  subscript and superscript text, without accepting arbitrary HTML.
- Preserve per-arrow colors through document and clipboard round trips and
  geometry edits. Documents containing the new optional color field require a
  Chemvas build that supports it.

### Fixed

- Trim bonds to the painted atom-label outlines with a small stroke-aware gap,
  rather than the empty text-box margins, without shrinking selection targets.
  Account for parallel strokes and filled bond widths so compact endpoints do
  not cross letter shapes or subscripts.
- Route Edit menu commands to focused single-line text inputs such as the
  SMILES field. Show the input's text Undo/Redo availability instead of the
  drawing history while editing text.
- Show platform-native shortcuts and text-aware descriptions in the clipboard
  menu hints.
- Refresh the unsaved-change indicators immediately after changing the canvas
  orientation.
- Open MOL files supplied on the command line through the same document-loading
  path used by the desktop app.
- Ask users to select a molecular structure before opening the MOL export save
  dialog when the canvas selection contains no structure.

- Render atom labels with their individual stored colors after restoration and
  label updates, rather than resetting them to the global text color.
- Derive composed curved-arrow heads from their kind when the `double` flag is
  omitted, and reject a contradictory explicit flag.
- Report the arrow index and label field for invalid composition labels, with
  guidance to omit unused sides, instead of a generic invalid-file error.

## [0.8.3] - 2026-09-08

This maintenance release fixes group movement after Redo and window feedback,
and makes reaction-condition editing easier to check. The `.chemvas` document
format remains version 7; existing supported documents do not need migration.

### Fixed

- Restore complete group selection after Undo/Redo before the next drag, so a
  pasted ring and its sidechain move together with the group's annotations.
- Keep tool, selection, and zoom feedback attached to the destination window
  when opening a document in a new window.
- Update the status bar's document name and unsaved marker after saving,
  renaming, editing, and Undo/Redo without replacing the current feedback message.
- Initialize headless Qt with its platform default font family, avoiding the
  missing generic-font warning when checking layouts on macOS.

### Changed

- Preview arrow labels while typing and explain explicit subscript and superscript
  ranges with chemical-formula examples.
- Show how to edit arrow and line labels, and how to enter and finish note editing,
  in the drawing tool hints.

## [0.8.2] - 2026-09-07

This maintenance release improves selection and text-editing workflows, preserves
copied groups, and keeps arrow-label typography intact in vector exports.
The `.chemvas` document format remains version 7. Grouped clipboard payloads
include membership that older versions may reject; use matching versions when
copying groups between running instances.

### Fixed

- Preserve note spacing, tabs, and empty paragraphs through document Undo/Redo
  and save/open without allowing external stylesheets or resource loading.
- Clear pasted/group-selected notes when clicking empty canvas or selecting a
  different object. Notes and shapes now move on the first selection drag.
- Move notes-only groups together from the first press on either member,
  including after selecting another object, with one-step Undo and Escape cancel.
- Keep copied groups independent of the originals, including mixed structures
  and annotations, with paste and its group membership in one Undo step.
- Switching away from Text commits the current note and returns keyboard/Undo
  input to the drawing. Text Undo no longer crosses completed editing sessions;
  undoing an emptied note also restores its text. Mouse drag and Shift-click
  select text naturally, and unsaved markers update while typing or formatting.
- Lines and arrows can be selected near their strokes and dragged on the first
  press. A small wobble during a click no longer moves them or adds an undo step;
  curved arrows no longer treat their interior as a filled click target. Picking
  uses a screen-space margin without changing the drawing or exported stroke width.
- Arrow labels now export as glyph outlines, retaining the canvas's text sizing
  and subscript/superscript positions in SVG figures and vector clipboard copies.
  The editable document and on-canvas label editing are unchanged.

### Changed

- Escape cancels active drawing/drag gestures and returns to Select. In a note,
  it commits the text and leaves editing so drawing shortcuts work again.
- Refocused the introduction and branding on reaction schemes, figure export,
  and scriptable document workflows, with a first-scheme tutorial and an editable
  example. Toolbar hints now describe shortcuts without a product comparison;
  the key bindings are unchanged.

## [0.8.1] - 2026-09-07

This maintenance release fixes SMILES bond-type handling, perspective movement,
and note selection counts, and consolidates editor and export responsibilities.
The `.chemvas` document format remains version 7 and Calculation Plan remains
version 2; existing supported documents do not need migration.

### Fixed

- Reject SMILES with unrepresentable bond types instead of silently converting
  dative, unspecified, or higher-order bonds into ordinary single/triple bonds.
- Preserve drawing perspective coordinates when moving a rotated structure, so
  subsequent rotation and clipboard operations keep its depth information.
- Count a selected note once when both Qt selection and note-selection state
  refer to it, including after paste and group selection.

### Changed

- Document replacement and scene reset use the history service's stack policy.
  Recorded structure builds retain their pre-build savepoint through history
  recording, and benzene template insertion no longer nests recorded builds.
- Figure-export preflight and rendering share plan resolution. Perspective
  rotation, movement, and clipboard placement share projection geometry.
- Arrow creation and curved-path editing share path/head construction, and tool
  menu actions carry kind IDs instead of deriving behavior from display labels.
- Calculation validation and reporting reuse a request-local component inventory;
  step editing shares duplicate-step and reviewed-precomplex retention rules.
- Architecture checks scan the current UI package and reject empty inventories.
  Eager-import checks resolve imported modules consistently, and tests that only
  called their own mocks have been removed while real delegation checks remain.

## [0.8.0] - 2026-09-07

This release makes the endpoint snapping 0.7.0 introduced usable. The catch
is measured on screen rather than in the document, so it does not shrink as
the view zooms out; a mark says when an end has been caught; and carrying an
existing line onto another's end now joins them, which is how a scheme
assembled from pieces actually gets built.

The `.chemvas` document format is unchanged at version 7. No kind and no key
is added, so a document written here opens in 0.7.0 and one written there
opens here.

### Added

- Moving an arrow or line, or a selection containing one, now connects it:
  carrying an end within reach of another item's end joins them exactly and
  rings the meeting point, and carrying on past it leaves the drag where the
  pointer is. Drawing already snapped; assembling a scheme by moving pieces
  did not, so the ends never actually met.

### Changed

- The endpoint snap reaches twelve pixels from the cursor at any zoom.
  It was a fixed fraction of a bond length, which is eight pixels at the
  default zoom and fewer as the view zooms out, so a connector had to be
  released almost exactly on the endpoint to take it. A ring on the
  drawing preview now marks an end that has taken an existing endpoint,
  and an endpoint handle sitting on another item's endpoint is drawn
  filled rather than hollow.

### Removed

- Removed `snap_to_arrow_endpoints_for`, which the drawing snap funnel had
  replaced and which nothing outside its own module called, and
  `ENDPOINT_SNAP_FRACTION`, the fraction of a bond length the catch used to
  be measured in.

## [0.7.0] - 2026-09-07

This release is a set of drawing tools for kinetic and energy schemes: lines
that are not bonds, rate-constant labels, favored-direction equilibrium
arrows, arc arrows, endpoint snapping and endpoint drag handles, align and
distribute, and a snap-to-grid view option.

The `.chemvas` document version remains 7, and a drawing that uses none of the
new kinds still opens in 0.6.1. One that uses any of them does not: earlier
releases check an arrow's kind against a closed list and its keys against a
closed set, so the twelve new kinds — four line styles, six arcs, two favored
equilibria — and the optional `labels` key are each rejected.

### Added

- View ▸ Snap to Grid draws a faint grid of half a bond length on the sheet and
  snaps the points the Line and Arrow tools place, and the ends dragged with
  endpoint handles, curved arrows included, onto it. An existing endpoint
  still takes precedence, and the Shift angle lock outranks the grid; a click,
  and a drag shorter than one grid step, both read as a click. The grid is left
  unpainted while it would be too dense to read. The setting belongs to the
  canvas rather than the document, so each window keeps its own and it is not
  saved.
- Selecting an arrow or line and clicking it now shows a handle at each
  endpoint; dragging one moves that end, snapping to nearby endpoints, and the
  whole drag undoes in one step. Arcs keep their sweep and equilibrium arrows
  their harpoons, labels follow, and a drag that would shrink the item below a
  tenth of a bond length is refused. Curved arrows keep their existing control
  handle, and their endpoint handles snap and refuse a collapse the same way.
- Edit ▸ Align and Edit ▸ Distribute line up or evenly space the selected
  structures and objects in a single undoable step. A molecule moves whole
  even when only part of it is selected, and a group moves as one object.
- Arc arrow kinds (`arc_90_left`, `arc_180_left`, `arc_270_left` and their
  `_right` mirrors) draw circular arcs through the drag endpoints for
  catalytic cycles; holding Shift while dragging bulges the arc to the other
  side, and a mirror flip keeps the mirror image.
- Arrow and line endpoints snap to nearby arrow and line endpoints while
  drawing, and a Line-tool click without a drag places a horizontal level two
  bond lengths long.
- Arrows and lines can carry a label above and below, such as the rate
  constants of a kinetic scheme. Double-clicking the arrow opens a two-field
  dialog; `_` and `^` mark subscripts and superscripts, and braces group
  several characters. Labels are stored in the arrow's document state under an
  optional `labels` key, move with the arrow, and survive undo, copy, flip and
  rotation.
- Two equilibrium arrow kinds, `equilibrium_forward` and `equilibrium_reverse`,
  draw the disfavored harpoon at half length so a scheme can show which
  direction is favored.
- A Line tool draws plain, dashed, wavy, and bold lines that are not bonds, for
  energy-level diagrams and connectors. Holding Shift locks the drag angle to
  15° steps. Lines are saved as four new kinds in the document's arrow list.

### Removed

- Removed the two `RDKitAdapter` strict-label conversion methods and the
  unused unsupported-bond-style option of the tolerant builder; only the tests
  called them. Molecule Info identifiers, MOL/XYZ export and the 3D preview
  already go through the stereo-aware conversion builder, and atom-mapping
  suggestions keep the tolerant builder.

## [0.6.1] - 2026-09-05

### Fixed

- SMILES insertion now preserves absolute tetrahedral stereochemistry as
  wedge/hash bonds and refuses specified stereochemistry the canvas cannot
  represent. Molecule Info identifiers now use the same stereo-aware conversion
  as the 3D preview, while retaining the element-only identifier policy.
- Undoing deleted notes now restores their registry and equal-z stacking order,
  including grouped notes, so an otherwise unchanged document stays clean.
- Deleting atoms now retains their original charge/radical mark items for Undo,
  preserving order, grouping and appearance when mixed with standalone marks.
- Layout QA now intersects actual shaped text glyphs instead of note hit boxes,
  avoiding overlap warnings for whitespace between visible letters. Rich-text
  backgrounds, decorations and super/subscript positions remain part of the
  checked paint geometry, including wrapped and bidirectional text runs.
- Rich-text layout checks skip undecorated fragment scans and inspect only
  intersecting lines for decorated fragments in long wrapped paragraphs.
- Molecule Info now pauses 3D work when its window is closed, closes without
  blocking on an active RDKit preview, and no longer leaves the main Qt object
  tree for nondeterministic QApplication teardown or truncates the last-window
  session snapshot during the deferred close.
- Help > Chemvas on GitHub now uses the WSL browser bridge when available,
  instead of silently accepting Qt's unsuccessful Linux browser dispatch.
- Deleting and restoring atom charge or radical marks now keeps the chemistry
  model and selection information synchronized, including undo and redo.
- Calculation handoff now omits UI values from locked endpoints and constrains
  structure-based mapping suggestions with reviewed atom correspondences.
- Atom-label layout now follows pasted and edited bond geometry, preserves
  isolated-label typing order, treats lowercase carbon labels consistently,
  and keeps mapping identifiers clear of visible atom glyphs.
- Layout QA now honors dashed strokes and skips fully transparent shapes, while
  version 7 documents retain legacy font sizes above the current authoring cap.
- Explicit Note-tool selection now expands mixed groups, and changing away from
  the Select tool clears stale resize and rotation handles.
- Transaction rollback now remains available after a failed savepoint release
  and preserves equal-z scene ordering in scoped snapshots.
- Packaged documentation now uses PyPI-safe links and identifies RDKit as a
  calculation-handoff dependency; the modularization ADR now distinguishes
  local checks from CI smoke jobs and reports the measured Qt-import ratio.

## [0.6.0] - 2026-08-30

This release combines correctness fixes for document ownership, crash recovery,
headless Calculation Plan validation, and the test gate with a consistency pass
over the whole codebase — lint and type enforcement, one owner per convention,
and the 3.12 idioms the tree was already reaching for.

Separately, twelve import paths moved as part of the consistency work; they are
listed below. The top-level `.chemvas` document version remains 7; the reviewed-
precomplex freshness basis changed as described under Fixed.

### Added

- The `chemvas.features.calculation_bundle` package root now exposes
  `ComponentInventory`, `inspect_component_inventory`,
  `precomplex_basis_sha256`, `validate_reviewed_precomplex_pair`, and
  `validate_reviewed_precomplex_pairs`. The `chemvas.features.session` package
  root now exposes `is_valid_process_identity`, and the
  `chemvas.domain.transactions` package root now exposes `run_rollback_step`.

### Fixed

- Save As now refuses a destination already owned by another live canvas, and
  opening a symlink or hard-link alias activates the existing document instead
  of creating an independently editable copy. Saving through a symlink updates
  its resolved target without replacing the link itself; saving an existing
  hard-linked target is refused because atomic replacement would split its names.
  On macOS, identity comparison respects whether the containing volume is case-
  sensitive, so case-distinct files remain distinct where the filesystem does.
- Crash recovery now binds a session to both its PID and process-creation
  identity, so a recycled PID owned by an unrelated process no longer hides the
  crashed session. The manifest remains strict version 1 for concurrent older
  binaries, while a separate owner sidecar carries the new identity; legacy or
  unreadable identity metadata retains the conservative PID-only policy. A
  malformed or unreadable manifest is preserved when the owner sidecar cannot
  prove it orphaned; an old session is pruned only when valid owner evidence
  proves that its process ended or its PID was reused.
- Graph Patch refuses to publish a document when a reviewed precomplex pair
  becomes stale. `inspect-plan` now reports stale or non-atomic reviewed pairs as
  blocked with stable reasons, using the same validator as selection and
  `pack-step`. That validator also binds both endpoints to one source/environment
  provenance and includes the environment plus resolved charge/radical marks in
  the current basis, while display-only colors and label visibility remain
  editable. Precomplex candidates made with the older basis must be regenerated
  and reviewed before Graph Patch publication or `pack-step` handoff.
- Local and main-CI test discovery now includes nested `test_*.py` files instead
  of silently omitting them. `CHECK_JOBS=0` and other non-positive or malformed
  concurrency overrides are rejected rather than reaching `xargs` as unlimited
  parallelism; arbitrarily large positive values are safely capped at eight.
  Test files run concurrently in isolated processes, and nested paths receive
  collision-free failure logs.
- `inspect-document` builds one indexed component/bond/alias-attachment
  inventory instead of repeatedly scanning the full graph for each bonded
  component or atom.

### Changed

- The application chrome moved from `chemvas.ui.main_window_*` to
  `chemvas.shell`, dropping the prefix the package name now carries:
  `palette`, `stylesheet`, `theme`, `toolbar_styles`, `toolbar_buttons`,
  `icon_design` (was `main_window_design_icon_renderer`), `icon_factory`
  and `icon_pixmap_factory`.
- The graph algorithms, index operations and rotation policy moved from
  three `chemvas.ui.graph_*` modules to the `chemvas.features.graph`
  package.
- `chemvas.ui.scene_delete_logic` is now `chemvas.ui.scene_delete_plan`.
  It classifies live `QGraphicsItem`s, so the `_logic` suffix — which
  this project defines as Qt-free — was describing it wrongly.
- Tag-triggered publication now verifies that the tag matches the package
  version, its commit is contained in `main`, and that exact `main` commit has a
  successful completed push CI run before building distributions.

### Removed

- `RDKitAdapter.get_name_from_smiles` and the 18-entry SMILES-to-name
  table behind it. No production path called it.
- Twenty-two other forwarding methods that were unused outside tests and dead
  forwarding chains.

## [0.5.1] - 2026-08-27

Bug fixes only — no name on the public import surface changed. The one
change importers can feel is a narrowed signature, called out under
Changed.

### Fixed
- The text tool refuses to clear the symbol of a non-carbon atom. Deleting
  the prefilled symbol in the Atom Label dialog removed the label item but
  kept the element, so the drawing showed a bare skeleton vertex —
  indistinguishable from carbon — while SMILES, MOL, and every other
  export still carried the heteroatom. The empty input now fails with a
  message; entering C converts the atom, and clearing the label of a
  carbon atom hides it exactly as before.
- Hash (dashed stereo) bonds no longer keep a frozen mark count after a
  gesture that changed their length. Dragging or rotating a selection
  refreshes boundary bonds in place, deliberately reusing the existing
  items mid-gesture — but nothing ever re-derived the count when the
  gesture ended, so a stretched hash bond kept its original sparse marks
  through commit, undo and redo, and figure exports, while reopening the
  document rendered the same bond with the correct density. Gesture ends
  and history replay now rebuild a bond whose derived count changed;
  mid-gesture updates still reuse the existing items.
- Transform handles can now be grabbed where they overlap the structure.
  The press hit-test ranked atoms and nearby bonds above everything else,
  so a curved-arrow endpoint handle sitting on an atom label — or within
  the bond pick radius — could never be picked up: the click selected and
  dragged the molecule instead. Handles now take priority, matching the
  order they are drawn in.
- The 3D-rotate tool no longer swallows mouse releases that end no
  rotation. Marquee-selecting on empty canvas with the tool active left
  the dashed rubber-band rectangle stuck on screen until the next mouse
  move, because every release was consumed before reaching the view.
- SMILES insertion now rejects isotope labels instead of silently dropping
  them. The document model has no isotope representation, so inserting
  d2-ethanol (`CC([2H])([2H])O`) drew plain ethanol and `[13CH4]` drew
  plain methane — every formula, identifier, and export then described the
  unlabeled compound with no warning. Isotope-bearing input now fails with
  a message naming the offending labels, the same way the SMILES reader
  already refuses alias-shadowed element symbols and the MOL reader
  refuses the mass-difference field.
- The selection formula/MW readout in the status bar now accounts for
  charge and radical marks. It used to compute on a bare copy of the
  selected atoms that dropped the mark layer, so a drawn methoxide read
  CH4O / 32.04 — the neutralized skeleton with implicit hydrogens
  completed to neutral valence — while the 3D panel showed the correct
  CH3O- / 31.03 for the same selection. The readout now derives its
  charge/radical annotations from the same mark layer that MOL/XYZ export
  and the 3D panel read. Adding or removing an atom-bound mark refreshes
  the readout immediately even when the selection itself is unchanged, and
  the readout cache now keys on the selected content (elements, bond
  orders, marks) rather than the selected ids alone, so a label or mark
  edit under a held selection recomputes at the next refresh instead of
  serving the old value.
- Save As and the XYZ/MOL/figure export dialogs no longer overwrite an
  existing file silently when filename normalization changes the target.
  The dialog's own overwrite prompt checks the name as typed; appending or
  replacing the extension afterwards (`aspirin` or `aspirin.v2` becoming
  `aspirin.chemvas`) could redirect the write to a file the dialog never
  asked about, and the atomic writer then replaced it without warning.
  When normalization retargets the write to an existing file, Chemvas now
  asks before replacing it; a path the dialog already confirmed is not
  asked about twice.
- The 3D conversion path no longer exports the enantiomer of the drawn
  molecule. The conformer that RDKit reads wedge/hash chirality from was
  built on raw canvas coordinates, whose y axis grows downward; RDKit
  perceives depictions y-up, so every stereocenter came out with the
  opposite absolute configuration — silently, because the wedge-vs-hash
  difference survives a mirror flip. The conformer now negates y exactly
  like the MOL writer always has. This corrects XYZ export, calculation
  artifacts (both the geometry and its MOL block), the 3D preview, and
  the MOL-export fallback used when a drawing contains abbreviation
  labels, which previously disagreed with the plain MOL export of the
  same drawing. A regression test now pins the absolute configuration of
  both routes against each other and against fixed R/S references.

### Changed
- Removed the never-wired startup-file mode from the session-restore
  layers. Three layers of docstrings and tests described a policy where
  launching with a file suppresses reopening the cleanly-closed previous
  workspace — but no production caller ever used it, and the launch path
  has always restored the full workspace and then opened the requested
  file on top, as its own comment says is intended. Launch behavior is
  unchanged; the dead parameter, its docstring claims, and its pinning
  tests are gone, so the documentation now says what the app does. If you
  import `plan_restore` from `chemvas.features.session`, note that its
  `include_clean_session` parameter is gone — passing it now raises
  `TypeError`.
- The package-root surface guard now reads every module-level import binding
  — absolute and plain imports included, not only relative ones — so a
  removed re-export resurrected under an absolute spelling fails the guard
  the same way a relative one always did. Test change only; no import in any
  package root changed.
- Dropped an uncalled palette-menu method from the panel-toolbar test
  harness. Nothing has reached it since the production menu path went; the
  bans that keep that path removed are untouched.

## [0.5.0] - 2026-08-26

**If you import from `chemvas` in your own code, read the Removed section
first.** This release takes thirty-two names off the public import surface of
nine packages, and it changes what deleting a bond or an atom leaves behind on
the sheet. Everything else is bug fixes — see Fixed — and internal
housekeeping.

### Added
- Six names joined the public import surface: `SETTINGS_KEYS`,
  `VALID_ARROW_KINDS`, `connected_atom_components` and `included_atom_ids` on
  `chemvas.domain.document`, `fill_correspondence_gaps` on
  `chemvas.features.calculation_bundle`, and
  `selected_atom_ids_with_bond_endpoints` on `chemvas.features.selection`,
  which is the new name of a function listed under Removed. Nothing new was
  written: most of these are names the consolidation work below moved to a
  shared owner, which then had to be reachable from more than one module.

### Changed
- Corrected the module docstring on the graph index operations. Documentation
  only, nothing about the code changed — it called the whole module "pure"
  without saying what that meant, which read as side-effect-free even though
  the index helpers mutate in place the mapping they are handed. The docstring
  now says what "pure" is about here, namely what the module reaches: no Qt
  and no drawing surface, and no document type of its own — while recording
  that a neighbour it calls does pull the document package into the import
  closure. It also names the one operation that takes the whole graph state and
  writes a cache on it, with the reason its cache and its version have to
  arrive together.
- Removed five scene-access helpers, four of them called only by the test
  suite and the fifth stranded when those four went.
  Internal change only — no drawing, saving or exporting path reached any of
  them. Four of them wrapped a graphics-scene call the production code never
  made through this module: the whole-scene clear — which is not the live
  scene reset the document session, the canvas lifecycle and the SMILES insert
  all go through — the two item-group calls, and the canvas-scoped "can this
  item be added" probe. The fifth is the scene-scoped half of that probe: it
  lost its last caller with the probe and went in the same pass. The
  similarly named "is this item in the scene" pair stays, because the colour
  mutation service, the edit tools and the history commands still call it. A
  boundary test pins all five as removed, scoped to the module that defined
  them because the bare names read as prefixes of live surfaces elsewhere.
- Removed twelve orphaned glyphs from the design-icon SVG table. Internal
  change only — every icon the window, toolbars and context bars name still
  renders, checked by rebuilding the full reachable set (literal calls, the
  template label table, and every dynamically built arrow/preset/orbital/
  bracket/shape/stroke name expanded over its actual value domain). A render
  cannot carry that claim on its own — a name the table no longer holds draws
  the fallback glyph rather than raising — so the reachability rebuild is what
  it rests on. Eleven of the glyphs lost their
  last consumer when twelve icon accessors went; the twelfth, "select",
  turned out never to have had one — the select tool's accessor has always
  drawn the move glyph. A boundary test pins all twelve as removed.
- Folded the per-module bans on a vocabulary this repository never had into
  one repo-wide architecture rule. Test-only change; no production code moved
  and no rule lost a name. Eleven spellings of "ask the canvas for a service or
  a context by name" — `canvas_service_for` with its optional, runtime and
  optional-runtime variants, `resolve_canvas_graph_service`, the four
  context-cache lookups, `tool_context_for_canvas` and `canvas_instance_attrs`
  — were banned a target module at a time, though several of the rules carrying
  them already scanned the whole tree. Every blob in every ref was tokenised:
  not one of the eleven has ever been written anywhere in this repository, in
  any spelling, outside the rule file that bans them and this entry. A ban
  written one module at a time is a ban that can miss the next module, so it is
  repo-wide now. Five rules that carried nothing else are gone into it, one of
  them a call-shape rule the word-anchored ban strictly subsumes, and a sixth
  was renamed: it never had anything to do with `tool_context_for_canvas`, and
  its old title read as an instruction to write the name now banned. The rest
  keep the alternatives that guard something, and the context-cache rule keeps
  its check that the deleted module stays deleted.
  Verified by replaying the whole rule set before and after against a scratch
  copy of the tree, with no failure either way; by pulling every banned
  identifier mechanically out of both versions and confirming not one was lost;
  by planting each of the eleven names in every module an old rule named and
  confirming old and new both fail; by planting each of them in a module no old
  rule named, where `resolve_canvas_graph_service` and `tool_context_for_canvas`
  slip past every old rule and fail the new one; by planting a violation of what
  each of the twenty edited rules still guards and confirming each still fails;
  and, for the twenty-first, by resurrecting the deleted context-cache module.
  The file holds more identifiers with the same history of never having existed.
  They stay: splitting the ghost half out of the rules that carry them would
  break rules that read as one thought.
- Replaced every lambda in the structure-growth action record with the bound
  method it wrapped, finishing a conversion that had stopped at seven of the
  seventeen fields. Internal change only — every field forwarded its
  arguments unchanged, measured by calling each field through the record
  before and after with the same inputs. The ten lambdas that remained were
  load-bearing for the tests alone: nine tests in the structure-build suite
  swap a method on an already-built service, and late binding is what let the
  record see the swap. Those tests now rebuild the record through the same
  production wiring function once their mocks are in place, so each still
  asserts what it asserted before — that the growth path reaches the service
  method of that name with those arguments. The comment that explained which
  half of the record was which is gone with the split it described.
- Merged modules whose only production caller was a single other module into
  that caller. Internal structure only — nothing about how the application
  draws, saves or exports a document changes. The five main-window stylesheet
  sections (window chrome, canvas tabs, scrollbars, form controls and the
  status bar) each lived in their own module, and the only production code
  that read any of them was the module that concatenated them, so they now sit
  in it; the theme test reads all five individually and follows them there.
  The stylesheet the window is given is byte-for-byte the string it was
  before, and the theme test no longer reads the module's own source text to
  prove the sections have left it.
  In the same pass, nine functions in the insert access module that renamed
  another module's function and forwarded their own arguments to it unchanged
  are gone, and their callers now name the function they were always reaching.
  One of those callers had been importing the same function twice, once under
  each name.
- Removed guards that defended against states the code cannot reach, and
  narrowed two that were hiding real failures. Nothing about drawing, saving
  or exporting a document changes when the application is wired correctly —
  but when it is *not*, several operations that used to do nothing quietly now
  fail loudly. Session recovery keeps skipping a document it cannot read; the
  set of failures it treats that way is narrower now, and one it never
  recognised at all is covered (see Fixed). The internal service ports (across
  ten modules), the tool context's ports, the window and 3D-preview
  ports and the main window's status bar were all reached through capability
  probes that returned "missing" and let the caller substitute a silent
  default: a bond that was never sprouted, an arrow that was never added, a
  window that was never raised to the front, a 3D preview whose worker was
  never shut down. All of those were measured to resolve on a real assembled
  canvas and window when the change was made — no test pins the measurement —
  so the probes only ever absorbed wiring mistakes. They now
  raise where the mistake is, instead of producing a document that silently
  lacks what was asked for.
  Two swallows were narrowed rather than removed. A session snapshot that
  cannot be read is still skipped when the file is missing or corrupt, but a
  programming error in that path no longer masquerades as a corrupt document
  and drops unsaved work from the crash-recovery list. A failure to record a
  clean exit on quit is still tolerated when app-data is unwritable — the only
  cause it can have, and one whose consequence is the conservative one of
  offering recovery on the next launch — while anything else surfaces.
  Also folded in: the delete-tool session's port validation and its unwind
  (the session type makes every checked state impossible, while the rollback
  that legitimately leaves a session live still reports itself and is still
  retried), six defensive reads of a dataclass field that always exists (three
  more like them remain where the object handed in is not always that
  dataclass), three membership filters over ids that came from the model they
  were checked against, a CLI subcommand check argparse had already made, a
  "nothing to export" refusal duplicated in two modules, and a marker written
  into an exception's
  dictionary through four layers of indirection that cannot fail.
- Gave duplicated constants and helpers one owner each. This is internal
  housekeeping and changes nothing about how the application behaves. The
  arrow kinds are the part worth naming: the same seven strings were spelled
  out in seven modules besides the schema, so adding a kind to the document
  schema and missing one of the copies would have been silent — the document
  would accept the new kind while a scene, an outline, an attach route or a
  tool went on treating it as something else. All seven now read the schema's
  set, and the four supersets union it instead of relisting the members.
  Folded in the same way: the document-settings allowlist, a second copy of
  `normalize_3d`, a twice-compiled SHA-256 pattern, five one-line `getattr`
  wrappers (dropped in favour of the builtin), and three rollback helpers that
  had been pasted out longhand. Architecture tests fail if the arrow kinds, the
  settings allowlist, the SHA-256 pattern, a second `normalize_3d` or a
  function that only forwards to `getattr` is written again; of the rollback
  helpers only the colour note has a pin.
- Deleting a bond or an atom on the canvas now also deletes the atoms the
  deletion leaves invisible on the sheet. An endpoint or former neighbour that
  ends up with no
  remaining bond disappears with the deletion, in the same undoable step —
  unless a label or an attached charge/radical mark keeps it visible, in which
  case it stays. Erasing the only bond of a two-carbon fragment previously
  kept both atoms behind as invisible orphans; the eraser, the Delete key on a
  hovered bond or atom, and selection deletes — including Cut, which routes
  through the same delete — all clean up their newly bare invisible atoms now,
  and undo restores them together with the deletion. The headless
  `apply-patch` is deliberately not part of this: its `remove_bond` still
  leaves a bare atom, as `docs/AGENT_CLI.md` says it does.
- The source distribution no longer ships the test tree, and the release gate
  now verifies the sdist's contents the way it already verified the wheel.
  Every published sdist carried 300+ `test_*.py` files without `conftest.py`
  and the other support modules the default packaging glob skipped, so the
  shipped tests could never be collected. The wheel — what `pip install
  chemvas` installs — never carried them and is unaffected by the packaging
  change.
- Gave eight more duplicated algorithms one owner each, and deliberately left
  one where it was. Internal housekeeping again; nothing about the application
  behaves differently. The bond-cycle cache is the part worth naming: two
  functions answered "is this bond in a ring?" with identical code and both
  wrote the answer into the same cache, so the rule for when a cached answer
  goes stale was written twice and could have been changed on one side only.
  The survivor is `cached_bond_in_cycle`, which is new on that module.
  Folded the same way: three depth-first reachability walks, the
  capture-and-roll-back scaffold the group and ungroup history commands each
  spelled out twice, the pair of scene-item detach helpers, the eleven-key
  fingerprint that pins a reaction precomplex to the geometry it was built
  from, the ring-fill polygon rebuild the move controller kept a private copy
  of, the scene-item pool reset the preview and hover renderers each spelled
  out, and the atom-state restore the add-atoms and delete-atoms history
  commands each wrote twice. Each merge was checked against the code it
  replaced over the inputs that would expose a difference — random graphs,
  injected rollback failures, deleted scene objects — and none of them changed
  an answer. Architecture tests pin all eight and fail if one of them is
  written a second time; they were checked against the tree from before each
  merge to confirm they report the copies that were really there.

  What did not merge is recorded at both of its sites: the shared tail of the
  atom and bond delete paths was written as a shared helper, measured at 24
  net lines longer than the copies, and reverted. A fourth scene-item pool
  reset stays in `features.selection.handles`, which is in a layer that never
  imports `ui` and so cannot reach the owner, and says so where it sits. Both
  precomplex geometry checks were kept even though the second cannot fail when
  reached through the first, because the other caller reaches it without the
  first.
- The pull-request checklist now asks for one command, `make check`, instead of
  three hand-listed ones. `python -m ruff check .`, `python -m mypy` and a
  narrowed pytest run leave out `ruff format --check` and the `machine.json`
  conformance check, so a contributor could tick every box and still not have
  run the gate. In the same pass: `wheel` left `[build-system].requires`
  (setuptools carries `bdist_wheel` itself, and both build sites go through
  `python -m build`), the CI test job runs pytest directly rather than through
  a coverage wrapper that had no threshold and whose uploaded artifact nothing
  read, and the feature-request template stopped offering MOL export — which
  ships — as its example of a missing feature.
- Removed seventeen `CanvasStyleController` methods with no production caller.
  Setters and getters for text size, selection colour and stroke delta, text
  font, weight, italic and line spacing, and the note box's fill, alpha, border
  and padding were all reachable only from the tests; the panels and context
  bars that change those settings route elsewhere. Nothing on the sheet
  changes.
- Removed six `RDKitAdapter` methods that only the tests called —
  `model_to_rdkit`, `model_to_rdkit_with_map`, `model_to_rdkit_tolerant`,
  `suggest_atom_correspondence`, `model_to_3d_coords` and `model_to_3d` —
  together with the `tab_reactions_suspended` field and the two ports that
  carried it. SMILES insertion, MOL export and the 3D preview reach RDKit by
  other methods that stay.
- The contributing guide no longer restates the architecture discipline in its
  own words. `docs/ARCHITECTURE.md` is the normative text, `CONTRIBUTING.md`
  keeps the worked example, the list of patterns the boundary tests reject, and
  the steps for migrating a feature, and points at the rest.

### Fixed
- Every command that reads a JSON file now reports an oversized number as
  malformed input instead of raising a bare arithmetic error. JSON floats are
  parsed as `Decimal`, which fails in two different places: an exponent it
  cannot represent at all is refused by the constructor, while one inside that
  bound but past the arithmetic context's limit constructs quietly and raises
  the first time it goes through an arithmetic operation. Both failures are
  `ArithmeticError`s and neither is a `ValueError`, and neither was caught: of
  the loader's nine call sites eight guard `ValueError` and its neighbours and
  one does not guard at all, while the range check that rejects an oversized
  coordinate named `OverflowError` — which is `decimal.Overflow`'s sibling
  rather than its parent — around an `abs()` that raises the latter. So every
  headless subcommand that reads a document or a JSON input — `check-layout`,
  `compose-document`, `apply-patch`, `attach-plan`, `generate-precomplex`,
  `render-document` and the `inspect` family among them — exited with a Python
  traceback on some band of oversized numbers while refusing others cleanly,
  and the same values could escape when opening an editable SVG or pasting a
  selection. Both bounds now
  reject the value the way a duplicate key or a `NaN` already was.
- Session recovery no longer aborts the launch on a recorded document holding
  such a number. Recovery runs before the event loop starts and skips documents
  it cannot read; this release narrowed that skip from any exception to
  `OSError` and `ValueError`, which would have turned either arithmetic failure
  into a fatal one. A recorded session is only pruned once a recovery finishes,
  so the failure would have repeated on every launch.
- The headless commands that create a new file — `compose-document`,
  `apply-patch`, `render-document` and the calculation bundle writers — no
  longer close a file descriptor they have already handed away when the write
  fails. `atomic_create_bytes` gives the staging descriptor to `os.fdopen`,
  which closes it on its way out, and the failure path then closed it a second
  time with the resulting `EBADF` swallowed, so nothing surfaced. Had the
  process opened another file in between, that second close would have landed
  on the new file instead. The owner is now unambiguous: the handover has its
  own failure path, the one case where the descriptor is still ours, and
  nothing after it touches the number. Two tests cover the two sides; the
  first fails on the previous code. Saving from the editor goes through a
  different writer and was never affected.
- A failed ungroup now names the operation it was rolling back, instead of
  the opposite one. When a recovery step fails, a note attached to the error
  says which recovery was attempted; the ungroup command had both of its
  directions backwards, reporting "after grouping" when it had been
  ungrouping and "after ungrouping" when undo had put the groups back. The
  wording had been copied from the grouping command, where redo does group
  and undo does ungroup, so it followed the undo/redo slot rather than the
  operation. Only the text changes — no recovery step was added, removed or
  reordered.
- The Korean README's Agent CLI row now lists document composition and the
  layout check next to render, inspect and the hash-gated Graph Patch. Both
  `compose-document` and `check-layout` ship and the English README names them,
  so a reader of `README.ko.md` alone had no way to learn the CLI can build a
  document or report layout collisions without editing one.
- Documentation that was no longer true: `docs/images/README.md` described the
  README hero as a reaction scheme plus several organocatalyst structures,
  while the image in place is the C–P bond cleavage scheme under KOtBu / THF
  from `examples/template2.chemvas`, and it named the wrong capture file and
  regeneration command alongside it.

### Removed
- **The silent zero in the pick-radius accessors.** `atom_pick_radius_for`
  and `bond_pick_radius_for` used to answer `0.0` when the canvas could not
  supply a radius, which is a canvas on which nothing is clickable; both now
  let the failure surface. Like the other guards removed here, this only
  changes what happens when the application is wired wrongly.
- **The capture path's dormant non-strict mode.** `capture_scene_runtime` and
  `capture_atom_primitive_graphics` declared `strict=False`, but all 19 call
  sites in the tree — thirteen in production, six in the tests — pass
  `strict=True`, so the lenient half never ran. Nothing changes today; what
  goes is a mode that, had anything ever selected it, would have swallowed a
  capture failure in silence: `contextlib.suppress(Exception)` around a child
  or geometry read, `continue` past an item whose accessor raised, and
  assignments blanking the parent, stacking-depth, signal-blocking and focus
  port pairs. Each produced a partial snapshot that undo would then restore
  from, with nothing recorded to say a field was missing. The parameter is gone
  from the ten capture-side functions and the strict arm is now
  unconditional. Carrying that removal one step further,
  `_verify_scene_membership` was left forwarding its `strict` to a helper that
  ignores it, and `_direct_scene_remove` and `_direct_scene_add` only ever
  passed it on to that same dead end, so all three lost the parameter; four
  restore-side call sites drop the argument. What
  remains of the restore side keeps its flag — there it is genuinely dynamic,
  strict during a normal restore and best-effort while a rollback is already
  unwinding — so `_item_parent` and `_item_is_attached_to_scene` still take
  `strict=errors is not None`. The scene-item helpers keep the flag for a
  different reason: the rollback inside `create_scene_items_atomically` reads
  the scene leniently, by omitting the argument, so that a scene which can no
  longer answer does not mask the failure already being unwound.
- **Five parameter names their functions never read**, over six removal
  sites — two functions each lose the same session-state parameter.
  `tool_action_key_for_canvas_state` branches on the active tool alone, so
  `active_bond_style` and `mark_kind` go, and the toolbar sync no longer looks
  up the tool settings to supply them. That lookup was the last caller of the
  `tool_settings_for_window` window port, so the port goes as well, together
  with the constructor parameter carrying it into the tool state service and
  the composition-root wiring behind it. `tool_settings_state_for`, the
  canvas-level accessor it wrapped, is untouched and still read directly
  wherever the tool settings are actually needed. `begin_template_insert` and
  `begin_smiles_insert` ignored the session state they were handed and built a
  fresh one; their `cancel_*` siblings do read it and keep theirs.
  `apply_pasted_perspective_for_canvas` took a `projection_anchor_2d` it never
  used, taking the anchor from the canvas rotation state instead — the
  identically named field, and `projection_center_3d`, are both still read. The
  rotation preview's `restore` took the in-flight exception and ignored it; the
  rollback note it feeds is still added by the caller. No behaviour changes.
- **The last three hand-painted icon renderers.** `MainWindowBondIconRenderer`,
  `MainWindowUtilityIconRenderer` and `MainWindowToolIconRenderer` drew the
  toolbar icons until the SVG design set took over, and
  `MainWindowIconCanvasStyle` was the port that fed the bond one. Like the
  arrow renderer retired before them, the cutover dropped every call into the
  three classes but kept constructing them, so a second source of icon geometry
  stayed in the tree with nothing reading it. The modules, their construction,
  their tests, and the twelve icon accessors that no longer had a production
  caller are
  gone, and the modules join the list production code may not import again.
  `main_window_icon_geometry.py` and the two icon fill tokens the renderers
  were the last readers of went with them. No icon changes appearance.
- **Two tools that were never registered.** `TransformTool` and `EditBondTool`
  were complete `Tool` subclasses, but neither name appears in the tool
  registry `ToolController` builds, so no toolbar button, shortcut, or menu
  could ever activate them — only the tests constructed them. Both classes and
  the helpers they were the last caller of are gone:
  `show_orbital_handles_for` (the live rotate handles still come from
  `HandleOverlayService`) and `ToolContext.bond_id_from_event` (the
  identically named hit-testing service method stays, because the right-click
  context menu uses it). Nothing changes on the sheet.
- **Eleven snap-setting accessors with no caller.** `CanvasToolModeController`
  exposed setters and getters for curved-arrow snapping, curved-arrow
  symmetry and orbital-handle snapping, and a setter for the bond snap angle
  (which never had a getter), but no menu,
  toolbar, context bar, or shortcut ever called any of them. Two consequences
  are real, though both were already the state of the shipped application:
  curved-arrow midpoint snapping and orbital rotate-handle angle snapping are
  now permanently off — they defaulted to off and had no interface to turn on —
  and bond-angle snapping stays fixed at 30°, which is what it was set to
  everywhere. The `curved_symmetry` field, which nothing ever read, and the
  unused `TOOL_SETTING_ATTRS` tuple went with them; the four snap fields the
  handle code still reads stayed.
- **Ten `*_access` ports with no production caller.** `rebuild_graphics_for`,
  `scale_qpoints_to_bond_length`, `mark_offset_from_click_for`,
  `visible_label_rect_for_atom_for`, `mark_clearance_for_kind_for`,
  `label_cut_radius_for_atom_for`, `build_selected_structure_payload_for`,
  `selection_signature_for`, `add_benzene_template_for` and
  `bold_bond_width_for` each forwarded to a service the application already
  reaches directly — except `selection_signature_for`, which is a pure
  function, and `scale_qpoints_to_bond_length`, which wraps a domain function
  in Qt point conversion — so the wrapper was a second door nobody used. Two
  scene helpers, `clear_canvas_scene_item_map` and
  `clear_canvas_scene_item_list_map`, lost their only production caller with
  `rebuild_graphics_for` and went too. The live
  `renderer_bold_bond_width_for` — a different function with a similar name —
  is untouched.
- **Six service methods only the tests called.**
  `CanvasGraphService.atom_bond_order_sum`,
  `CanvasGeometryController.ring_for_bond`,
  `DeleteSelectionPlan.has_work`, `MainWindowStatusService.zoom_status_tip`,
  `MainWindowState.reset_canvas_name_counter`, and the
  `_snapshot_canvas_scene` module function are gone. The private helpers and
  neighbours they sat next to — `_ring_items_for_bond`, `has_zoom_label`,
  `_DetachedSceneSnapshot.capture` — are live and stay. The module-level
  `reset_rdkit_export_job_state_for_tests` wrapper went too; it was a second
  name for `RDKitExportJobRegistry.reset_for_tests`, which stays.
- **Exports and members nothing reads.** `compute_identifiers_for` (the access
  wrapper, not the live `compute_identifiers`), `TEXT_STYLE_ATTRS`,
  `CANVAS_TEMPLATE_FIELDS`, `DESIGN_ICON_NAMES`, `HEADLESS_SUBCOMMANDS`,
  `SceneDeleteController._restore_observer_ports`,
  `StructureBuildService.latest_bond_id` and `.viewport_center`, and the
  `hash_bond_width` and `wedge_width_px` fields on `ACS1996Style`. None of the
  ten had a production reader; the two style fields in particular never reached
  the
  renderer, so no drawn bond changes. The similarly named survivors —
  `_try_restore_observer_ports`, `viewport_center_scene_pos_for`,
  `renderer_bold_bond_width_for`, `CANVAS_TEMPLATE_TOOL_FIELDS`,
  `CANVAS_TEMPLATE_TEXT_FIELDS`, `has_design_icon` — are untouched.
- **The QMenu population path in `MainWindowToolRoutingService`.** Nothing in
  the application called `populate_template_menu`, `populate_arrow_menu`, or
  `populate_palette_menu`: the context bar page factories draw the same
  template, arrow, and palette entries directly. Following the cascade to its
  fixed point also retired `add_menu_action`, `palette_icon`,
  `template_entries`, `acs_color_palette`,
  `activate_arrow_type_from_menu`, `activate_arrow_preset_from_menu`, and the
  stranded `build_template_entries`. `apply_color_preset` and
  `apply_ring_fill_preset` stay — the panel toolbar routes through them — as do
  `ARROW_MENU_SPECS`, `ARROW_PRESET_SPECS`, `COLOR_PALETTE_SPECS`,
  `icon_arrow_preview` and `icon_template_preview`.
- **The canvas tab reorder wiring.** Each window holds a single canvas and the
  tab strip is hidden, so `tabMoved` was connected to a handler that discarded
  its arguments. The handler, the closure and parameter that carried it, and
  the `setMovable(True)` call are gone: canvas tabs are no longer marked
  movable. Nothing was reorderable in practice, since the strip is not drawn.
- **Thirty-two names off the public import surface of nine packages.** This
  narrows what `chemvas` offers to importers, so it is an API reduction rather
  than housekeeping: code outside this repository that did
  `from chemvas.features.rendering import DOUBLE_STYLE_SEQUENCE` has to import
  it from `chemvas.features.rendering.bond_style` now. Nothing inside the
  repository did — each was checked against every tracked file with no path or
  extension filter. Thirty-one appeared only in the package root that
  re-exported them and the module that defines them, and those thirty-one stay
  where they are and stay importable from the module named beside each below;
  only the package-level re-export goes. The exception is
  `selected_rotation_atom_ids`, which is not a re-export removal at all: it was
  renamed to
  `selected_atom_ids_with_bond_endpoints` and moved from
  `features.selection.rotation` to `features.selection.hit`, so the old name
  now resolves nowhere.
  Gone from `chemvas.domain.document`: `CALCULATION_INCLUSIONS`,
  `CALCULATION_PLAN_FORMAT`, `CALCULATION_PLAN_VERSION`, `CALCULATION_ROLES`
  and `CalculationEndpointPrecomplex` (all in `.calculation_plan`), and
  `SUPPORTED_FILE_VERSIONS` (in `.state`). From `chemvas.features.rendering`:
  `BOLD_DOUBLE_STYLES`, `BOLD_DOUBLE_STYLE_SEQUENCE`, `DOTTED_DOUBLE_STYLES`,
  `DOTTED_DOUBLE_STYLE_SEQUENCE` and `DOUBLE_STYLE_SEQUENCE` (in
  `.bond_style`), and `DEFAULT_BOLD_OUT_LENGTH_SCALE` (in `.bond_geometry`).
  From `chemvas.features.insertion`: `SmilesPreviewPlan`,
  `SmilesPreviewSnapshot` and `snapshot_smiles_preview_geometry` (in
  `.smiles`), `TemplatePreviewPlan` (in `.template_preview`), and the lazily
  loaded `ring_polygon_points_for_atoms` (in `.ring_occupancy`), which also
  leaves the lazy-export table. From `chemvas.features.selection`:
  `LineStrokePathBuilder` and `PenWidthGetter` (in `.outline`),
  `ROTATION_DRAG_SENSITIVITY` and `RotatePointAroundAxis` (in
  `.rotation_geometry`), and the renamed `selected_rotation_atom_ids`. From
  `chemvas.features.document_composition`: `COMPOSITION_FORMAT`,
  `COMPOSITION_VERSION` and `MAX_BONDS` (in `.service`). From
  `chemvas.features.calculation_bundle`: `PathPrecheck` and `StepReadiness` (in
  `.plan`). From `chemvas.features.document_patch`: `DOCUMENT_PATCH_FORMAT` and
  `DOCUMENT_PATCH_VERSION` (in `.service`). From `chemvas.features.session`:
  `RestorePlan` and `SESSION_SCHEMA_VERSION` (in `.logic`). From
  `chemvas.features.export`: `MM_PER_INCH` (in `.plan`).
  `HoverAction` is a near miss worth naming: it left
  `chemvas.features.hover`'s `__all__`, so `import *` no longer offers it, but
  it is defined in that package root and stays importable by name.
  `normalize_3d` and `SHA256_HEX_RE` are untouched: each has a reader, and each
  was put where it is on purpose. `VALID_ARROW_KINDS` moved the other way and
  is now public — see Added.
- **The `chemvas.ui.canvas_state_lookup` module.** Its two production callers
  were rewritten off it and the module was deleted. Both rewrites tightened
  what they accept: the document-metadata accessor used to build and attach a
  metadata state when the canvas had none and now reads the one the runtime
  state carries, and the scene-runtime snapshot lookup dropped its fallback to
  a public attribute of the same name along with its leading-underscore
  stripping. As with the other guards removed here, a correctly wired canvas
  sees no difference.
- **The unused context-bar segment button.** `segment_button` and the
  `CONTEXT_SEGMENT_STYLE` it painted with had no caller anywhere in the tree;
  no context bar ever drew one.

## [0.4.1] - 2026-08-20

### Fixed
- `chemvas compose-document` crashed with a Python traceback and exit status 1
  on a wrongly typed `bond_length_px` canvas setting — `null`, a list, an
  object, or an integer beyond float range. That one value feeds the
  electronic-mark distance arithmetic before the document rules examine it;
  every other settings key was already refused cleanly. The merged settings are
  now validated by those rules before any value is used, so `bond_length_px` is
  refused the same way, with a `chemvas: error:` message and exit status 2.

## [0.4.0] - 2026-08-17

### Added
- **Public headless document composer**: `chemvas compose-document` compiles a
  strict, bounded Composition v1 manifest into a canonical, reopenable Chemvas
  document and publishes it atomically without replacing an existing output.
- **Deterministic layout diagnostics**: `chemvas check-layout` reports bounded,
  read-only note overlap, note/shape-border collision, and sheet-clipping
  warnings with stable persisted item indices and source hashes.
- **Structured note styles and electronic annotations**: headless composition
  accepts sanitized structured text styles and authoritative formal-charge and
  radical annotations, deriving consistent linked visual marks before
  publication.

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
- Document validation now bounds the global `text_font_size` setting to the
  6–96 pt range that interactive editing has always enforced; the reader
  previously accepted any size of 6 pt or larger. No Chemvas-written document
  is affected, since no editing path could store a larger value. *(This entry
  was added after the 0.4.0 release to document a change that shipped in it.)*

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

[Unreleased]: https://github.com/dhsohn/Chemvas/compare/v0.12.0...HEAD
[0.12.0]: https://github.com/dhsohn/Chemvas/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/dhsohn/Chemvas/compare/v0.10.2...v0.11.0
[0.10.2]: https://github.com/dhsohn/Chemvas/compare/v0.10.1...v0.10.2
[0.10.1]: https://github.com/dhsohn/Chemvas/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/dhsohn/Chemvas/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/dhsohn/Chemvas/compare/v0.8.4...v0.9.0
[0.8.4]: https://github.com/dhsohn/Chemvas/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/dhsohn/Chemvas/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/dhsohn/Chemvas/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/dhsohn/Chemvas/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/dhsohn/Chemvas/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/dhsohn/Chemvas/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/dhsohn/Chemvas/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/dhsohn/Chemvas/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/dhsohn/Chemvas/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/dhsohn/Chemvas/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/dhsohn/Chemvas/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/dhsohn/Chemvas/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/dhsohn/Chemvas/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/dhsohn/Chemvas/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dhsohn/Chemvas/releases/tag/v0.1.0
