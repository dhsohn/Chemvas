# Browser adapter

[한국어](WEB_ADAPTER.ko.md)

The browser presentation adapter is an experimental interface in active development,
intended for future Leaf integration rather than a standalone web release. It is
available only when running from a repository source checkout; installable wheel
and sdist packages exclude the web adapter modules and assets.

## Run (source checkout only)

```bash
python -m pip install -e .
chemvas --ui web
chemvas --ui qt
```

After `make check`, use `.venv/bin/chemvas` on macOS/Linux or
`.venv/Scripts/chemvas.exe` on Windows. Python 3.12+ is required.
Running `chemvas --ui web` from a packaged wheel or sdist installation exits with
an explanatory error directing you to a source checkout.
`chemvas --ui web --no-browser` prints the local launch URL. Keep the terminal
open; Ctrl+C stops the server. The URL contains a session credential and stays
local. No frontend build, CDN or Node runtime is needed. The browser server imports
no Qt; the environment still provides Qt for the desktop application.
File > Export Figure alone runs the desktop's Qt figure export, in a separate
short-lived process, so it needs that Qt installation.

## SMILES insertion

The SMILES field and Insert button use the desktop's optional RDKit backend.
Install the existing `rdkit` extra (`python -m pip install -e ".[rdkit]"`) only
if you need this feature. Without it, the field reports the same missing-backend
error as the desktop; drawing does not require RDKit.

Enter a SMILES string, choose Insert (or press Enter), then click on the sheet to
place the translucent structure once. The preview follows the pointer. Escape,
a tool change, focus loss, document replacement or another edit cancels it;
moving outside the sheet hides the ghost until re-entry. The existing insertion
planner and committer preserve atom labels, bond styles and electronic annotations.
A placement is one Undo/Redo command and saved copies use the existing document
format. Unsupported stereochemistry and isotope inputs keep the native errors.
The session keeps one parsed model for the current text and bond length. Preview
and font measurements never publish a document or add history, and late replies
cannot bring back a cancelled preview. Font-engine rendering differences remain.

## Connected implementations

- Toolbar order, names, tooltips, bond options and status hints come from the
  existing `main_window_config`. Both adapters use `shell.icon_design` artwork,
  the existing palette, dimensions and ACS1996 rendering metrics. Context options
  use the native white checked box, soft border and segmented-group spacing.
- Bond creation executes `StructureBondBuildService` and `StructureBuildCommitter`.
  Bond presses send raw scene coordinates and use the existing atom-first picking
  policy and shared radii. Releases onto bonds use the native nearest-endpoint
  snapping rule; angle steps come from `CanvasToolSettingsState`. Existing atoms
  and bonds are reused by the builder. Browser gestures commit on release; Qt
  restyles a pressed bond immediately.
- Benzene insertion executes `StructureBenzeneBuildService` and the same committer;
  the Ring page's other templates use the desktop's template planning,
  `TemplateGeometryResolverService` and `commit_template_ring`.
  Ring clicks use the native atom/bond distance preference and insertion gate;
  implicit atom hit circles use the native pick radius. Attachment, fusion, atom
  merging, bond orders and ring records keep their existing owners. Label click targets use the measured ink bounding rectangle, adding an offset
  anchor circle only for compact labels through the native predicate. Font sampling can
  still shift their edges slightly. Single and multiple deletion use one request
  to the existing deletion planner.
- Bold polygons come from `BondGraphicsDrawService`, preserving bond order, ring
  orientation and adjacent bold-bond mitres. Only point/polygon construction changes.
- Dotted bonds use `BondLineGeometryService.dotted_bond_dots` for their centers,
  radius and junction spacing; SVG only draws those circles. Double-bond overlays
  retain the native order and inner/outer policy.
- Atom input resolves the native hover target before nearby bond endpoints and
  fallback atoms. Direct label hits retain desktop item priority; SVG bond IDs
  no longer determine which atom is edited.
- Atom labels use the native label direction, alias anchor, subscript and stacked
  hydrogen layout. The browser measures font advances and line heights, sends
  them to the existing Python layout functions, and displays the positioned runs
  at the integer pixel sizes resolved by the desktop’s pinned 96-DPI font policy.
  Each session retains one bounded set of measured font metrics and glyph ink,
  outside document data and Undo/Redo. Native run placement and the original bond
  planner use that set directly when rendering edits, previews and history replay.
  Known glyphs need one response and one render; newly encountered glyphs request
  a measurement update bound to the returned revision, without sending the document
  back or replaying a committed edit. Previews send the session/revision and edit
  only. Invalid or stale measurements cannot change document/history or replace the
  accepted font data. Replacement discards the preceding measurement set.
  The planner shares the native convex-hull, clearance radius and contour-band
  intersection calculations;
  fixed-distance trimming and white label masking are removed. Browser ink is
  sampled at up to 8× resolution in a bounded raster. Half-covered pixels define
  the contour, constrained to the font engine's actual ink bounds so antialiasing
  does not add an outer pixel. Clearance uses a 64-sided round envelope.
  Font engines and sampling can produce small differences;
  this is not a claim of pixel-identical rendering on every platform.
- Imported charge and radical marks share native attachment coordinates, circle/dot
  dimensions and text-run placement, including custom colors and plain multiline
  text. SVG displays the resulting primitives; font-engine rounding differences
  remain possible. Marks are created, moved, reassigned and changed with the
  charge shortcuts through the same services as the desktop.
- Brackets and dagger symbols use the desktop's stroke commands and glyph
  layout. Their bounds follow the desktop's filled outline; dagger bounds come
  from the browser's measured glyph ink.
- SVG bond primitives come from `BondGeometryPlanService`,
  `BondLineGeometryService` and `BondRingDoubleGeometryService`, including the
  shared ring-edge selection policy. Live document ring order takes precedence
  over cached graph cycles in both adapters.
- Arrow and line paths share the existing native calculations in `line_geometry`.
  Qt consumes move/line/quadratic commands as `QPainterPath`; SVG consumes the same
  commands with native widths, dash spacing, caps and joins. All 19 kinds are
  covered, including mirrored/favored equilibrium and stored curve controls.
  A drawing is limited to 500,000 arrow path points.
  Arrows and lines support selection, dragging, mixed Select All, deletion and Undo/Redo through the native move controller and deletion planner. Arrow creation reuses the native endpoint snap funnel, default curve and Shift arc mirroring. The original arrow kinds/icons and More arrows grouping are available. The four Line kinds use the native endpoint/Shift rules and blank-click level length. Arrow presets and width/head sliders share native values and clamps.
  Clicking a selected arrow again toggles its endpoint handles; curved arrows also
  show the curve midpoint handle. Native endpoint minimum length, curve carry and
  midpoint limits run in the shared geometry owner. A snapped endpoint handle is
  filled and all handles keep their screen size. Previews retain the last valid
  endpoint, while release publishes one edit; Escape discards pending previews.
  Arrow labels share the original mini-syntax, HTML escaping, blank-label cleaning
  and placement calculation. Double-click in Select, Arrow or Line to edit Above
  and Below, with the original syntax hint, previews and 200-character counters.
  Untouched CRLF/CR text is preserved; OK records one edit and Cancel records none.
  Browser rich-text boxes join the bounded, revision-bound font measurement exchange,
  outside document history. Both adapters retain their font engines; small glyph
  width and baseline differences remain possible.
- Decorative shapes reuse native circle/ellipse/rectangle bounds, rounded-corner
  radii, click defaults, stroke widths and option definitions. Creation, previews,
  interior picking, movement, deletion and Undo/Redo are connected. Borderless
  previews use the native dashed grey guide; committed transparent interiors remain
  clickable. Shape movement shares the original record transform. Imported fills
  are retained. Eight resize handles share native positions, screen sizes and the
  original minimum-size clamp; a drag records one history command. As in Qt, a
  shape-only selection does not receive a rotation frame. Bring to Front and Send
  to Back share the
  native stable ordering and bounded depth bands. SVG depth order and foreground
  shape picking preserve those values, including imported custom depths.
- Color uses the native 16-swatch palette and original opaque pastel calculation
  for shape fills. Existing atom, bond, arrow and shape records receive colors;
  swatches apply to the current selection, and painting uses the native hit target
  before falling back to that selection. Preview/history and hidden-carbon guidance
  remain connected. Custom color picking uses the browser platform dialog; its
  appearance can differ from Qt. Notes, marks and ring-color expansion await their
  object adapters.
- `CanvasHistoryService` and `CanvasHistoryState` own Undo/Redo. The server builds
  a private candidate using the original operations, validates it, records one
  command, then publishes it. Commands retain documents only; Undo/Redo regenerates
  drawing primitives through the same renderer. Failed replay uses the existing
  history transaction owner to retain the document and stacks. JavaScript mirrors
  accepted state. A lost response triggers a read of the current session without
  repeating the edit. If that read also fails, the next action only reconnects and
  asks the user to check the refreshed drawing before editing again.

Draw bonds with X, place or attach benzene with J, select with Space and delete
with Delete or the eraser. Click a bond to apply its selected style. A short bond
click uses the original default direction. Hover a bond and press 1/2/3, b/w/h/d,
Shift+B/H/D or l/c/r to apply the native bond-style shortcut. These keys do not
change the active drawing style on empty space. Hover an atom to use the native
label letters and 0–9/z/v/u growth keys. A lowercase `a` attaches benzene to an
atom or fuses it to a bond; over a bond, 4–8 fuse regular rings and 9/0 fuse the
two chair orientations. Hover handling precedes tool selection, so A selects the
Atom tool only when no structure consumes it. X resets the Bond tool to Single
on empty space; over an atom, it applies the native X label. Charge marks (+/−)
report that they are not yet connected.
Undo/Redo treats each gesture as one edit. Plain wheel scrolls; Cmd+wheel on macOS
and Ctrl+wheel elsewhere zoom around the pointer. Browser Control/pinch zoom
remains available. Zoom limits (20–500%)
and button steps come from the desktop declarations. Browser pixel deltas map to
the native angle/pixel ratio; line/page deltas use the measured line height or
viewport extent. Physical wheel sensitivity can differ because browsers do not
expose Qt angle deltas. F5–F8 controls zoom.

The paper uses the native sheet dimensions and centered scene coordinates,
including custom sizes. File → Canvas Size connects the native paper list,
orientation, millimetre limits and dimension calculation. It preserves drawing
coordinates and records one undoable change; Custom disables orientation and
preset sizes display their dimensions without allowing edits. Drawing starts/releases and atom input must be inside
the sheet. Leaving it cancels a bond drag, even if the pointer returns before
release. Hover edits on off-sheet structures report the native guidance;
Select movement/deletion and the eraser remain available to recover those objects.

Pointer-selected toolbar buttons preserve focus, matching native NoFocus.
Keyboard-focused buttons and menu headings keep Enter/Space activation, even with the
pointer over the canvas. Space on the canvas selects the selection tool. Drag selected atoms/bonds to move them,
Shift-click to add or remove selections, and use Command/Ctrl+A to select the
whole structure. Drag empty canvas to select intersecting rendered shapes in either
direction. Command on macOS or Control elsewhere adds the area to the selection.
Escape, focus loss and tool/document changes cancel a pending area gesture;
late server picks cannot overwrite the selection. Area selection creates no
history command; subsequent movement or deletion uses the existing selection
workflow. SVG performs the item-shape intersection on the native geometry,
including transparent rings and shapes, rather than selecting bounding boxes.
The rubber band uses the browser's system Highlight color; platform styling can
differ from Qt's native rubber band. Delete removes the selection in one command. Escape returns to
Select and cancels the preview. Tool changes and focus loss cancel the preview.
With no selection, Delete/Backspace follows the native hover rule: first clear a
bonded atom’s visible label to implicit carbon; otherwise delete the hovered atom
or bond. A lone labelled atom is removed outright. Keyboard hover checks the
current SVG label hit shape before the native scene-distance fallback, so long
labels remain targets beyond their atom-center radius. Selection highlights do
not enlarge that hit shape. Enter over an atom opens the
native-label prompt, independent of the Atom tool’s current symbol; Enter over a
bond or empty space does nothing. Accepting an empty prompt resets implicit carbon,
while Cancel leaves the document and history unchanged.

A selects the Atom tool. Enter a symbol in the context bar and click to apply it;
an empty context field opens the existing-symbol prompt. Cancel leaves the document unchanged.

File → Open reads `.chemvas`; Save downloads a copy that Qt can open. Document
versions 7–9 retain their version and data. Download initiation cannot prove a
completed disk save, so the dirty marker and close warning remain visible, and
downloading Save never clears the dirty marker or removes a recovery draft.

Automatic recovery drafts protect unsaved work separately from desktop Qt
recovery. An OS process lock ensures only one running server owns a drafts
folder at a time; a second server started concurrently runs with recovery
disabled and notifies the user. Each unsaved document receives one stable random
draft identifier. After each accepted change, the server atomically writes the
complete drawing in a draft envelope storing the document name, save timestamp,
and `.chemvas` payload, without storing launch tokens, origins, or session
credentials. Files are stored unencrypted in local per-user application storage
(`~/Library/Application Support/Chemvas/browser-drafts` on macOS;
`%LOCALAPPDATA%/Chemvas/browser-drafts` or `~/AppData/Local/Chemvas/browser-drafts`
on Windows; `$XDG_DATA_HOME/Chemvas/browser-drafts` if `$XDG_DATA_HOME` is an
absolute path, otherwise `~/.local/share/Chemvas/browser-drafts` on Linux), or in a
custom folder specified at CLI launch via `--drafts-dir`. Drafts survive browser
reloads and server restarts, even when the server binds to a different loopback
port.

File > Recover Unsaved Work lists available drafts. Recovering replaces the
current drawing only after the existing unsaved-changes confirmation. The
recovered drawing adopts the existing draft identifier without multiplying
files; it is unsaved, and downloading Save downloads a copy while keeping the
drawing dirty and retaining the draft. Opening another document or replacing the
drawing after discard confirmation, or undoing to a known-clean baseline, removes
the draft. Closing a tab or stopping the server preserves drafts on disk.
Recovering a draft currently open in another window requires explicit
confirmation and ends that other window's session. Takeover is refused if the
holding window is busy beyond a bounded wait or its latest accepted changes
failed to reach the recovery draft; the other window stays open so you can
switch to it and save a copy or resolve draft-write failure. A crashed tab whose
server remains running can still be listed as open until you explicitly take
over its draft or restart the server. Up to 16 drafts (each up to
the 96 MiB document budget plus 64 KiB envelope) are retained without age-based
expiration. Draft write failures retain the last good copy on disk and show an
error notice, so the latest in-memory edits may not yet be recoverable. Damaged
or incompatible draft files are kept on disk for explicit discard. If a draft
folder cannot be read or written due to filesystem errors, the failure is
reported.

Chemistry Copy, Cut and Paste (Edit menu and ⌘/Ctrl+C, ⌘/Ctrl+X, ⌘/Ctrl+V) use
the canonical Chemvas v3 selection payload format without a parallel chemistry
schema. For supported selections, atoms, bonds, complete rings, attached and
selected marks, arrows, decorative shapes, orbitals, text notes, groups
(keeping remapped membership), embedded images (subject to image budgets),
and perspective 3D coordinates (where only perspective depth points reproject
through the target camera) are preserved; the existing validator may refuse
unsupported, corrupt, or oversized payloads atomically. Atom IDs are
remapped past existing IDs, and repeated pastes cascade with bond-length
offsets. Cut removes the selection only after a usable copy is created and the
source drawing is current. Each paste records as a single Undo/Redo edit.
Browser API capabilities vary; this adapter uses an asynchronous plain-text
clipboard transport (`text/plain`) where browser permissions and user gestures
allow; otherwise a validated copy is kept in the current window with an explicit
notice, disappearing on page reload. Native Qt custom MIME is
`application/x-chemvas-selection+json`, with no direct implemented
cross-adapter OS clipboard exchange. An open note editor retains native text
editing shortcuts; opening the Edit menu ends note editing and applies
clipboard actions to the canvas. Clipboard access and permission prompts vary
by browser.

Ring Fill reuses the native complete-cycle selection and opaque pastel blend.
Select a ring interior, all of its atoms, or all of its bonds, then choose a fill
swatch. Partial atom and bond selections are not combined to invent a cycle.
Ring Fill opens its palette while Select remains active. Transparent ring
interiors also support Shift selection, dragging, Color and erasing. Color paints
the ring's atoms and bonds; erasing a ring interior removes only its fill. Undo
restores the previous state. Equal-distance bond hits use the native grid order.

File > Export MOL downloads the selected structure as a `.mol` file named
after the document, matching the desktop menu. Use Select All to export all
chemistry. Attached marks supply charges and radicals. Empty or nonchemical
selections are refused, and the shared MOL writer reports unsupported
structures or V2000 limits. Optional RDKit expands abbreviation labels when
available. Export leaves the document and its history unchanged.

File > Export Figure downloads the whole sheet as a plain SVG file named after
the document, with a trailing `.chemvas` replaced by `.svg`. The browser does not draw this figure. For each export the server
starts a separate Python process that opens a private copy of the current
document in the desktop's offscreen canvas and runs the desktop's existing SVG
figure export; that process uses Qt, writes only inside a private temporary
folder the server creates for that export, and ends with the export. The server
removes that folder once the process has ended, including after a failed export
or a stopped one. The browser saves the result as an ordinary
download; the server has no option to write it anywhere else. An open note is
committed first, which can itself change the document and its history, and a
note that is not saved stops the export. One export runs at a time, and the
result for a document changed, renamed, replaced, busy or loading while the
export ran is dropped. The desktop export's own messages, such as
"There is nothing to export.", are shown unchanged. An export that runs longer
than 120 seconds is stopped, output over the size limit of the desktop's
command-line rendering is refused, and an export process that fails, including
one where Qt cannot start, reports that the figure could not be exported. In
each case nothing is downloaded. The export itself leaves the document, its
revision and its Undo/Redo history unchanged. Selection-only export, PDF, PNG, TIFF, editable
SVG and the options of the desktop's export dialog are not available in the
browser.

View > Valence Checking underlines atoms with more ordinary bonds than their
charge allows, using the desktop's rules: hydrogen, boron, carbon, nitrogen,
oxygen and fluorine in their common charge states, read from each atom's stored
charge and radical annotations, which mark edits keep in sync. Abbreviation
labels, radicals, dotted bonds and metal coordination are not assessed.
Underlines follow atoms you drag, and a
change's new warnings appear once it is accepted. It is on for each opened
drawing, is a view setting only and never blocks saving or exporting; the
underline is not part of the drawing or of any saved or exported file.
As on the desktop, only warnings on items in the visible area are drawn, each
along just the visible width. One view draws at most 50,000 zigzag points; the
warnings past that, in atom order, are left out until fewer are in view.

## Connections still in progress

Remaining object handles,
panels and the rest of publication export await their existing workflow
adapters. Their original toolbar/menu positions remain visible with
unconnected actions disabled. The browser has no separate simplified
editors or figure renderer for these actions.

Text notes and note boxes display and select, move, delete, rotate, flip and
align like the desktop. The Text tool (T) adds a note where you click or edits
the note you click, starting with all its text selected; Esc or clicking away
finishes, and an emptied note is removed. The Text page steps the font size and
toggles bold, italic, superscript, subscript and alignment for the selected text,
or for every selected note when none is open, and the Color tool recolors whole
notes. With only a caret, a button sets the format of the text you type next, as
on the desktop; moving the caret, pasting or deleting clears it, and a caret
format alone saves nothing. Pasted text keeps the browser's formatting, and an
empty line uses the document's default format. Input methods and caret placement
still need checks across browsers and platforms. Undo (Ctrl+Z or Cmd+Z) and Redo
(Ctrl+Shift+Z, Cmd+Shift+Z or Ctrl+Y) inside the open note step through its own
changes: a run of typing or deletion, a new paragraph, a formatting change or
committed input-method text is one step. The browser's context-menu Undo and Redo
may stay unavailable there, since the browser enables them from its own
history, and a spelling correction keeps the browser's formatting. Notes with
lists or non-point
font sizes open read-only as plain text.

Every bond style displays, including outward and either doubles. Right-clicking a
double bond offers the desktop's Inward, Centered and Outward positions.

Documents with a calculation plan stay editable. An edit that leaves the plan's
components behind drops it from that version with the desktop's save warning;
Undo brings it back.

Images, groups and perspective views are editable. Images can be selected,
moved, deleted, rotated and flipped (the pixels stay upright while their box
moves, as on the desktop), brought to front or sent to back together with
shapes, aligned, distributed and grouped; Insert Image and Image Properties use
the desktop's validation, budget, placement and fields. Embedded image sources
may take a document up to the 96 MiB full document budget, while the drawing
without them stays within 2 MiB. Groups keep the desktop's group state: Edit >
Group and Ungroup (Ctrl+G, Ctrl+Shift+G), selections that complete to whole
groups, the dashed group box, and the desktop's refusal to join two groups'
molecules. Perspective views read their stored depth points through the
desktop's rules, and each accepted edit keeps the points that still project onto
a live atom; the Perspective Rotation tool is not connected. Downloaded
copies keep all document data. Font rasterization, label hit shapes, bond junctions,
rich text, menus, file dialogs and clipboard behavior still require browser and
platform work. Qt remains the complete editor.

The server binds to loopback, verifies Host/Origin and the launch credential, and
serves an explicit asset allowlist. It stores up to 16 in-memory sessions (at that limit, windows
idle for 30 minutes are closed to make room), accepts
image-stripped drawings up to 2 MiB, full documents including embedded images
up to 96 MiB, and open/session HTTP requests up to 98 MiB. It accepts documents
up to 2,000 atoms/3,000 bonds and uses the existing 100-command history limit.
These are per-request/session limits, not an overall process memory cap. Recovery durability requires an accepted edit and a successful draft write; on a failed write, the previous good copy remains on disk and latest in-memory edits may not be recoverable. Uncommitted note text and edits not yet accepted at unload may be lost, and the browser's leave-page warning remains in place.

## Maintenance and verification

`bootstrap/web_adapter.py` owns HTTP/session and existing-service connections.
The browser modules contain transport, SVG materialization and DOM/event wiring.
Editing algorithms remain in their existing owners. A Qt-specific boundary may
accept a point factory or an unrecorded candidate caller; it must preserve the
native default behavior. Do not add a second edit engine, a second figure
renderer, per-tool forwarding files or copied rollback blocks. See
[ADR 0029](adr/0029-browser-adapter.md).

`make check` covers Qt-free imports, actual HTTP requests, rejected retired actions,
failed-edit atomicity, Undo/Redo, document preservation and JavaScript checks.
Tests require Node.js 20+. `tests/test_web_clipboard.py`, `tests/test_web_drafts.py`
and `tests/web_adapter.test.mjs` verify clipboard payload creation, paste planning,
draft locking, envelope persistence, takeover and session client recovery actions.
Differential tests compare actual Qt and browser bond creation, click direction,
benzene attachment/fusion, deletion and bond styles. They also compare ring line
coordinates at two bond lengths with and without ring records, and exercise web → Qt
save → web edit/Undo → Qt reopening. Real browser checks cover gestures and layout.
Clipboard behavior varies across browsers and platforms; these checks do not establish
complete UI, recovery or output parity, and Qt retirement needs separate acceptance.

Browser arrow gestures use a 10-screen-pixel Manhattan drag threshold. The browser cannot read the desktop system drag-distance preference; Qt continues to use that preference. Moving selected arrows or lines joins a moved end to another arrow's or line's end when it comes within 12 screen pixels at the current zoom, as the desktop's selection drag does: the whole selection shifts by that amount, and the move preview and the release use the same rule. The connect mark the desktop shows during that drag is not shown in the browser yet.

Select resolves graphics hits and scene coordinates through a revision-bound session pick, without changing or rendering the document. Ordinary selection uses the existing preferred structure policy; Shift selection and eraser use direct atom/bond hits and the native near-bond fallback. The fixed browser bond hit stroke is removed. A selection drag retains release coordinates while its pick is pending; cancellation and document changes discard late results. Eraser resolves and deletes in one candidate edit. Native arrow-near tolerance (six screen pixels beyond direct hits) and transparent ring-interior picking are connected.
Area selection currently requires the SVG intersection API. In browsers without
it, including Firefox, a drag is cancelled, the prior selection is restored and
an explicit notice is shown. Use Shift-click or Select All there, or select the
area in the Qt version.

Selected arrows and lines use the original path commands and native selection
width, with the same 1.5-screen-pixel outline above drawing content. Separate
head/stem subpaths retain their overlapping boundaries. SVG luminance masks
materialize the stroke boundary without Qt or a second arrow geometry algorithm.
SVG stroking/antialiasing can differ from Qt's path stroker, especially around
curves and joins; this is not pixel-identical rendering.

Molecular selection uses the native bond-band choice, atom-indicator rule and
connected-component calculation. A read-only, revision-bound query returns the
parts for the current selection. Move previews return those parts from the same
candidate document; selection changes discard older replies. Selected ring
interiors expand to their atoms for the outline, and unlabeled bonded carbons no
longer get separate filled circles. SVG morphology draws the boundary of each
component's combined alpha shape, without a second graph or bond algorithm.
Its raster kernel can differ from Qt's vector union at corners and small zoom
levels. Label selection now uses the native layout rectangle, document margin
and shared circular/padded bounds. Ink rectangles remain exclusively for glyph
picking. The original three-radius-width threshold decides whether a label keeps
a circle or receives an expanded box; measurement completion and previews carry
those bounds with their candidate. Font-engine metric differences remain.
Plain atom and arrow label line heights measure the browser's normal font line
at a 2048-pixel em, then rescale before the native document ceiling. This retains
the font's line gap without the half-pixel rounding of a small HTML span. Arial,
Times New Roman and Courier New at 8–64 pixels, regular/bold/italic, match the
native macOS document heights in 513 browser-measured comparisons. This does not
establish equivalence for every installed or fallback font. Wheel line deltas
continue to use their ordinary CSS line height.

Select's angle field and Rotate button connect the original numeric rotation
command. Edit → Rotate focuses that field. Its default is 15 degrees, range
-180 through 180, with one-degree step buttons; Enter applies the entered angle.
Selected bonds and ring fills expand to their atom IDs. The pivot uses atom
positions, arrow endpoint/control bounds and native shape bounds, without label
extents. Atom coordinates, annotation records and ring polygons use the original
transform and move services. Shapes remain upright while their centers orbit the
pivot, matching Qt. One application creates one Undo/Redo entry; an empty selection
or zero angle creates none. Preview and rejected edits leave the document intact.
Horizontal and vertical flip reuse the same whole-selection pivot and original
annotation transforms. The native Select icons, Edit menu actions and
Command/Control+Shift+H/V shortcuts are connected. Equilibrium mirroring and
above/below label exchange, arc handedness and shape bounds follow the original
transform. A zero-length equilibrium arrow rejects the whole edit before any
mutation. Repeated flips remove the native serializer’s omitted false mirror flag
while preserving record identity. Each flip has one Undo/Redo entry; empty and
unchanged selections create none.

Alignment and equal-gap distribution use the original native object grouping and
rectangle-delta calculations. Selecting any atom, bond or ring moves its complete
connected molecule without changing its internal geometry. Six alignment icons,
two distribution icons and their Edit submenus reuse the original definitions.
Outer objects stay fixed during distribution; fewer than two/three objects are
no-ops. Bounds include full atom-label layout and native path-item stroke bounds;
arrow labels do not enlarge their parent item’s alignment box, matching Qt.
Missing font measurements reject the edit. Candidate preview, publication and
Undo/Redo use the existing document/history path. A group aligns and
distributes as one object.

Diagonal round line caps now include Qt’s cubic control envelope in bounds,
correcting the small alignment offset from using a painted-circle box. Curved
arrow bounds retain the approximation described below, so their alignment can
inherit that documented coordinate error.

Selection frames and their rotation knobs reuse the native eligibility, padding,
corner radius, stem and handle sizes. Frames include full atom-label layout bounds
and arrow-label blocks. Like Qt, two selected atoms or a selected arrow/line get a
frame; shapes alone do not. Shape bounds are excluded from the visual frame even
when numeric rotation's pivot includes the selected shapes. The frame lives above
outlines and below object handles; its knob stays the same size on screen.

Dragging the knob sends pointer positions to the original rotation-angle function,
with the native 15-degree Shift step. Each preview transforms the committed press
state, rather than the preceding preview. Release applies one history command;
Escape/cancellation discards previews, and returning to the press position is an
exact no-op. A late preview cannot overwrite a finished or cancelled drag.

Qt's path-item bounds use stroked cubic control envelopes. The browser adapts
quadratic commands into offset control bounds with bounded subdivision; painted
arrow paths are unchanged. Cap/join envelopes and independent-side subdivision
are approximate: the 684-case native comparison has a maximum coordinate/size
error of 1.93 document units at a six-unit pen after the round-cap correction. Extreme-bend oversizing from the
initial unsplit control bounds (about 195 units) is corrected. This is not exact
Qt frame geometry for every curve or a claim of pixel parity.

Decorative shape selection uses the existing ellipse/rectangle paths and native
selection padding, including borderless and collapsed shapes. The same SVG
component-boundary renderer used for molecules draws each selected shape above
content and below resize handles; move/resize previews consume candidate geometry.
Qt shape selection now explicitly uses winding fill to avoid holes caused by
an inherited odd-even rule in borderless rectangles. Combining the two native
stroke widths in SVG differs slightly at flattened caps: native region sampling
matches outside a 0.25-document-unit boundary fringe, and SVG rasterization still
has the corner/antialiasing limitations above. This is not pixel parity.


The status-bar grid control cycles None → Hex → Square → None and exposes the
native 15%, 20% and 25% strengths. View → Snap to Grid toggles the current style.
Native background segments form bounded SVG tiles at the scene origin, spaced
by half the current bond length. Below six screen pixels the grid is hidden,
while snapping stays enabled. Arrow/Line drawing and endpoint handles use the
original endpoint → explicit angle → grid funnel; molecules, shapes and curve
midpoints retain their existing behavior. Grid choices are transient tool state,
not saved document settings or Undo entries. SVG and Qt antialiasing can differ.
