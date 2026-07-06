# Architecture

## Responsibility Boundaries
- CanvasView (`app/ui/canvas_view.py`): input handling, tool dispatch, selection state, and coordinating model/render/history updates. It should not own low-level drawing primitives.
- MoleculeModel (`app/core/model.py`): pure atom/bond data and IDs. No Qt dependencies.
- RDKitAdapter (`app/core/rdkit_adapter.py`): optional chemistry backend for SMILES import, property calculation, 3D coordinate generation, alias expansion, and preview scene building. UI code should treat it as a best-effort service, not a required startup dependency.
- Renderer (`app/core/renderer.py`): style, pens/brushes, font settings.
- HistoryCommand (`app/core/history.py`): delta-based undo/redo. Multi-entity operations are grouped with `CompositeCommand`, which applies its child delta commands in order on redo and in reverse on undo.
- BondRenderer (`app/ui/bond_renderer.py`): bond QGraphicsItem creation/updates and geometry helpers, driven by CanvasView context.
- Graphics items (`app/ui/graphics_items.py`): non-selectable QGraphicsItem wrappers.
- Label layout (`app/ui/label_layout_logic.py`): pure, Qt-free parsing of a raw atom-label string into typographic runs (subscripts) plus their placement. It is the single source of truth for label typography: `AtomLabelItem` consumes it for on-screen painting, and vector export consumes the same placement when outlining glyphs, so screen and export never diverge. It operates on display text only and never mutates the stored `element` string.
- Figure export (`app/ui/export_plan_logic.py` + `app/ui/export_dialog_logic.py` + `app/ui/export_render_service.py`): the two pure modules compute the padded source rect / physical output size (in points) and own the dialog's format/size/path rules; the Qt service (`export_scene`) collects visible content items (transient overlays excluded the same way as clipboard copy), computes bounds from item-specific export ink/content rects when available (so label hit targets and transparent implicit-carbon dots do not affect physical sizing), hides everything else, switches atom labels into outline mode, and renders the scene region into one of four sinks — `QSvgGenerator` (SVG at 72 dpi so 1 unit = 1 pt), `QPdfWriter` (PDF, page sized to content in points), or a `QImage` (PNG/TIFF with DPI metadata). `unit_scale` (points per scene unit) or `target_width_pt` give a deterministic physical size independent of zoom: bond-length mode uses the style's `bond_length_pt`, column modes fit 84/174 mm. `scope` picks whole-canvas vs selection; `background` picks transparent vs white. Outlined labels mean no format carries font-dependent `<text>`, so screen/SVG/PDF/raster all show identical glyphs.

## UI Layer Discipline (ports / access / state / services)
The `app/ui` package is deliberately split into many small modules with fixed roles. The goal is that `CanvasView` and `MainWindow` stay thin Qt shells (no god object), every service is constructible headlessly (the full test suite runs in ~20s against `SimpleNamespace` canvases), and all dependencies are explicit.

- **State modules** (`*_state.py`): one dataclass per concern plus a `<name>_state_for(canvas)` accessor. All state accessors go through `ensure_canvas_state(canvas, name, factory)` (`ui/canvas_state_lookup.py`), which uses a single name for lookup and attach. On real canvases every state lives as a field of the eagerly-built `CanvasRuntimeState` container (`ui/canvas_runtime_state.py`); the container is strict — an accessor asking for a field the container does not have fails loudly instead of silently attaching a shadow copy. A handful of states (`model`, `renderer`, `bond_renderer`, `rdkit`) are deliberately stored as direct canvas attributes and use `runtime_field=False`. Adding a new state means: dataclass + accessor + a `CanvasRuntimeState` field; `test_state_accessor_names_match_runtime_state_container` enforces the sync.
- **Access modules** (`*_access.py`): free functions (`foo_for(canvas)`) wrapping one operation. They must not reach into `canvas.services` directly; service lookup is delegated to the matching ports module.
- **Ports modules** (`*_ports.py`): the only modules that resolve the service container (`canvas_services_for` / `window` private storage). Everything else receives collaborators via injection or calls a port.
- **Services and controllers**: constructed once per canvas in `ui/canvas_service_composer.py` with explicit keyword injection — no service locator inside services, no `=None` collaborator defaults that hide a missing wire.
- **core is Qt-free and ui-free**: `app/core` must not import `ui` at module level (a lazily resolved protocol implementation is the one sanctioned exception, see `core/history.py`).

These rules are enforced by `tests/test_architecture_boundaries.py`. That file contains *rules* (forbidden access patterns, removed surfaces that must stay removed, dependency contracts) — not assertions that a specific implementation phrasing exists. When adding a rule, express it as a pattern ban or a dependency contract that new code automatically falls under.

Known trade-offs of this discipline (accepted deliberately): a real indirection tax (~20% of ui LOC is wiring) and weak static typing at the canvas seam (`canvas: Any`). When an invariant spans several of these small modules (e.g. the derived graph index), the consistency contract must be written down in one owner module — see `ui/graph_index_operations.py` and `CanvasGraphService.bond_id_between_with_repair` for the pattern.

## Data/Render Flow
Tools -> CanvasView -> MoleculeModel mutation -> Renderer/BondRenderer -> QGraphicsScene updates -> HistoryCommand push.

3D flow: export command or preview refresh -> current molecule / active atom-bond selection -> MoleculeModel subgraph + atom mark annotations -> RDKitAdapter conversion graph build -> RDKit 3D embedding -> `.xyz` writer or preview scene.

## Composite Grouping
When an operation touches multiple entity types at once (ex: atom creation plus bond creation), CanvasView groups the individual delta commands into a single `CompositeCommand` so the whole operation undoes/redoes atomically.

## 3D Conversion Constraints
- Export scope is limited to chemical graph data. Arrows, bracket annotations, free text, and other scene-only annotations must be ignored when building the export payload.
- RDKit stays optional. If it is unavailable, the export action should fail with a clear message rather than introducing a hard dependency into app startup.
- Canvas charge/radical marks should be normalized into per-atom annotations before conversion so formal charge and radical electrons survive into RDKit.
- Supported aliases (`Me`, `Et`, `OH`, `Ph`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `i-Pr`) should be expanded into explicit fragments at conversion time. Unsupported abbreviations must still fail loudly instead of guessing.
- Wedge/hash bonds should be translated into RDKit bond directions on single bonds only. Invalid stereo usage should fail with a precise message.
- `.xyz` is coordinate-only. Bond order and reaction semantics are not preserved in the output format and should not be treated as round-trippable state.
- The preview window should reuse the same conversion path as `.xyz` export to avoid divergence between what the user sees and what gets exported.
- The 3D preview opens as a separate modeless window from the toolbar. It uses the selected-structure conversion path, owns the `Export 3D XYZ` action for the selected molecule, and shows an empty preview when no chemical structure is selected.
- Each open canvas tab is an independent document with its own file path and clean/dirty digest. `.chemvas` loading accepts only the canonical single-canvas payload.

## Planned Next Slices
- Extract preview rendering (bond/SMILES/template) into dedicated renderer modules.
- Batch scene updates around multi-item operations (selection, mass move, template insert).
- Publication export has landed (`export_scene`): SVG/PDF/PNG/TIFF, outlined labels, format/scope/DPI/background dialog, and physical-unit sizing (bond-length + 84/174 mm column fit). Next on this path:
- Clipboard vector: also place PDF/SVG flavors on the clipboard (today only a PNG is copied) so paste into Illustrator / macOS Office stays vector.
- Fold formal charge into label superscripts (`place_runs` already supports the `super` role); resolve the inline charge-vs-subscript ambiguity using the existing charge mark/property rather than parsing inline text.
