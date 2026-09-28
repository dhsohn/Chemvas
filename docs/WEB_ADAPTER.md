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
  the existing palette, dimensions and ACS1996 rendering metrics.
- Bond creation executes `StructureBondBuildService` and `StructureBuildCommitter`.
  Atom picking, endpoint snapping, click direction and bond-style click policy
  use the same functions as Qt. Existing atoms and bonds are reused by the builder.
- Benzene insertion executes `StructureBenzeneBuildService` and the same committer.
  Attachment, fusion, atom merging, bond orders and ring records keep their existing
  owners. Single and multiple deletion use one request to the existing deletion planner.
- Bold polygons come from `BondGraphicsDrawService`, preserving bond order, ring
  orientation and adjacent bold-bond mitres. Only point/polygon construction changes.
- SVG bond primitives come from `BondGeometryPlanService`,
  `BondLineGeometryService` and `BondRingDoubleGeometryService`, including the
  existing ring-edge selection policy.
- `CanvasHistoryService` and `CanvasHistoryState` own Undo/Redo. The server builds
  a private candidate using the original operations, validates it, records one
  command, then publishes it. JavaScript mirrors accepted state.

Draw bonds with X, place or attach benzene with J, select with Space and delete
with Delete or the eraser. Click a bond to apply its selected style. A short bond
click uses the original default direction. B selects Bold while using the Bond tool. Undo/Redo treats each gesture as one
edit. Middle-button or Alt-drag pans; F5–F8 controls zoom.

Space selects the selection tool. Drag selected atoms/bonds to move them,
Shift-click to add or remove selections, and use Command/Ctrl+A to select the
whole structure. Delete removes the selection in one command. Escape, tool
changes and focus loss cancel the preview.

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
copies; editing is rejected. Font measurement, label clipping, bond junctions,
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
