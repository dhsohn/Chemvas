# Architecture

## Responsibility Boundaries
- CanvasView (`app/ui/canvas_view.py`): input handling, tool dispatch, selection state, and coordinating model/render/history updates. It should not own low-level drawing primitives.
- MoleculeModel (`app/core/model.py`): pure atom/bond data and IDs. No Qt dependencies.
- Renderer (`app/core/renderer.py`): style, pens/brushes, font settings.
- HistoryCommand (`app/core/history.py`): delta-based undo/redo with `SnapshotCommand` as a fallback.
- BondRenderer (`app/ui/bond_renderer.py`): bond QGraphicsItem creation/updates and geometry helpers, driven by CanvasView context.
- Graphics items (`app/ui/graphics_items.py`): non-selectable QGraphicsItem wrappers.

## Data/Render Flow
Tools -> CanvasView -> MoleculeModel mutation -> Renderer/BondRenderer -> QGraphicsScene updates -> HistoryCommand push.

## Snapshot Fallback
When an operation touches multiple entity types at once (ex: atom creation plus bond creation), CanvasView falls back to `SnapshotCommand` to keep undo/redo safe until a dedicated delta command exists.

## Planned Next Slices
- Extract preview rendering (bond/SMILES/template) into dedicated renderer modules.
- Batch scene updates around multi-item operations (selection, mass move, template insert).
