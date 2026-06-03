# Architecture

## Responsibility Boundaries
- CanvasView (`app/ui/canvas_view.py`): input handling, tool dispatch, selection state, and coordinating model/render/history updates. It should not own low-level drawing primitives.
- MoleculeModel (`app/core/model.py`): pure atom/bond data and IDs. No Qt dependencies.
- RDKitAdapter (`app/core/rdkit_adapter.py`): optional chemistry backend for SMILES import, property calculation, 3D coordinate generation, alias expansion, and preview scene building. UI code should treat it as a best-effort service, not a required startup dependency.
- Renderer (`app/core/renderer.py`): style, pens/brushes, font settings.
- HistoryCommand (`app/core/history.py`): delta-based undo/redo with `SnapshotCommand` as a fallback.
- BondRenderer (`app/ui/bond_renderer.py`): bond QGraphicsItem creation/updates and geometry helpers, driven by CanvasView context.
- Graphics items (`app/ui/graphics_items.py`): non-selectable QGraphicsItem wrappers.
- Label layout (`app/ui/label_layout_logic.py`): pure, Qt-free parsing of a raw atom-label string into typographic runs (subscripts) plus their placement. It is the single source of truth for label typography: `AtomLabelItem` consumes it for on-screen painting, and vector export consumes the same placement when outlining glyphs, so screen and export never diverge. It operates on display text only and never mutates the stored `element` string.
- Figure export (`app/ui/export_plan_logic.py` + `app/ui/export_dialog_logic.py` + `app/ui/export_render_service.py`): the two pure modules compute the padded source rect / physical output size (in points) and own the dialog's format/size/path rules; the Qt service (`export_scene`) collects visible content items (transient overlays excluded the same way as clipboard copy), hides everything else, switches atom labels into outline mode, and renders the scene region into one of four sinks — `QSvgGenerator` (SVG at 72 dpi so 1 unit = 1 pt), `QPdfWriter` (PDF, page sized to content in points), or a `QImage` (PNG/TIFF with DPI metadata). `unit_scale` (points per scene unit) or `target_width_pt` give a deterministic physical size independent of zoom: bond-length mode uses the style's `bond_length_pt`, column modes fit 84/174 mm. `scope` picks whole-sheet vs selection; `background` picks transparent vs white. Outlined labels mean no format carries font-dependent `<text>`, so screen/SVG/PDF/raster all show identical glyphs.
- Style presets (`app/core/style_presets.py`): named `ACS1996Style` variants (ACS 1996 / Nature·RSC / Presentation). `CanvasView.apply_style_preset` sets `_style_preset` and round-trips the whole document (`snapshot_state` → `apply_state`), so every item — bonds, atom labels, marks, TS brackets, orbitals, arrows — is rebuilt with the new metrics in one pass (history is preserved; selection is cleared). `apply_document_settings` is the single place that maps a preset name to `renderer.style` (keeping the on-screen `bond_length_px`), so apply, save and load all share it. The active preset persists in document settings as the optional `style_preset` key; files written before it load as `ACS 1996`.

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
- All workbook sheets are canvas sheets. Non-canvas workbook payloads are rejected during document validation.

## Planned Next Slices
- Extract preview rendering (bond/SMILES/template) into dedicated renderer modules.
- Batch scene updates around multi-item operations (selection, mass move, template insert).
- Publication export has landed (`export_scene`): SVG/PDF/PNG/TIFF, outlined labels, format/scope/DPI/background dialog, physical-unit sizing (bond-length + 84/174 mm column fit), journal style presets, and preset persistence (the `style_preset` settings key, backward-compatible). Next on this path:
- Clipboard vector: also place PDF/SVG flavors on the clipboard (today only a PNG is copied) so paste into Illustrator / macOS Office stays vector.
- Fold formal charge into label superscripts (`place_runs` already supports the `super` role); resolve the inline charge-vs-subscript ambiguity using the existing charge mark/property rather than parsing inline text.
