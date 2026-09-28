# Browser adapter

[한국어](WEB_ADAPTER.ko.md)

Chemvas is migrating its existing editor to a browser presentation adapter while
keeping the Qt application. The browser adapter is in development; full workflow
and visual parity remain the acceptance target.

## Run

```bash
python -m pip install -e .
chemvas --ui web
chemvas --ui qt
```

After `make check`, use `.venv/bin/chemvas` on macOS/Linux or
`.venv/Scripts/chemvas.exe` on Windows. Python 3.12+ is required.
`chemvas --ui web --no-browser` prints the local launch URL. Keep the terminal
open; Ctrl+C stops the server. The URL contains a session credential and stays
local. No frontend build, CDN or Node runtime is needed. The browser path imports
no Qt; the combined package still installs Qt for the desktop application.

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
- Benzene insertion executes `StructureBenzeneBuildService` and the same committer.
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
- SVG bond primitives come from `BondGeometryPlanService`,
  `BondLineGeometryService` and `BondRingDoubleGeometryService`, including the
  shared ring-edge selection policy. Live document ring order takes precedence
  over cached graph cycles in both adapters.
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
including custom sizes. Drawing starts/releases and atom input must be inside
the sheet. Leaving it cancels a bond drag, even if the pointer returns before
release. Hover edits on off-sheet structures report the native guidance;
Select movement/deletion and the eraser remain available to recover those objects.

Space selects the selection tool. Drag selected atoms/bonds to move them,
Shift-click to add or remove selections, and use Command/Ctrl+A to select the
whole structure. Delete removes the selection in one command. Escape returns to
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
completed disk save, so the dirty marker and close warning remain visible.
There is no autosave or recovery in the browser yet.

## Connections still in progress

Text and arrow editing, marquee selection, selection outlines and handles,
panels, SMILES, chemistry clipboard and publication export await their existing
workflow adapters. Their original toolbar/menu positions remain visible with
unconnected actions disabled. The browser has no separate simplified editors
or SVG export command for these actions.

Text, arrows, images, groups, extra annotation types and unsupported styles open
as incomplete read-only previews. Their original data remains in downloaded
copies; editing is rejected. Font rasterization, label hit shapes, bond junctions,
rich text, menus, file dialogs and clipboard behavior still require browser and
platform work. Qt remains the complete editor.

The server binds to loopback, verifies Host/Origin and the launch credential, and
serves an explicit asset allowlist. It stores up to 16 in-memory sessions, accepts
requests up to 2 MiB and documents up to 2,000 atoms/3,000 bonds, and uses the
existing 100-command history limit. These are per-request/session limits, not an
overall process memory cap. Refreshing or closing can discard unsaved work.

## Maintenance and verification

`bootstrap/web_adapter.py` owns HTTP/session and existing-service connections.
The browser modules contain transport, SVG materialization and DOM/event wiring.
Editing algorithms remain in their existing owners. A Qt-specific boundary may
accept a point factory or an unrecorded candidate caller; it must preserve the
native default behavior. Do not add a second edit engine, per-tool forwarding
files or copied rollback blocks. See [ADR 0029](adr/0029-browser-adapter.md).

`make check` covers Qt-free imports, actual HTTP requests, rejected retired actions,
failed-edit atomicity, Undo/Redo, document preservation and JavaScript checks.
Tests require Node.js 20+. Differential tests compare actual Qt and browser
bond creation, click direction, benzene attachment/fusion, deletion and bond
styles. They also compare ring line coordinates at two bond lengths with and
without ring records, and exercise web → Qt save → web edit/Undo → Qt reopening.
Real browser checks cover gestures and layout. These checks do not establish
complete UI, recovery or output parity; Qt retirement needs separate acceptance.
