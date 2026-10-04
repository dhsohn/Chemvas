# ADR 0029: Browser presentation adapter over existing editing owners

- Status: Extended by [ADR 0032](0032-browser-clipboard-and-drafts.md)
- Date: 2026-09-28
- Extends: [ADR 0005](0005-responsibility-based-editor-boundaries.md)

## Problem

The browser must preserve Chemvas editing rules while the Qt application remains
available. Independent browser commands, label/movement policies, annotation
editors and a browser-drawn SVG download path would introduce a second set of
behaviors.
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
The Ring tool is the desktop's template session: it starts on benzene, the Ring
page chooses among `TEMPLATE_ENTRY_SPECS`, and a click runs the same request,
plan, `TemplateGeometryResolverService` (now given the browser's point type) and
`commit_template_ring` (now Qt-free, shared with the desktop commit). The hover
preview is a read-only `template_preview` query that runs the same plan and
resolver (benzene through the builder's placement plan) and returns the preview
geometry of `plan_template_preview_update`, drawn with the shared preview color
and opacity.
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
A move edit may carry the view scale. After the existing translation, the
browser offers the moved arrows' and lines' ends to the other arrows' and lines'
ends through `endpoint_connection` in line_geometry, the rule the desktop's
`connection_for` now calls on each selection-drag frame: the smallest shift that
puts a moved end on another end within `ENDPOINT_SNAP_SCREEN_PX` at that scale
moves the whole selection once more, in the same candidate and history command.
A move without a scale only translates. The desktop's on-drag connect mark is
not connected.
Arrow labels are edited through an `arrow_labels` edit and previewed through a
read-only `label_preview` query, using the shared label syntax and placement.
Arrow and Line drawing previews return the ends the endpoint funnel caught
(`points_on_endpoints`), which the browser draws as the desktop's snap rings at
their on-screen size.
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
its block and run model at once, in the markup `note_markup` returns for those
runs, so text typed meanwhile keeps its content and format. A reply is applied
only while the editor still holds the runs it was sent, and the server remains
the owner of that accepted rendering; before it arrives, the editor's transient
pixel and script sizes mirror `browser_font_pixels` and `qt_script_pixels`,
which a differential test compares. Selected notes change together in one
`note_format` edit that may not alter their text. The Color tool
recolors whole notes inside the same color edit as the rest of the selection:
like `apply_note_color`'s whole-document merge, every character run takes the
color and an empty paragraph's own character format keeps it, which restores
to the same Qt character formats. A caret without a selection follows Qt's
typing format: toggles and size steps accumulate on a format held only by the
open editor, starting from the character before the caret, or after it at the
start of a nonempty paragraph, and change neither the document nor history.
Text typed at that caret, including committed input-method text, takes that
format in the editor at once, and a new paragraph started there keeps it;
navigation keys, pointer presses and other caret moves drop it. Ending the edit
still sends the single `note_text` edit above. Undo (Ctrl+Z or Cmd+Z) and Redo
(Ctrl+Shift+Z, Cmd+Shift+Z or Ctrl+Y) inside the open editor, and the browser's
own `historyUndo` and `historyRedo` input, restore the editor's own steps,
because the browser's native history cannot follow the editor re-rendering
formatted runs; Ctrl+Alt (AltGr) combinations stay with the keyboard. Each
change is one step: contiguous typing, or contiguous deletion in one direction,
extends the step before it, while a new paragraph and a committed composition
are one step each, and caret formats, cancelled compositions and `note_markup`
replies record none. This grouping is the editor's own rule, not a measured
copy of Qt's, and steps are not limited in number. An input with no
`beforeinput` of its own after the last input, Undo, Redo or composition
records no step and clears Redo. The browser decides whether its context-menu
Undo and Redo are available from its own native history, which the editor does
not feed, so those items can be unavailable while the editor has steps; the
editor does not enable them. Pasted, dropped, deleted and replaced content,
such as a spelling correction, keeps the browser's own runs and drops the
pending format; the
desktop's plain-text paste with a pending format has not been compared. An
empty paragraph, or a position after a line break, with nothing pending uses
the document's default format rather than Qt's stored format. Input-method
composition, font rendering and caret placement at run boundaries still need
checks in real browsers and platforms. Lists and non-point font sizes are not
connected; notes with them keep the document read-only and display as plain
text.
There is no separate graph-patch editing endpoint, plain-note dialog, simplified
arrow editor or browser-drawn figure export. Every document bond style now goes
through `BondGeometryPlanService`, so no bond style keeps a document read-only.
The double-bond context menu is a read-only `bond_menu` query that takes the
native context target (the picked bond, else the nearest bond within the wider of
0.35 bond lengths and the structure pick radius) and lists
`DOUBLE_BOND_CONTEXT_STYLES` with `style_for_double_position`; choosing an entry
applies the resulting style at order 2, as the desktop menu does. A calculation
plan does not draw on the canvas, so it travels with edits; after each accepted
edit `calculation_plan_save_warning`, shared with the desktop snapshot, decides
whether the plan still matches the graph, and a stale plan is left out of that
version with the desktop's warning while history keeps the prior version.
Atom annotations that no mark implies stay as they are, as on the desktop,
which resynchronizes an atom's annotation only when its marks change.
Perspective views are editable: the drawing reads the stored depth points
through the desktop's 3D geometry ports, whose rules live in
`domain/document/perspective.py`, so ring double bonds project the same way.
The shared move controller carries a moved atom's point, a bond length change
rescales the points as the desktop does, and each accepted edit saves only the
points that still project onto a live atom. The Perspective Rotation tool is not
connected yet. Groups are editable: the adapter keeps the desktop's group state
with candidate record identities as scene record ids, so deletes and reordering
carry references the way the desktop snapshot does. Group rules live in
`features/groups`: Edit > Group and Ungroup (Ctrl+G, Ctrl+Shift+G) plan the
same merge, connection preflights refuse joining two groups' molecules with the
desktop's message, new bonds and label merges extend the owning group, and
Align and Distribute treat a group as one object. The drawing lists each
group's selection keys, and the browser completes a selection to whole groups
and toggles a group as one unit; the dashed group box uses the desktop's
padding, corner radius and dash pattern. Images are editable: select, move,
delete, rotate and flip (the pixels stay upright and the box moves as on the
desktop), Bring to Front and Send to Back over images and shapes together,
Align and Distribute, and grouping. Embedded image sources travel only when a
document is opened and in the `export` answer that Save downloads; every other
session response replaces `data_base64` with a SHA-256 `data_ref`, and the
browser fetches each source once from an authorized `/api/image` request as a
Blob URL. Open and session requests accept a document up to the desktop's
document budget, while the drawing without image sources stays within 2 MiB.
File > Export MOL is an `export_mol` session query under the same revision
check. Like the desktop's selected-only export, it takes the selected atoms,
bonds and ring-fill atoms, or else the owners of selected charges and
radicals, builds the shared `build_3d_conversion_payload`, and writes it
through `export_molfile_block`, the policy the desktop's `export_mol` now
calls: the V2000 writer, its hard limits, and the optional RDKit expansion of
abbreviations. The answer is Molfile text that the browser downloads; the
query changes no document, revision or history, and the browser drops a reply
for a document replaced or edited meanwhile.
File > Export Figure is an `export_figure` session query under the same
revision check, accepting only `format` `svg`. The browser sends `scope`
`sheet` and downloads the returned `svg` text as plain SVG named after the
document, a trailing `.chemvas` replaced by `.svg`. The desktop export paints a Qt scene, so the threaded server does not
call it in-process and still imports no Qt: `figure_svg` runs one short-lived
child of the same interpreter (`-I`, this checkout's `app` path) per request.
The child receives a JSON copy of the accepted document on stdin, creates its
QApplication, opens the document with `offscreen_canvas` and calls the existing
`export_figure(fmt="svg")` into a private `TemporaryDirectory` that
`figure_svg` creates per request and passes as a child argument, then returns
the text. `figure_svg` owns that folder: it removes it after the child exits,
whether the export succeeded, was refused or failed, and after a timeout once
`subprocess.run` has killed and waited for the child. The browser never
supplies a server path.
The native export is the only SVG writer and its file output is the test
oracle; there is no browser figure renderer and no SVG post-processing. Bounds:
120 seconds per export, the `MAX_OUTPUT_BYTES` limit of the command-line
renderer, and a fixed refusal when the child exits abnormally, as when Qt
cannot start. The desktop export's own `ValueError` messages pass through
unchanged. The query itself changes no document, revision or history. The
browser first commits an open note, which can record its own edit, and a note
that is not saved stops the export; it runs one export at a time and drops a
reply for a document replaced, renamed, edited, busy or loading meanwhile. A non-empty selection is
refused, and selection-only scope, PDF, PNG, TIFF, editable SVG and the export
dialog's options are not connected.
Atom input is a revision-bound session query, so no request sends the document
back. Insert Image sends the chosen file's bytes with the visible scene rect,
and the adapter applies the desktop's validation, budget and placement
(`inserted_image_box`); the new image is selected and Select becomes active.
Image Properties follows `IMAGE_PROPERTIES_SPEC`: the dialog sends only the
fields that changed, so accepting it unchanged is a no-op, and its aspect lock
follows the image's pixel ratio.

SMILES placement now connects the existing optional `RDKitAdapter`,
`plan_smiles_commit` and `apply_smiles_commit_plan`. The commit owner accepts a
point factory and an unrecorded private candidate, keeping its default Qt
transaction unchanged. Its label access imports the existing Qt-free shape
policy directly instead of importing the Qt renderer. There is no second
insertion algorithm and no required RDKit dependency. Input bounds and entry
labels are shared with the desktop. Each browser session retains one parsed model
keyed by normalized text and bond length; preparation never changes the committed
document. Charged and radical candidates request the existing bounded font
measurements before using the native label-aware mark offsets. Materializing
those marks preserves parsed annotations rather than applying a new charge edit.
The browser renders only additions from a disposable candidate at one group
opacity. Pointer requests coalesce, cancellation and session/revision changes
discard late replies, and a click completes preview measurements before the
single existing history edit. Missing RDKit and unsupported chemistry retain the
native failures. Undo/Redo and save/reopen keep the ordinary document path.

Open uploads a selected file; Save, Export MOL and Export Figure download.
There is no filesystem write API, client-chosen server path or persistent
document store. The server binds to loopback, verifies its own
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
Annotations, marquee selection, other object handles, recovery and the rest of
publication export remain migration work. Browser glyph sampling still differs slightly from Qt
font outlines; bond junctions and platform input also remain incomplete. Requests are limited
to 2 MiB and documents to 2,000 atoms/3,000 bonds, with at most 16 memory sessions
and the existing history limit. At that limit, sessions idle for 30 minutes are
closed so a crashed tab cannot hold a slot until the server restarts. These bounds do not cap total process memory.
The existing Qt document and scientific contracts remain in effect.

Selection picking is a revision-bound, read-only session action that returns a target without rendering the document or entering history. The browser supplies all direct graphics hits, including atoms underneath arrow ink; the adapter applies native role priority and the existing preferred structure picker. Shift selection and eraser retain raw graphics/near-bond semantics. Eraser picking stays inside its candidate edit. Pending pointer selection stores release coordinates and discards results after cancellation or a document revision change. No new HTTP route or separate selection history is introduced.
