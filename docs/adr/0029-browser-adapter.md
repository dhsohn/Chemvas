# ADR 0029: Browser presentation adapter over existing editing owners

- Status: Accepted
- Date: 2026-09-28
- Extends: [ADR 0005](0005-responsibility-based-editor-boundaries.md)

## Problem

The browser must preserve Chemvas editing rules while the Qt application remains
available. Independent browser commands, label/movement policies, annotation
editors and an SVG download path would introduce a second set of behaviors.
ADR 0005 requires one owner for each mutation rule and rejects obligatory
access/port/service layers.

## Decision

Select presentation through `chemvas --ui qt` or `chemvas --ui web`; Qt is the
default. Use browser-native modules and SVG without a frontend build framework.
Reuse the existing toolbar declarations, artwork, palette and dimensions.
Keep HTTP/session, DOM wiring and SVG materialization cohesive; do not split
by tool or impose file-length targets.

`BrowserStructureAdapter` connects the existing `StructureBondBuildService`,
`StructureBenzeneBuildService` and `StructureBuildCommitter` to document records.
Atom picking, endpoint geometry, bond-click policy and deletion planning use
shared existing owners. Existing model serialization preserves document data.
Rendering services supply SVG bond primitives, including ring topology order.
Qt imports stay at native materialization or transaction boundaries. Injected
point factories and unrecorded build calls preserve native defaults.

The Python session owns a committed document. An edit runs against a private
candidate, validates the whole result, records it through the existing
`CanvasHistoryService`, then publishes it. JavaScript has no history stack.
Gesture previews are disposable candidates using the same edit path. Revision
checks reject stale writes; reads can recover the current revision without
replaying an uncertain edit. If recovery fails, the next action only reconnects.
Document names travel with the authoritative session so replacement-response loss
cannot retain the previous file name. Each existing session serializes its own
requests; registration uses the server inventory lock. History commands retain
only documents and regenerate drawing on replay, using the existing history
transaction port to preserve state if rendering fails. The adapter adds no copied
try/restore sequence.

Atom-label direction and anchor decisions live with the existing pure label
layout functions. The browser measures font advances, ascent, descent, line height
and glyph ink at the desktop's integer pixel sizes under pinned 96 DPI. Each
session owns one replaceable `BrowserFontMeasurements` value, separate from the
committed document and history. The font family is fixed by the native style;
metric/ink key counts, glyph point counts and HTTP body size are bounded.
The browser also retains only its most recently requested measurement set.

Edits, previews and history replay use the registered measurements to call
`place_runs` / `place_hydride_stack` and the original bond planner in one pass.
Missing glyphs return a measurement request instead of rendering a discarded,
unclipped scene. A revision-bound measurement action completes the accepted
snapshot, or reconstructs a disposable preview from its edit. It carries no
document and never repeats a committed mutation. Validation and rendering must
succeed before the new font value replaces the old one. Measurement updates and
previews do not advance revisions, mark documents dirty or create history entries.
A failed presentation triggers read-only resynchronization using the accepted
session identity, including on first load. Stale measurement/preview requests are
rejected before any font change. The old stateless label, drawing and preview HTTP
routes are removed; pure label placement remains the shared rendering boundary.
The Qt renderer consumes the same direction, placement and clipping owners.

Arrow path calculation moves from `ArrowRenderer` into the existing Qt-free
`line_geometry` module. Its move/line/quadratic commands feed both QPainterPath
and SVG, including native equilibrium shortening, arc tangents and default curve
controls. The native renderer retains records, pens, item lifetime and label
children. Internal per-kind construction methods collapse into one path adapter;
the curved-handle entry point remains. The provisional browser single-head path
is removed. Browser arrow items expose canonical records to the existing
CanvasMoveController; selection buckets feed the existing deletion planner.
Mixed graph/arrow changes remain one private candidate and one history command.
Arrow creation adapts pointer coordinates and modifiers into the native endpoint
snap funnel in line_geometry, then constructs the existing Arrow record.
Native LineTool also consumes this funnel for endpoint/Shift/grid priority.
The desktop retains its system drag-distance setting; the browser uses 10 CSS
pixels because the setting is unavailable there. Arrow kinds, More arrows
grouping and icons reuse desktop declarations. Line creation and arrow style controls reuse native rules, presets and slider
ranges. Arrow endpoint mutation and curve midpoint/carry calculations move to
this same geometry owner; the Qt services retain point conversion and scene updates.
SVG displays server-supplied handle positions with native screen size and snapped
fill. A handle request carries the current pointer and the last accepted preview
position, so a rejected short endpoint frame retains its preceding valid position.
Each preview is disposable; release waits for an in-flight preview and publishes
one existing history command. Cancellation or revision changes discard the gesture.
Arrow labels and drawing snap markers remain separate connection work.
The browser limits a drawing to 500,000 arrow path points before publishing a
candidate, including read-only loads.

Unconnected tools stay at their original UI positions and remain disabled.
Mark graphics adapt document records to the existing move controller, deletion
planner and independent-selection policy. Native placement, mark/atom priority,
transform offsets and bond-length offset scaling are shared calculations. Selection
uses the native hit shapes and circular indicator; alignment receives measured
native item bounds. These editing ports are compared against actual Qt commands,
and consistent marked documents can now be edited. The original Mark options
connect creation; the context menu connects explicit owner reassignment using the
same annotation validation and before/after plan as Qt. Candidate highlighting and
cancellation do not change the document. Inconsistent mark/annotation records and
isotopes remain read-only. Charge shortcuts use the existing shortcut service with
native opposite-mark cancellation and compass/overflow placement shared by both
adapters. Font measurements carry advance width, rendered bounding width and
glyph ink separately: mark clearance consumes bounding width, while collision
checks consume ink. Neither substitutes for the other. The session retains native per-atom mark binding order through edits,
measurement completion and the existing history commands. This transient order is
not written to `.chemvas` files; opening a file initializes it from document order,
as Qt does. Native deletion undo also restores the previous binding indices, so
undoing a deletion cannot change the next opposite-charge cancellation. Selected
marks use native owner text and distance checks for the owner guide and amber
warning. Mark hover calls the same placement calculation as insertion and renders
a transient free glyph without updating the live document or electronic annotations.
Its color, opacity, stacking and atom indicator reuse native style values. Pointer
requests coalesce while a response is pending; leaving the canvas or changing the
revision cannot publish an obsolete preview. Mark measurement requests reject
concurrent direct edits. Charge keypresses retain their pointer target and session
and await the preceding charge edit before invoking that same measurement/edit
path. A rejected edit stops its pending chain; a replaced session cannot receive
keypresses from the previous document. These
limits and platform font geometry differences still prevent mark-editing parity. Bond-length changes use the existing model scaling operation and preserve
free annotation positions.
Scrollable bounds combine the sheet and persistent drawing with the native sheet
margin through the shared `sheet_scene_bounds` calculation. Accepted snapshots
supply these bounds; previews do not replace them. The browser clamps navigation
and candidate highlighting to that range and centers axes smaller than the
viewport. Candidate scrolling uses the native margin and integer conversion.
Qt scrollbar quantization can differ from the continuous SVG boundary by one
screen pixel. Arrow bounds retain the existing half-pen approximation of Qt's
stroke controls; rich arrow labels currently use their measured layout box
rather than Qt's exported glyph outline. These remain geometry differences.
Brackets use the shared stroke commands and dagger layout that the desktop fills.
Insertion, drag preview, selection, movement, deletion, rotation, flipping,
alignment and scroll range use the bounds of Qt's flat-cap, miter-join outline;
the browser samples curves along exact normals, which agrees with Qt within
0.001 scene units, including flat brackets whose zero-length sides Qt drops and
whose reversing joins it clips at the miter limit. Dagger bounds come from the
browser's measured glyph ink. A dagger's hit target is that ink box and its
six-pixel near search measures to the ink's convex hull, which can catch a point
beside a crossbar slightly earlier than Qt's glyph outline. Near picking of
bracket strokes measures to the same outline ring. The Color tool keeps the desktop notice and does not recolor
brackets.
Text notes render the saved note HTML that `sanitize_note_html` accepts. The
server rewrites it into a closed browser subset (paragraphs, breaks and inline
runs), resolves point sizes to Qt's integer pixels and scales script runs from
the integer point size, as QTextEngine does. Because the page's CSP ignores style
attributes, the browser applies those validated declarations through CSSOM. It
then gives every line a zero-width strut: Qt sizes a line from its own runs'
ascent, descent and leading, ceils it, and places proportional spacing below the
text, where CSS would split it around the text. Measured note boxes join the
existing rich-text box measurements; heights and baselines agree with Qt, widths
within the browser's glyph advance rounding. Notes rotate about their position
and flip by mirroring their scene box's centre; both rules now live in
`rotate_annotation` and `mirrored_box_position`, which the desktop scene code
also calls. Picking follows the native foreground-note rule, and the selection
box is the padded layout rectangle with the native screen-width stroke. Scroll
bounds use the layout rectangle rather than Qt's glyph outline. Every selected
note shows that box, including marquee selections, where Qt paints its own
dashed frame instead. The Text tool follows `NoteTool`: a click on a note edits
it with its text selected (Ctrl toggles and Shift extends the selection
instead), and a click elsewhere on the sheet starts a new note there. The
editor is a contenteditable overlay transformed with the note, carrying the
note's validated rich text; while it is open it uses the document line pitch
rather than the per-line struts. Ending the edit serializes the blocks and
runs into the saved subset (Qt point sizes from `data-pt`, weight, slant,
decoration, color and script alignment) and sends one `note_text` edit, like
NoteItem's focus out: unchanged text records nothing, a new empty note is
dropped and an emptied note is deleted. The server sanitizes the HTML, derives
the plain text as `toPlainText` does and rejects formatting it could not render
back. The browser context bar uses the desktop's tool-to-page map, so the note
tool shows the desktop Text page, built from the same size and format
declarations. Formatting follows `CanvasNoteController`: the target is the open
editor's selection, else each selected note whole; bold, italic and script
toggles follow the format before the cursor end, sizes step each run by one
point within 6-96, alignment applies to touched blocks, and a button is checked
only when the whole target shares its format. The editor applies the change to
its block and run model and asks the server for the markup (`note_markup`), so
point-to-pixel and script sizes stay in one converter; selected notes change
together in one `note_format` edit that may not alter their text. Formatting a
caret without a selection (Qt's typing format), the Color tool on notes, lists
and non-point font sizes are not connected; notes with the last two keep the
document read-only and display as plain text.
There is no separate graph-patch editing endpoint, plain-note dialog, simplified
arrow editor or browser SVG export workflow. Every document bond style now goes
through `BondGeometryPlanService`, so no bond style keeps a document read-only.
The double-bond context menu is a read-only `bond_menu` query that takes the
native context target (the picked bond, else the nearest bond within the wider of
0.35 bond lengths and the structure pick radius) and lists
`DOUBLE_BOND_CONTEXT_STYLES` with `style_for_double_position`; choosing an entry
applies the resulting style at order 2, as the desktop menu does. Images, groups,
perspective views, calculation plans, isotopes and inconsistent mark records
remain in read-only documents, including saved copies, until their existing
workflows are connected.

Open uploads a selected file; Save downloads a copy. There is no filesystem write
API or persistent document store. The server binds to loopback, verifies its own
Host/Origin and fresh launch credential, and serves a fixed asset allowlist.
Qt remains supported until full workflow, recovery, document and output parity
is demonstrated and a separate retirement decision is made.

## Verification and limits

`tests/test_web_adapter.py` checks Qt-free imports, actual HTTP authorization,
malformed input, document versions 7–9, failed candidate publication, history and
rejection of retired demo actions. It invokes `tests/web_adapter.test.mjs` for
transport failure, concurrency, text escaping and non-mutating gesture display.

Differential tests compare actual Qt and browser bonds, benzene attachment/fusion,
deletion, styles and line coordinates, plus document reopening across adapters.
Native tests retain recorded-build rollback and ring-cache behavior. Real browser
checks cover gestures and layout; these are not complete visual-parity evidence.

Atom labels and merging reuse `AtomLabelService` and `AtomLabelMergeService`;
selected-atom/bond dragging uses `CanvasMoveController`. Shift-click and Select All
provide multiple selection. Bold polygons reuse `BondGraphicsDrawService`.
Annotations, marquee selection, other object handles, recovery and publication export
remain migration work. Browser glyph sampling still differs slightly from Qt
font outlines; bond junctions and platform input also remain incomplete. Requests are limited
to 2 MiB and documents to 2,000 atoms/3,000 bonds, with at most 16 memory sessions
and the existing history limit. At that limit, sessions idle for 30 minutes are
closed so a crashed tab cannot hold a slot until the server restarts. These bounds do not cap total process memory.
The existing Qt document and scientific contracts remain in effect.

Selection picking is a revision-bound, read-only session action that returns a target without rendering the document or entering history. The browser supplies all direct graphics hits, including atoms underneath arrow ink; the adapter applies native role priority and the existing preferred structure picker. Shift selection and eraser retain raw graphics/near-bond semantics. Eraser picking stays inside its candidate edit. Pending pointer selection stores release coordinates and discards results after cancellation or a document revision change. No new HTTP route or separate selection history is introduced.
