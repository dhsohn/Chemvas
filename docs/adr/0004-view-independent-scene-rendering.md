# ADR 0004: View-independent document scene rendering

- Status: Accepted
- Date: 2026-09-20

## Context

Drawing a document previously required a `CanvasView` and its editor service
graph. The command-line renderer therefore built selection, input, history,
and editing collaborators even though it needed only a scene. Splitting files
without changing those dependencies would leave the same coupling in place.

## Decision

`SceneRenderContext` explicitly supplies current scene and model providers,
style renderer, and drawing state. `SceneRenderState` owns the shared drawing
fields; `CanvasRuntimeState` extends it with editor state. The GUI passes its
actual runtime state, not a mirrored copy. Its model provider follows document
replacement and rollback without retaining an obsolete model.
The scene provider likewise follows the view's public `setScene` operation.

`SceneGeometry`, `AtomLabelRenderer`, `BondRenderer`, and the annotation builders
consume that context. Geometry and label drawing no longer resolve editing
services from a canvas. Bond-length edits and label prompts/history remain in
their editor services. Molecular drawing keeps its existing order: bonds,
labels and carbon dots, then incident-bond redraws.

`populate_document_scene` is the shared document-to-graphics path. It restores
drawing settings, background items, projection, molecule graphics, and
annotations. GUI document replacement remains responsible for its savepoint,
history, groups, sheet/view bounds, and selection/spatial state. A note's editor
focus callback is injected; its actual text layout and paint class is shared.
Whole-model ingress explicitly calls `prepare_molecule_for_scene` to retain
the existing whitespace/literal-label normalization. `render_molecule` itself
does not mutate the model, and the input document state remains unchanged.

`FigureExportService` resolves one export plan, checks budgets, paints to an
atomic temporary file, and performs the font-size check. The GUI adapter supplies
selected items and, when requested, embeds the editable document payload.
`render-document` and `check-layout` compose a `QGraphicsScene` directly under a
`QApplication`; neither needs a `CanvasView` or history. Commands that edit a
document (`layout-document` and `insert-template`) retain the editor assembly.

## Consequences

- The scene renderer remains Qt-dependent. This is an editor boundary, not a
  second Qt-free rendering engine or a new public document schema.
- GUI and headless output share drawing, sizing, resource limits, and font
  measurement. The command-line publication and report contracts are unchanged.
- Canonical shape and TS bracket records remain in the shared drawing state;
  editor accessors adapt to the same stores and lifetime policy.
- Existing rollback ownership is unchanged. Exact graphics snapshots also retain
  construction glyph runs, so a dagger's painted font can be restored after a
  failed redraw. Missing font provenance on an arbitrary path still fails closed.
- New drawing code must receive the context or explicit drawing collaborators,
  not resolve input, selection, history, or window services through a canvas.
