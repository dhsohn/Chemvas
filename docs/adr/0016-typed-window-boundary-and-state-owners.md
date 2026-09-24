# ADR 0016: A typed window boundary, and owners for state writes

- Status: Accepted
- Date: 2026-09-24
- Extends: [ADR 0012](0012-flat-editor-runtime-and-ui-packages.md), [ADR 0014](0014-one-spelling-for-canvas-and-window-state.md)

## Problem

ADR 0012 replaced the window's forwarder layer with direct attribute access,
and in doing so `chemvas.shell.main_window.MainWindow` lost its types:
`services` went from a small protocol to `Any`, and `runtime_state` and
`tab_references` were `Any` as well. Every `ui` function that takes a
`window` left the parameter untyped, so a misspelled service or a call with
the wrong arguments passed mypy. The review of #462 and #463 named this as
the one regression of the simplification: fewer layers is right, but not
paid for with `Any`.

The shell cannot import `ui`, where the concrete services, state and tab
references live, so the shell had described its runtime structurally and the
description had decayed to `Any` at the first inconvenience.

ADR 0014 also inlined 21 single-statement state writes such as
`set_document_display_name_for(canvas, name)` into direct field assignment.
Most are single-field writes with no invariant, but a few coordinate more
than one field, or coerce their value, and inlining spread that policy over
their call sites.

## Decision

1. `MainWindow` is generic in its runtime types. The five runtime objects
   (services, state, tab references, ui references, 3D preview) are type
   parameters; the three the shell touches are bounded by small protocols
   listing the members it relies on, the two it only carries (state, tab
   references) are bounded by `object`, and the shell stays free of `ui`. Bootstrap fulfils the
   contract with the classes it builds, and `MainWindowRuntime` is likewise
   generic so mypy checks that the runtime bootstrap hands over matches the
   parameters the window is instantiated with.
2. `ui` names the window type once. `chemvas.ui.window.main_window_like`
   binds the parameters to the concrete `ui` classes as `MainWindowLike`,
   bootstrap instantiates that alias, and every main-window parameter in
   `ui` (190 of them) is annotated with it; the about dialog, which needs
   only a parent widget, takes a `QWidget`. The alias is a real `QMainWindow`, so
   the window can be passed as a Qt parent, and its runtime properties are
   the concrete services, state and tab references.
3. The one `Any` that remains at the boundary is the preview's
   `shutdown_finished` signal in the shell protocol: mypy checks a type
   variable bound against the class-level `pyqtSignal` descriptor rather
   than the bound signal an instance yields, and neither spelling both
   admits `Preview3D` and offers `connect`. The reason is written next to
   it.
4. Optional Qt accessors are narrowed once. `QMainWindow.statusBar()` is
   typed `QStatusBar | None` although Qt creates the bar on demand;
   `status_bar_for(window)` in `main_window_ports` raises if it is missing
   and every caller uses it, instead of 27 unchecked `window.statusBar()`
   uses.
5. State writes that coordinate fields or coerce values are owner methods
   again, in a separate change: the document metadata state's display
   name, source digest and note-chrome invalidation; the clipboard's paste
   source and count, which always change together; the selection state's
   note clearing; the window callback binding; and the selection-info
   interaction stamp. Single-field writes with no invariant (`last_canvas_tab_index`,
   `last_export_format`, `next_atom_id`, the grid-snap flag) stay as field
   assignments.

The two decisions land as two changes, each with its own `make check`.

## Verification and limits

Annotating the `window` parameters surfaced 82 mypy errors, all in `ui`:
Optional Qt accessors used without a check, and `window` passed where a
`QWidget` was required. None was a latent crash; the second group is why the
alias is a concrete `QMainWindow` rather than a protocol. `make check` runs
the full gate on each change.

Not done: `ui/window` remains outside mypy's strict profile, so a `window`
parameter that is never annotated (in a nested function, or a test helper)
is still `Any`; and the `object`-typed `window` parameters in
`shell.window_registry` stay, since the registry deliberately treats windows
as opaque.
