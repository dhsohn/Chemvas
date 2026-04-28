# Architecture

## Responsibility Boundaries
- CanvasView (`app/ui/canvas_view.py`): input handling, tool dispatch, selection state, and coordinating model/render/history updates. It should not own low-level drawing primitives.
- MoleculeModel (`app/core/model.py`): pure atom/bond data and IDs. No Qt dependencies.
- RDKitAdapter (`app/core/rdkit_adapter.py`): optional chemistry backend for SMILES import, property calculation, 3D coordinate generation, alias expansion, and preview scene building. UI code should treat it as a best-effort service, not a required startup dependency.
- Renderer (`app/core/renderer.py`): style, pens/brushes, font settings.
- HistoryCommand (`app/core/history.py`): delta-based undo/redo with `SnapshotCommand` as a fallback.
- BondRenderer (`app/ui/bond_renderer.py`): bond QGraphicsItem creation/updates and geometry helpers, driven by CanvasView context.
- Graphics items (`app/ui/graphics_items.py`): non-selectable QGraphicsItem wrappers.

## Data/Render Flow
Tools -> CanvasView -> MoleculeModel mutation -> Renderer/BondRenderer -> QGraphicsScene updates -> HistoryCommand push.

3D flow: export command or preview refresh -> current molecule / active atom-bond selection -> MoleculeModel subgraph + atom mark annotations -> RDKitAdapter conversion graph build -> RDKit 3D embedding -> `.xyz` writer or preview scene.

## Snapshot Fallback
When an operation touches multiple entity types at once (ex: atom creation plus bond creation), CanvasView falls back to `SnapshotCommand` to keep undo/redo safe until a dedicated delta command exists.

## 3D Conversion Constraints
- Export scope is limited to chemical graph data. Arrows, TS brackets, free text, and other scene-only annotations must be ignored when building the export payload.
- RDKit stays optional. If it is unavailable, the export action should fail with a clear message rather than introducing a hard dependency into app startup.
- Canvas charge/radical marks should be normalized into per-atom annotations before conversion so formal charge and radical electrons survive into RDKit.
- Supported aliases (`Me`, `Et`, `OH`, `Ph`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `i-Pr`) should be expanded into explicit fragments at conversion time. Unsupported abbreviations must still fail loudly instead of guessing.
- Wedge/hash bonds should be translated into RDKit bond directions on single bonds only. Invalid stereo usage should fail with a precise message.
- `.xyz` is coordinate-only. Bond order and reaction semantics are not preserved in the output format and should not be treated as round-trippable state.
- The preview panel should reuse the same conversion path as `.xyz` export to avoid divergence between what the user sees and what gets exported.
- The right-side dock is a toggleable core workspace region for 3D preview. It stays on the same conversion path as `.xyz` export, but users can hide it when they do not need live 3D inspection.
- All workbook sheets are canvas sheets. Legacy `result_sheets` payloads may still exist in older files, but current UI ignores them on load.

## Planned Next Slices
- Extract preview rendering (bond/SMILES/template) into dedicated renderer modules.
- Batch scene updates around multi-item operations (selection, mass move, template insert).
