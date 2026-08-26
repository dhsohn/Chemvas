# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Hash (dashed stereo) bonds no longer keep a frozen mark count after a
  gesture that changed their length. Dragging or rotating a selection
  refreshes boundary bonds in place, deliberately reusing the existing
  items mid-gesture — but nothing ever re-derived the count when the
  gesture ended, so a stretched hash bond kept its original sparse marks
  through commit, undo and redo, and figure exports, while reopening the
  document rendered the same bond with the correct density. Gesture ends
  and history replay now rebuild a bond whose derived count changed;
  mid-gesture updates still reuse the existing items.
- Transform handles can now be grabbed where they overlap the structure.
  The press hit-test ranked atoms and nearby bonds above everything else,
  so a curved-arrow endpoint handle sitting on an atom label — or within
  the bond pick radius — could never be picked up: the click selected and
  dragged the molecule instead. Handles now take priority, matching the
  order they are drawn in.
- The 3D-rotate tool no longer swallows mouse releases that end no
  rotation. Marquee-selecting on empty canvas with the tool active left
  the dashed rubber-band rectangle stuck on screen until the next mouse
  move, because every release was consumed before reaching the view.
- SMILES insertion now rejects isotope labels instead of silently dropping
  them. The document model has no isotope representation, so inserting
  d2-ethanol (`CC([2H])([2H])O`) drew plain ethanol and `[13CH4]` drew
  plain methane — every formula, identifier, and export then described the
  unlabeled compound with no warning. Isotope-bearing input now fails with
  a message naming the offending labels, the same way the SMILES reader
  already refuses alias-shadowed element symbols and the MOL reader
  refuses the mass-difference field.
- The selection formula/MW readout in the status bar now accounts for
  charge and radical marks. It used to compute on a bare copy of the
  selected atoms that dropped the mark layer, so a drawn methoxide read
  CH4O / 32.04 — the neutralized skeleton with implicit hydrogens
  completed to neutral valence — while the 3D panel showed the correct
  CH3O- / 31.03 for the same selection. The readout now derives its
  charge/radical annotations from the same mark layer that MOL/XYZ export
  and the 3D panel read. Adding or removing an atom-bound mark refreshes
  the readout immediately even when the selection itself is unchanged, and
  the readout cache now keys on the selected content (elements, bond
  orders, marks) rather than the selected ids alone, so a label or mark
  edit under a held selection recomputes at the next refresh instead of
  serving the old value.
- Save As and the XYZ/MOL/figure export dialogs no longer overwrite an
  existing file silently when filename normalization changes the target.
  The dialog's own overwrite prompt checks the name as typed; appending or
  replacing the extension afterwards (`aspirin` or `aspirin.v2` becoming
  `aspirin.chemvas`) could redirect the write to a file the dialog never
  asked about, and the atomic writer then replaced it without warning.
  When normalization retargets the write to an existing file, Chemvas now
  asks before replacing it; a path the dialog already confirmed is not
  asked about twice.
- The 3D conversion path no longer exports the enantiomer of the drawn
  molecule. The conformer that RDKit reads wedge/hash chirality from was
  built on raw canvas coordinates, whose y axis grows downward; RDKit
  perceives depictions y-up, so every stereocenter came out with the
  opposite absolute configuration — silently, because the wedge-vs-hash
  difference survives a mirror flip. The conformer now negates y exactly
  like the MOL writer always has. This corrects XYZ export, calculation
  artifacts (both the geometry and its MOL block), the 3D preview, and
  the MOL-export fallback used when a drawing contains abbreviation
  labels, which previously disagreed with the plain MOL export of the
  same drawing. A regression test now pins the absolute configuration of
  both routes against each other and against fixed R/S references.

### Changed
- The package-root surface guard now reads every module-level import binding
  — absolute and plain imports included, not only relative ones — so a
  removed re-export resurrected under an absolute spelling fails the guard
  the same way a relative one always did. Test change only; no import in any
  package root changed.
- Dropped an uncalled palette-menu method from the panel-toolbar test
  harness. Nothing has reached it since the production menu path went; the
  bans that keep that path removed are untouched.

## [0.5.0] - 2026-08-26

**If you import from `chemvas` in your own code, read the Removed section
first.** This release takes thirty-two names off the public import surface of
nine packages, and it changes what deleting a bond or an atom leaves behind on
the sheet. Everything else is bug fixes — see Fixed — and internal
housekeeping.

### Added
- Six names joined the public import surface: `SETTINGS_KEYS`,
  `VALID_ARROW_KINDS`, `connected_atom_components` and `included_atom_ids` on
  `chemvas.domain.document`, `fill_correspondence_gaps` on
  `chemvas.features.calculation_bundle`, and
  `selected_atom_ids_with_bond_endpoints` on `chemvas.features.selection`,
  which is the new name of a function listed under Removed. Nothing new was
  written: most of these are names the consolidation work below moved to a
  shared owner, which then had to be reachable from more than one module.

### Changed
- Corrected the module docstring on the graph index operations. Documentation
  only, nothing about the code changed — it called the whole module "pure"
  without saying what that meant, which read as side-effect-free even though
  the index helpers mutate in place the mapping they are handed. The docstring
  now says what "pure" is about here, namely what the module reaches: no Qt
  and no drawing surface, and no document type of its own — while recording
  that a neighbour it calls does pull the document package into the import
  closure. It also names the one operation that takes the whole graph state and
  writes a cache on it, with the reason its cache and its version have to
  arrive together.
- Removed five scene-access helpers, four of them called only by the test
  suite and the fifth stranded when those four went.
  Internal change only — no drawing, saving or exporting path reached any of
  them. Four of them wrapped a graphics-scene call the production code never
  made through this module: the whole-scene clear — which is not the live
  scene reset the document session, the canvas lifecycle and the SMILES insert
  all go through — the two item-group calls, and the canvas-scoped "can this
  item be added" probe. The fifth is the scene-scoped half of that probe: it
  lost its last caller with the probe and went in the same pass. The
  similarly named "is this item in the scene" pair stays, because the colour
  mutation service, the edit tools and the history commands still call it. A
  boundary test pins all five as removed, scoped to the module that defined
  them because the bare names read as prefixes of live surfaces elsewhere.
- Removed twelve orphaned glyphs from the design-icon SVG table. Internal
  change only — every icon the window, toolbars and context bars name still
  renders, checked by rebuilding the full reachable set (literal calls, the
  template label table, and every dynamically built arrow/preset/orbital/
  bracket/shape/stroke name expanded over its actual value domain). A render
  cannot carry that claim on its own — a name the table no longer holds draws
  the fallback glyph rather than raising — so the reachability rebuild is what
  it rests on. Eleven of the glyphs lost their
  last consumer when twelve icon accessors went; the twelfth, "select",
  turned out never to have had one — the select tool's accessor has always
  drawn the move glyph. A boundary test pins all twelve as removed.
- Folded the per-module bans on a vocabulary this repository never had into
  one repo-wide architecture rule. Test-only change; no production code moved
  and no rule lost a name. Eleven spellings of "ask the canvas for a service or
  a context by name" — `canvas_service_for` with its optional, runtime and
  optional-runtime variants, `resolve_canvas_graph_service`, the four
  context-cache lookups, `tool_context_for_canvas` and `canvas_instance_attrs`
  — were banned a target module at a time, though several of the rules carrying
  them already scanned the whole tree. Every blob in every ref was tokenised:
  not one of the eleven has ever been written anywhere in this repository, in
  any spelling, outside the rule file that bans them and this entry. A ban
  written one module at a time is a ban that can miss the next module, so it is
  repo-wide now. Five rules that carried nothing else are gone into it, one of
  them a call-shape rule the word-anchored ban strictly subsumes, and a sixth
  was renamed: it never had anything to do with `tool_context_for_canvas`, and
  its old title read as an instruction to write the name now banned. The rest
  keep the alternatives that guard something, and the context-cache rule keeps
  its check that the deleted module stays deleted.
  Verified by replaying the whole rule set before and after against a scratch
  copy of the tree, with no failure either way; by pulling every banned
  identifier mechanically out of both versions and confirming not one was lost;
  by planting each of the eleven names in every module an old rule named and
  confirming old and new both fail; by planting each of them in a module no old
  rule named, where `resolve_canvas_graph_service` and `tool_context_for_canvas`
  slip past every old rule and fail the new one; by planting a violation of what
  each of the twenty edited rules still guards and confirming each still fails;
  and, for the twenty-first, by resurrecting the deleted context-cache module.
  The file holds more identifiers with the same history of never having existed.
  They stay: splitting the ghost half out of the rules that carry them would
  break rules that read as one thought.
- Replaced every lambda in the structure-growth action record with the bound
  method it wrapped, finishing a conversion that had stopped at seven of the
  seventeen fields. Internal change only — every field forwarded its
  arguments unchanged, measured by calling each field through the record
  before and after with the same inputs. The ten lambdas that remained were
  load-bearing for the tests alone: nine tests in the structure-build suite
  swap a method on an already-built service, and late binding is what let the
  record see the swap. Those tests now rebuild the record through the same
  production wiring function once their mocks are in place, so each still
  asserts what it asserted before — that the growth path reaches the service
  method of that name with those arguments. The comment that explained which
  half of the record was which is gone with the split it described.
- Merged modules whose only production caller was a single other module into
  that caller. Internal structure only — nothing about how the application
  draws, saves or exports a document changes. The five main-window stylesheet
  sections (window chrome, canvas tabs, scrollbars, form controls and the
  status bar) each lived in their own module, and the only production code
  that read any of them was the module that concatenated them, so they now sit
  in it; the theme test reads all five individually and follows them there.
  The stylesheet the window is given is byte-for-byte the string it was
  before, and the theme test no longer reads the module's own source text to
  prove the sections have left it.
  In the same pass, nine functions in the insert access module that renamed
  another module's function and forwarded their own arguments to it unchanged
  are gone, and their callers now name the function they were always reaching.
  One of those callers had been importing the same function twice, once under
  each name.
- Removed guards that defended against states the code cannot reach, and
  narrowed two that were hiding real failures. Nothing about drawing, saving
  or exporting a document changes when the application is wired correctly —
  but when it is *not*, several operations that used to do nothing quietly now
  fail loudly. Session recovery keeps skipping a document it cannot read; the
  set of failures it treats that way is narrower now, and one it never
  recognised at all is covered (see Fixed). The internal service ports (across
  ten modules), the tool context's ports, the window and 3D-preview
  ports and the main window's status bar were all reached through capability
  probes that returned "missing" and let the caller substitute a silent
  default: a bond that was never sprouted, an arrow that was never added, a
  window that was never raised to the front, a 3D preview whose worker was
  never shut down. All of those were measured to resolve on a real assembled
  canvas and window when the change was made — no test pins the measurement —
  so the probes only ever absorbed wiring mistakes. They now
  raise where the mistake is, instead of producing a document that silently
  lacks what was asked for.
  Two swallows were narrowed rather than removed. A session snapshot that
  cannot be read is still skipped when the file is missing or corrupt, but a
  programming error in that path no longer masquerades as a corrupt document
  and drops unsaved work from the crash-recovery list. A failure to record a
  clean exit on quit is still tolerated when app-data is unwritable — the only
  cause it can have, and one whose consequence is the conservative one of
  offering recovery on the next launch — while anything else surfaces.
  Also folded in: the delete-tool session's port validation and its unwind
  (the session type makes every checked state impossible, while the rollback
  that legitimately leaves a session live still reports itself and is still
  retried), six defensive reads of a dataclass field that always exists (three
  more like them remain where the object handed in is not always that
  dataclass), three membership filters over ids that came from the model they
  were checked against, a CLI subcommand check argparse had already made, a
  "nothing to export" refusal duplicated in two modules, and a marker written
  into an exception's
  dictionary through four layers of indirection that cannot fail.
- Gave duplicated constants and helpers one owner each. This is internal
  housekeeping and changes nothing about how the application behaves. The
  arrow kinds are the part worth naming: the same seven strings were spelled
  out in seven modules besides the schema, so adding a kind to the document
  schema and missing one of the copies would have been silent — the document
  would accept the new kind while a scene, an outline, an attach route or a
  tool went on treating it as something else. All seven now read the schema's
  set, and the four supersets union it instead of relisting the members.
  Folded in the same way: the document-settings allowlist, a second copy of
  `normalize_3d`, a twice-compiled SHA-256 pattern, five one-line `getattr`
  wrappers (dropped in favour of the builtin), and three rollback helpers that
  had been pasted out longhand. Architecture tests fail if the arrow kinds, the
  settings allowlist, the SHA-256 pattern, a second `normalize_3d` or a
  function that only forwards to `getattr` is written again; of the rollback
  helpers only the colour note has a pin.
- Deleting a bond or an atom on the canvas now also deletes the atoms the
  deletion leaves invisible on the sheet. An endpoint or former neighbour that
  ends up with no
  remaining bond disappears with the deletion, in the same undoable step —
  unless a label or an attached charge/radical mark keeps it visible, in which
  case it stays. Erasing the only bond of a two-carbon fragment previously
  kept both atoms behind as invisible orphans; the eraser, the Delete key on a
  hovered bond or atom, and selection deletes — including Cut, which routes
  through the same delete — all clean up their newly bare invisible atoms now,
  and undo restores them together with the deletion. The headless
  `apply-patch` is deliberately not part of this: its `remove_bond` still
  leaves a bare atom, as `docs/AGENT_CLI.md` says it does.
- The source distribution no longer ships the test tree, and the release gate
  now verifies the sdist's contents the way it already verified the wheel.
  Every published sdist carried 300+ `test_*.py` files without `conftest.py`
  and the other support modules the default packaging glob skipped, so the
  shipped tests could never be collected. The wheel — what `pip install
  chemvas` installs — never carried them and is unaffected by the packaging
  change.
- Gave eight more duplicated algorithms one owner each, and deliberately left
  one where it was. Internal housekeeping again; nothing about the application
  behaves differently. The bond-cycle cache is the part worth naming: two
  functions answered "is this bond in a ring?" with identical code and both
  wrote the answer into the same cache, so the rule for when a cached answer
  goes stale was written twice and could have been changed on one side only.
  The survivor is `cached_bond_in_cycle`, which is new on that module.
  Folded the same way: three depth-first reachability walks, the
  capture-and-roll-back scaffold the group and ungroup history commands each
  spelled out twice, the pair of scene-item detach helpers, the eleven-key
  fingerprint that pins a reaction precomplex to the geometry it was built
  from, the ring-fill polygon rebuild the move controller kept a private copy
  of, the scene-item pool reset the preview and hover renderers each spelled
  out, and the atom-state restore the add-atoms and delete-atoms history
  commands each wrote twice. Each merge was checked against the code it
  replaced over the inputs that would expose a difference — random graphs,
  injected rollback failures, deleted scene objects — and none of them changed
  an answer. Architecture tests pin all eight and fail if one of them is
  written a second time; they were checked against the tree from before each
  merge to confirm they report the copies that were really there.

  What did not merge is recorded at both of its sites: the shared tail of the
  atom and bond delete paths was written as a shared helper, measured at 24
  net lines longer than the copies, and reverted. A fourth scene-item pool
  reset stays in `features.selection.handles`, which is in a layer that never
  imports `ui` and so cannot reach the owner, and says so where it sits. Both
  precomplex geometry checks were kept even though the second cannot fail when
  reached through the first, because the other caller reaches it without the
  first.
- The pull-request checklist now asks for one command, `make check`, instead of
  three hand-listed ones. `python -m ruff check .`, `python -m mypy` and a
  narrowed pytest run leave out `ruff format --check` and the `machine.json`
  conformance check, so a contributor could tick every box and still not have
  run the gate. In the same pass: `wheel` left `[build-system].requires`
  (setuptools carries `bdist_wheel` itself, and both build sites go through
  `python -m build`), the CI test job runs pytest directly rather than through
  a coverage wrapper that had no threshold and whose uploaded artifact nothing
  read, and the feature-request template stopped offering MOL export — which
  ships — as its example of a missing feature.
- Removed seventeen `CanvasStyleController` methods with no production caller.
  Setters and getters for text size, selection colour and stroke delta, text
  font, weight, italic and line spacing, and the note box's fill, alpha, border
  and padding were all reachable only from the tests; the panels and context
  bars that change those settings route elsewhere. Nothing on the sheet
  changes.
- Removed six `RDKitAdapter` methods that only the tests called —
  `model_to_rdkit`, `model_to_rdkit_with_map`, `model_to_rdkit_tolerant`,
  `suggest_atom_correspondence`, `model_to_3d_coords` and `model_to_3d` —
  together with the `tab_reactions_suspended` field and the two ports that
  carried it. SMILES insertion, MOL export and the 3D preview reach RDKit by
  other methods that stay.
- The contributing guide no longer restates the architecture discipline in its
  own words. `docs/ARCHITECTURE.md` is the normative text, `CONTRIBUTING.md`
  keeps the worked example, the list of patterns the boundary tests reject, and
  the steps for migrating a feature, and points at the rest.

### Fixed
- Every command that reads a JSON file now reports an oversized number as
  malformed input instead of raising a bare arithmetic error. JSON floats are
  parsed as `Decimal`, which fails in two different places: an exponent it
  cannot represent at all is refused by the constructor, while one inside that
  bound but past the arithmetic context's limit constructs quietly and raises
  the first time it goes through an arithmetic operation. Both failures are
  `ArithmeticError`s and neither is a `ValueError`, and neither was caught: of
  the loader's nine call sites eight guard `ValueError` and its neighbours and
  one does not guard at all, while the range check that rejects an oversized
  coordinate named `OverflowError` — which is `decimal.Overflow`'s sibling
  rather than its parent — around an `abs()` that raises the latter. So every
  headless subcommand that reads a document or a JSON input — `check-layout`,
  `compose-document`, `apply-patch`, `attach-plan`, `generate-precomplex`,
  `render-document` and the `inspect` family among them — exited with a Python
  traceback on some band of oversized numbers while refusing others cleanly,
  and the same values could escape when opening an editable SVG or pasting a
  selection. Both bounds now
  reject the value the way a duplicate key or a `NaN` already was.
- Session recovery no longer aborts the launch on a recorded document holding
  such a number. Recovery runs before the event loop starts and skips documents
  it cannot read; this release narrowed that skip from any exception to
  `OSError` and `ValueError`, which would have turned either arithmetic failure
  into a fatal one. A recorded session is only pruned once a recovery finishes,
  so the failure would have repeated on every launch.
- The headless commands that create a new file — `compose-document`,
  `apply-patch`, `render-document` and the calculation bundle writers — no
  longer close a file descriptor they have already handed away when the write
  fails. `atomic_create_bytes` gives the staging descriptor to `os.fdopen`,
  which closes it on its way out, and the failure path then closed it a second
  time with the resulting `EBADF` swallowed, so nothing surfaced. Had the
  process opened another file in between, that second close would have landed
  on the new file instead. The owner is now unambiguous: the handover has its
  own failure path, the one case where the descriptor is still ours, and
  nothing after it touches the number. Two tests cover the two sides; the
  first fails on the previous code. Saving from the editor goes through a
  different writer and was never affected.
- A failed ungroup now names the operation it was rolling back, instead of
  the opposite one. When a recovery step fails, a note attached to the error
  says which recovery was attempted; the ungroup command had both of its
  directions backwards, reporting "after grouping" when it had been
  ungrouping and "after ungrouping" when undo had put the groups back. The
  wording had been copied from the grouping command, where redo does group
  and undo does ungroup, so it followed the undo/redo slot rather than the
  operation. Only the text changes — no recovery step was added, removed or
  reordered.
- The Korean README's Agent CLI row now lists document composition and the
  layout check next to render, inspect and the hash-gated Graph Patch. Both
  `compose-document` and `check-layout` ship and the English README names them,
  so a reader of `README.ko.md` alone had no way to learn the CLI can build a
  document or report layout collisions without editing one.
- Documentation that was no longer true: `docs/images/README.md` described the
  README hero as a reaction scheme plus several organocatalyst structures,
  while the image in place is the C–P bond cleavage scheme under KOtBu / THF
  from `examples/template2.chemvas`, and it named the wrong capture file and
  regeneration command alongside it.

### Removed
- **The silent zero in the pick-radius accessors.** `atom_pick_radius_for`
  and `bond_pick_radius_for` used to answer `0.0` when the canvas could not
  supply a radius, which is a canvas on which nothing is clickable; both now
  let the failure surface. Like the other guards removed here, this only
  changes what happens when the application is wired wrongly.
- **The capture path's dormant non-strict mode.** `capture_scene_runtime` and
  `capture_atom_primitive_graphics` declared `strict=False`, but all 19 call
  sites in the tree — thirteen in production, six in the tests — pass
  `strict=True`, so the lenient half never ran. Nothing changes today; what
  goes is a mode that, had anything ever selected it, would have swallowed a
  capture failure in silence: `contextlib.suppress(Exception)` around a child
  or geometry read, `continue` past an item whose accessor raised, and
  assignments blanking the parent, stacking-depth, signal-blocking and focus
  port pairs. Each produced a partial snapshot that undo would then restore
  from, with nothing recorded to say a field was missing. The parameter is gone
  from the ten capture-side functions and the strict arm is now
  unconditional. Carrying that removal one step further,
  `_verify_scene_membership` was left forwarding its `strict` to a helper that
  ignores it, and `_direct_scene_remove` and `_direct_scene_add` only ever
  passed it on to that same dead end, so all three lost the parameter; four
  restore-side call sites drop the argument. What
  remains of the restore side keeps its flag — there it is genuinely dynamic,
  strict during a normal restore and best-effort while a rollback is already
  unwinding — so `_item_parent` and `_item_is_attached_to_scene` still take
  `strict=errors is not None`. The scene-item helpers keep the flag for a
  different reason: the rollback inside `create_scene_items_atomically` reads
  the scene leniently, by omitting the argument, so that a scene which can no
  longer answer does not mask the failure already being unwound.
- **Five parameter names their functions never read**, over six removal
  sites — two functions each lose the same session-state parameter.
  `tool_action_key_for_canvas_state` branches on the active tool alone, so
  `active_bond_style` and `mark_kind` go, and the toolbar sync no longer looks
  up the tool settings to supply them. That lookup was the last caller of the
  `tool_settings_for_window` window port, so the port goes as well, together
  with the constructor parameter carrying it into the tool state service and
  the composition-root wiring behind it. `tool_settings_state_for`, the
  canvas-level accessor it wrapped, is untouched and still read directly
  wherever the tool settings are actually needed. `begin_template_insert` and
  `begin_smiles_insert` ignored the session state they were handed and built a
  fresh one; their `cancel_*` siblings do read it and keep theirs.
  `apply_pasted_perspective_for_canvas` took a `projection_anchor_2d` it never
  used, taking the anchor from the canvas rotation state instead — the
  identically named field, and `projection_center_3d`, are both still read. The
  rotation preview's `restore` took the in-flight exception and ignored it; the
  rollback note it feeds is still added by the caller. No behaviour changes.
- **The last three hand-painted icon renderers.** `MainWindowBondIconRenderer`,
  `MainWindowUtilityIconRenderer` and `MainWindowToolIconRenderer` drew the
  toolbar icons until the SVG design set took over, and
  `MainWindowIconCanvasStyle` was the port that fed the bond one. Like the
  arrow renderer retired before them, the cutover dropped every call into the
  three classes but kept constructing them, so a second source of icon geometry
  stayed in the tree with nothing reading it. The modules, their construction,
  their tests, and the twelve icon accessors that no longer had a production
  caller are
  gone, and the modules join the list production code may not import again.
  `main_window_icon_geometry.py` and the two icon fill tokens the renderers
  were the last readers of went with them. No icon changes appearance.
- **Two tools that were never registered.** `TransformTool` and `EditBondTool`
  were complete `Tool` subclasses, but neither name appears in the tool
  registry `ToolController` builds, so no toolbar button, shortcut, or menu
  could ever activate them — only the tests constructed them. Both classes and
  the helpers they were the last caller of are gone:
  `show_orbital_handles_for` (the live rotate handles still come from
  `HandleOverlayService`) and `ToolContext.bond_id_from_event` (the
  identically named hit-testing service method stays, because the right-click
  context menu uses it). Nothing changes on the sheet.
- **Eleven snap-setting accessors with no caller.** `CanvasToolModeController`
  exposed setters and getters for curved-arrow snapping, curved-arrow
  symmetry and orbital-handle snapping, and a setter for the bond snap angle
  (which never had a getter), but no menu,
  toolbar, context bar, or shortcut ever called any of them. Two consequences
  are real, though both were already the state of the shipped application:
  curved-arrow midpoint snapping and orbital rotate-handle angle snapping are
  now permanently off — they defaulted to off and had no interface to turn on —
  and bond-angle snapping stays fixed at 30°, which is what it was set to
  everywhere. The `curved_symmetry` field, which nothing ever read, and the
  unused `TOOL_SETTING_ATTRS` tuple went with them; the four snap fields the
  handle code still reads stayed.
- **Ten `*_access` ports with no production caller.** `rebuild_graphics_for`,
  `scale_qpoints_to_bond_length`, `mark_offset_from_click_for`,
  `visible_label_rect_for_atom_for`, `mark_clearance_for_kind_for`,
  `label_cut_radius_for_atom_for`, `build_selected_structure_payload_for`,
  `selection_signature_for`, `add_benzene_template_for` and
  `bold_bond_width_for` each forwarded to a service the application already
  reaches directly — except `selection_signature_for`, which is a pure
  function, and `scale_qpoints_to_bond_length`, which wraps a domain function
  in Qt point conversion — so the wrapper was a second door nobody used. Two
  scene helpers, `clear_canvas_scene_item_map` and
  `clear_canvas_scene_item_list_map`, lost their only production caller with
  `rebuild_graphics_for` and went too. The live
  `renderer_bold_bond_width_for` — a different function with a similar name —
  is untouched.
- **Six service methods only the tests called.**
  `CanvasGraphService.atom_bond_order_sum`,
  `CanvasGeometryController.ring_for_bond`,
  `DeleteSelectionPlan.has_work`, `MainWindowStatusService.zoom_status_tip`,
  `MainWindowState.reset_canvas_name_counter`, and the
  `_snapshot_canvas_scene` module function are gone. The private helpers and
  neighbours they sat next to — `_ring_items_for_bond`, `has_zoom_label`,
  `_DetachedSceneSnapshot.capture` — are live and stay. The module-level
  `reset_rdkit_export_job_state_for_tests` wrapper went too; it was a second
  name for `RDKitExportJobRegistry.reset_for_tests`, which stays.
- **Exports and members nothing reads.** `compute_identifiers_for` (the access
  wrapper, not the live `compute_identifiers`), `TEXT_STYLE_ATTRS`,
  `CANVAS_TEMPLATE_FIELDS`, `DESIGN_ICON_NAMES`, `HEADLESS_SUBCOMMANDS`,
  `SceneDeleteController._restore_observer_ports`,
  `StructureBuildService.latest_bond_id` and `.viewport_center`, and the
  `hash_bond_width` and `wedge_width_px` fields on `ACS1996Style`. None of the
  ten had a production reader; the two style fields in particular never reached
  the
  renderer, so no drawn bond changes. The similarly named survivors —
  `_try_restore_observer_ports`, `viewport_center_scene_pos_for`,
  `renderer_bold_bond_width_for`, `CANVAS_TEMPLATE_TOOL_FIELDS`,
  `CANVAS_TEMPLATE_TEXT_FIELDS`, `has_design_icon` — are untouched.
- **The QMenu population path in `MainWindowToolRoutingService`.** Nothing in
  the application called `populate_template_menu`, `populate_arrow_menu`, or
  `populate_palette_menu`: the context bar page factories draw the same
  template, arrow, and palette entries directly. Following the cascade to its
  fixed point also retired `add_menu_action`, `palette_icon`,
  `template_entries`, `acs_color_palette`,
  `activate_arrow_type_from_menu`, `activate_arrow_preset_from_menu`, and the
  stranded `build_template_entries`. `apply_color_preset` and
  `apply_ring_fill_preset` stay — the panel toolbar routes through them — as do
  `ARROW_MENU_SPECS`, `ARROW_PRESET_SPECS`, `COLOR_PALETTE_SPECS`,
  `icon_arrow_preview` and `icon_template_preview`.
- **The canvas tab reorder wiring.** Each window holds a single canvas and the
  tab strip is hidden, so `tabMoved` was connected to a handler that discarded
  its arguments. The handler, the closure and parameter that carried it, and
  the `setMovable(True)` call are gone: canvas tabs are no longer marked
  movable. Nothing was reorderable in practice, since the strip is not drawn.
- **Thirty-two names off the public import surface of nine packages.** This
  narrows what `chemvas` offers to importers, so it is an API reduction rather
  than housekeeping: code outside this repository that did
  `from chemvas.features.rendering import DOUBLE_STYLE_SEQUENCE` has to import
  it from `chemvas.features.rendering.bond_style` now. Nothing inside the
  repository did — each was checked against every tracked file with no path or
  extension filter. Thirty-one appeared only in the package root that
  re-exported them and the module that defines them, and those thirty-one stay
  where they are and stay importable from the module named beside each below;
  only the package-level re-export goes. The exception is
  `selected_rotation_atom_ids`, which is not a re-export removal at all: it was
  renamed to
  `selected_atom_ids_with_bond_endpoints` and moved from
  `features.selection.rotation` to `features.selection.hit`, so the old name
  now resolves nowhere.
  Gone from `chemvas.domain.document`: `CALCULATION_INCLUSIONS`,
  `CALCULATION_PLAN_FORMAT`, `CALCULATION_PLAN_VERSION`, `CALCULATION_ROLES`
  and `CalculationEndpointPrecomplex` (all in `.calculation_plan`), and
  `SUPPORTED_FILE_VERSIONS` (in `.state`). From `chemvas.features.rendering`:
  `BOLD_DOUBLE_STYLES`, `BOLD_DOUBLE_STYLE_SEQUENCE`, `DOTTED_DOUBLE_STYLES`,
  `DOTTED_DOUBLE_STYLE_SEQUENCE` and `DOUBLE_STYLE_SEQUENCE` (in
  `.bond_style`), and `DEFAULT_BOLD_OUT_LENGTH_SCALE` (in `.bond_geometry`).
  From `chemvas.features.insertion`: `SmilesPreviewPlan`,
  `SmilesPreviewSnapshot` and `snapshot_smiles_preview_geometry` (in
  `.smiles`), `TemplatePreviewPlan` (in `.template_preview`), and the lazily
  loaded `ring_polygon_points_for_atoms` (in `.ring_occupancy`), which also
  leaves the lazy-export table. From `chemvas.features.selection`:
  `LineStrokePathBuilder` and `PenWidthGetter` (in `.outline`),
  `ROTATION_DRAG_SENSITIVITY` and `RotatePointAroundAxis` (in
  `.rotation_geometry`), and the renamed `selected_rotation_atom_ids`. From
  `chemvas.features.document_composition`: `COMPOSITION_FORMAT`,
  `COMPOSITION_VERSION` and `MAX_BONDS` (in `.service`). From
  `chemvas.features.calculation_bundle`: `PathPrecheck` and `StepReadiness` (in
  `.plan`). From `chemvas.features.document_patch`: `DOCUMENT_PATCH_FORMAT` and
  `DOCUMENT_PATCH_VERSION` (in `.service`). From `chemvas.features.session`:
  `RestorePlan` and `SESSION_SCHEMA_VERSION` (in `.logic`). From
  `chemvas.features.export`: `MM_PER_INCH` (in `.plan`).
  `HoverAction` is a near miss worth naming: it left
  `chemvas.features.hover`'s `__all__`, so `import *` no longer offers it, but
  it is defined in that package root and stays importable by name.
  `normalize_3d` and `SHA256_HEX_RE` are untouched: each has a reader, and each
  was put where it is on purpose. `VALID_ARROW_KINDS` moved the other way and
  is now public — see Added.
- **The `chemvas.ui.canvas_state_lookup` module.** Its two production callers
  were rewritten off it and the module was deleted. Both rewrites tightened
  what they accept: the document-metadata accessor used to build and attach a
  metadata state when the canvas had none and now reads the one the runtime
  state carries, and the scene-runtime snapshot lookup dropped its fallback to
  a public attribute of the same name along with its leading-underscore
  stripping. As with the other guards removed here, a correctly wired canvas
  sees no difference.
- **The unused context-bar segment button.** `segment_button` and the
  `CONTEXT_SEGMENT_STYLE` it painted with had no caller anywhere in the tree;
  no context bar ever drew one.

## [0.4.1] - 2026-08-20

### Fixed
- `chemvas compose-document` crashed with a Python traceback and exit status 1
  on a wrongly typed `bond_length_px` canvas setting — `null`, a list, an
  object, or an integer beyond float range. That one value feeds the
  electronic-mark distance arithmetic before the document rules examine it;
  every other settings key was already refused cleanly. The merged settings are
  now validated by those rules before any value is used, so `bond_length_px` is
  refused the same way, with a `chemvas: error:` message and exit status 2.

## [0.4.0] - 2026-08-17

### Added
- **Public headless document composer**: `chemvas compose-document` compiles a
  strict, bounded Composition v1 manifest into a canonical, reopenable Chemvas
  document and publishes it atomically without replacing an existing output.
- **Deterministic layout diagnostics**: `chemvas check-layout` reports bounded,
  read-only note overlap, note/shape-border collision, and sheet-clipping
  warnings with stable persisted item indices and source hashes.
- **Structured note styles and electronic annotations**: headless composition
  accepts sanitized structured text styles and authoritative formal-charge and
  radical annotations, deriving consistent linked visual marks before
  publication.

### Changed
- The README hero image and example now show `examples/template2.chemvas`
  (the C–P bond cleavage scheme); fixed a title typo in that document
  ("Cleavege" → "Cleavage").
- Restructured `README.md` / `README.ko.md` into a short landing page (identity,
  statement of need, quickstart, capability table, docs index). The detailed
  user documentation moved to `docs/REFERENCE.md` and the headless/agent
  contracts to `docs/AGENT_CLI.md`, both without content changes. The docs-sync
  guards now pin the file-format example and tool hotkeys to `docs/REFERENCE.md`
  and additionally pin the READMEs' prose mention of the current document
  version.
- The CI job that installs RDKit now runs every RDKit-gated test file — the
  two calculation integration modules, the molfile round trips, and the whole
  adapter file — instead of selecting name-prefixed tests inside one file.
  Measured in a no-RDKit environment mirroring the main CI job, 36 tests gate
  on a real RDKit and only 11 carried the selected prefix, so 25 ran in no CI
  job at all. A new guard pins the workflow's file list to the gates in the
  test tree, in both directions. The main job in turn no longer runs the two
  modules whose module-level gate skips every test without RDKit — those runs
  executed zero tests — and the same guard pins that exclusion list too, so a
  file with ungated tests cannot be excluded by mistake.
- Multi-part atom labels now anchor the attachment-side token at the atom and
  reverse their displayed groups when necessary (`CF3` → `F3C`, `OTs` → `TsO`,
  `Ph3P` → `PPh3`). This keeps attached bond lines at full length without
  changing the label stored in the document.
- Document validation now bounds the global `text_font_size` setting to the
  6–96 pt range that interactive editing has always enforced; the reader
  previously accepted any size of 6 pt or larger. No Chemvas-written document
  is affected, since no editing path could store a larger value. *(This entry
  was added after the 0.4.0 release to document a change that shipped in it.)*

### Fixed
- The **Equilibrium** arrow now draws the conventional harpoon pair (⇌): one
  barb per line, both on the outside of the pair, with the forward arrow on
  top. Each line previously carried a full arrow head (⇄), which denotes two
  separate opposing reactions rather than an equilibrium. Documents saved
  earlier re-render with the corrected arrow; the stored file format and the
  arrow's `equilibrium` kind are unchanged.
- External JSON inputs now reject duplicate object keys and non-standard numeric
  constants instead of silently accepting a parser-dependent interpretation.
  This applies consistently to Chemvas documents, Calculation Plans, graph
  patches, precomplex requests, editable SVG metadata, and clipboard payloads.
- Autosave no longer replaces a complete recovery snapshot with a warning-bearing
  partial snapshot, such as one that would omit a temporarily inconsistent
  Calculation Plan. The last good snapshot remains recoverable, and a persistent
  status-bar warning stays visible until a later autosave succeeds cleanly.
- Bold double bonds in rings now thicken inward like bold single bonds, so
  adjacent strips meet in sharp mitred corners instead of leaving a clipped
  corner or white wedge.
- The abbreviation labels `Ts` (tosyl) and `Ac` (acetyl) are also the element
  symbols for tennessine and actinium, and three conversion paths resolved them
  as those elements instead of as abbreviations. All of them now treat the
  labels the way they treat every other abbreviation.
  - MOL export wrote them into the atom block as elements rather than taking
    the RDKit expansion path, so one drawing exported different chemistry to
    `.mol` than to `.xyz`. A molfile whose atom symbol is `Ts` or `Ac` is also
    rejected on import now, instead of being read back as the abbreviation.
  - Molecule Info reported a formula, molecular weight, SMILES, and InChI
    computed from tennessine or actinium: a drawn methyl tosylate came back as
    `CH3OTs` at 323.03 rather than `C8H10O3S` at 186.23. Those identifiers now
    stay blank, as they already did for `Ph`, `Me`, and every other
    abbreviation.
  - SMILES insertion placed an atom the rest of the app then read as the
    abbreviation: typing `C[Ac]` drew what Chemvas treats as an acetyl group.
    A SMILES asking for either element is now refused with a message naming the
    symbol, isotope-qualified forms such as `[227Ac]` included. Every other
    element, and every isotope of one, still imports.
- **Suggest by structure** closed Chemvas when the drawing contained an atom
  RDKit cannot sanitize — a neutral nitrogen still carrying four bonds because
  its charge has not been added yet, a carbon that briefly holds five, and
  similar work-in-progress states. The window disappeared without a message,
  taking every atom correspondence mapped in that dialog with it. The
  suggestion now runs on the connectivity as drawn; the structure's real
  problem is still reported where it always was, by the 3D preview and by
  `.xyz` and calculation-step export.
- **Suggest by structure** also reported every failure as "RDKit found no
  shared substructure beyond what is already mapped" — a chemistry claim about
  the drawing that was false whenever the tool, not the chemistry, was the
  problem. Without RDKit installed the button stayed enabled and gave that
  same answer (the 0.2.0 notes said the button is disabled in that case; it
  never was), an endpoint whose components are all context-only got it too,
  and a substructure search that stopped early discarded an already-computed
  mapping and reported it as no shared substructure — on a symmetric
  host–guest pair, about 4 clicks in 10. Each case now says what happened:
  a missing RDKit names the `chemvas[rdkit]` extra to install, a stopped
  search says to try again, an empty endpoint is named, and only a genuinely
  empty comparison keeps the no-shared-substructure sentence.

### Removed
- **Per-shape arrow icon renderer**: `MainWindowArrowIconRenderer` painted the
  arrow previews, presets, and the width/head controls until the toolbar-icon
  unification moved all of them to the shared SVG design set. That change
  dropped every call into the class but kept constructing it, so a second
  source of arrow icon geometry stayed in the tree and drifted — it still drew
  the equilibrium arrow with two full heads after the canvas moved to harpoons.
  The module, its construction, and its tests are gone, and the module now sits
  on the list production code may not import again. No icon changes appearance.

## [0.3.0] - 2026-08-13

### Changed
- **Current-only document contract**: Chemvas now reads and writes document
  version 7 only, with compact bond arrays and Calculation Plan v2 when a plan
  is present. Earlier document versions and Calculation Plan v1 payloads are
  rejected instead of being upgraded or read through compatibility branches.
- **Current-only precomplex contract**: precomplex generation accepts request
  format v2 with `chemvas-rigid-precomplex-placement/2` only. The frozen v1
  request/profile reproduction path and its partly unverified radius table have
  been removed.
- **Canonical desktop paths**: saved Chemvas drawings use `.chemvas` across
  startup arguments, OS file-open events, File Open, Open Recent, clean-session
  restoration, Save, and Save As; `.svg` and `.mol` remain explicit import
  inputs. Stale unsupported recent/session paths are ignored. Current internal
  crash autosaves can recover their drawing state, but an unsupported original
  path is cleared and the recovered canvas opens unbound and unsaved.

### Removed
- Removed deprecated export facades, history aliases, selection-style wrappers,
  bracket/bold compatibility aliases, and legacy version/profile constants so
  retired contracts cannot silently return.

## [0.2.0] - 2026-08-13

### Added
- **Reviewed precomplex ensembles and document version 6**: Calculation Plan v2
  can persist bounded deterministic rigid-placement candidates for two-component
  reactant and product endpoints, including exact XYZ, environment, contact,
  validation, and generation provenance. `generate-precomplex` creates the
  candidates, `inspect-precomplex` reports them, and `select-precomplex` records
  an explicit reviewer selection. `pack-step` regenerates the ensemble and
  rejects stale or unreproducible selections before publishing a reviewed
  endpoint pair; the coordinates remain initial guesses for downstream quantum
  optimization and scientific review.
- **Context-validated attached `PPh3` alias expansion**: a `PPh3` atom label
  connected to carbon by one ordinary covalent single bond now expands into an
  explicit four-coordinate `[P+](Ph)3` fragment for 3D `.xyz` conversion,
  Molecule Info, and elementary-step geometry. Standalone, metal-coordinate,
  non-single, styled, and explicitly re-annotated contexts fail closed.
- **Structural atom-mapping suggestions**: the Calculation dialog's atom
  correspondence editor gains a **Suggest by structure** button that fills
  unmapped reactant atoms from the maximum common substructure of the included
  reactant and product (RDKit). Bond orders are matched loosely, so atoms whose
  bonds only change order — a typical reaction center such as C-O → C=O — are
  suggested too; only atoms whose connectivity actually breaks or forms are left
  for you. It only fills gaps — it never overwrites a mapping you set, keeps the
  same-element rule, and reuses no product atom. The button is disabled when
  RDKit is unavailable.
- **Atom-id labels on the canvas**: while the Calculation dialog is open, every
  included atom is labelled with its stable Chemvas id on the drawing (reactant
  atoms tinted blue, product atoms orange), so a correspondence-table row can be
  matched to a spot on the structure at a glance. The labels are transient
  overlays that never change the document or selection.
- **Sulfonate and acyl alias labels**: `OTs`, `Ts`, `OMs`, `Ms`, `OTf`, `Tf`,
  `Ns`, `OAc`, and `Ac` now expand into explicit fragments for 3D `.xyz`
  conversion, Molecule Info, and elementary-step geometry, instead of being
  rejected as a single opaque pseudo-atom. `Ns` is the para
  (4-nitrobenzenesulfonyl) isomer.
- **Role-aware endpoint locking in the Calculation dialog**: once a drawn
  component is included as a step's reactant (or product), the same
  component's opposite endpoint is disabled, so a consumed species cannot be
  assigned to both sides by mistake. The lock is role-aware — catalysts and
  spectators stay editable on both endpoints — and only disables the other
  side; it never clears an existing selection, so changing the role back
  restores it.
- **Single-file elementary-step artifact**: `inspect-plan` reports stable
  source-mapping, electronic-state, and component-count blockers, while
  `pack-step` atomically writes one non-overwriting `machine.json` using
  `factory/machine-observation` v1 with a `chemistry/elementary-step` v1 payload.
  The payload inlines source and RDKit provenance, atom correspondence, bond
  changes, and for a qualifying single-component step, exact reactant/product
  XYZ in one reactant atom-identity order with canonical 0-based reaction-center
  indices. Readiness and exact blocking codes live in the common `handoff`
  field; the former step-specific envelope, multi-directory bundle, and separate
  endpoint files are removed.
- **Headless document rendering**: `chemvas render-document` now renders a
  bounded `.chemvas` drawing to a new SVG or PNG through the canonical figure
  exporter without opening a desktop window or loading RDKit. It preserves the
  source, refuses replacement and symlink targets, atomically publishes only a
  complete output, and reports exact source/output hashes plus point/pixel
  dimensions as deterministic JSON.
- **Canvas mapping highlights**: selecting an atom-correspondence row or
  browsing its product choices temporarily marks reactant and product atoms on
  the drawing with distinct R/P colors and line styles. The dialog owns and
  removes these non-selectable overlays without changing the document,
  selection, history, or dirty state.
- **GUI atom correspondence editor**: the Calculation dialog now maps each
  included reactant atom to a same-element product atom by stable Chemvas ID,
  preserves explicit unmapped partial drafts, reports mapped/total readiness,
  and rejects duplicate product assignments before the existing `pack-step`
  gate. Exact atom IDs shared by both endpoints are suggested without inferring
  a mechanism.
- **Agent-safe graph patches**: `chemvas inspect-document` exposes stable atom IDs,
  exact source hashes, and the complete graph without Qt; `chemvas apply-patch`
  dry-runs or atomically publishes a new non-overwriting document after strict
  versioned JSON, document, and Calculation Plan validation. The bounded v1
  operation set edits atoms and bonds without invoking a language model or
  inferring chemistry.
- **macOS application name**: the menu bar now reads **Chemvas** instead of the
  interpreter or script name. Run from source or from a `pip install`, the
  process has no `Info.plist`, so Qt fell back to the basename of `argv[0]` and
  macOS to the process name; Chemvas now supplies `CFBundleName` itself before
  the `QApplication` is built. A real `.app` bundle already names itself and is
  left alone.
- **Menu bar**: standard **File / Edit / View** menus (alongside the existing
  Help menu) expose New Canvas, Open / Open Recent, Save / Save As, exports,
  Undo / Redo, clipboard and selection commands, flips and rotation, zoom
  controls, and the Molecule Info window — with the platform shortcuts shown
  where they apply.
- **Canvas Size dialog**: File ▸ Canvas Size… changes the sheet size and
  orientation of the active document.
- **Eraser tool**: click or drag to erase atoms, bonds, and annotations; one
  drag records a single undo step.
- **MOL import**: File ▸ Open reads MDL Molfiles (`.mol`, V2000) into a new
  untitled document, no RDKit required. Property records are limited to
  `M  CHG` / `M  RAD`, and wedge/hash stereo to single bonds. Malformed or
  unsupported files are rejected with a specific error instead of a
  best-effort guess; nonzero counts-line chiral flags and singlet radical code
  1 are currently rejected rather than silently losing spin/stereo semantics.
- **Copy InChI**: the Molecule Info window now offers the full InChI string
  alongside the existing SMILES and InChIKey copy buttons.
- **Autosave & crash recovery**: open documents are snapshotted to a per-user
  app-data folder every few seconds. After an abnormal exit the next launch
  restores the unsaved work — flagged unsaved with a `●` and a status-bar note —
  while a clean quit reopens whatever files were open, so the last session comes
  back automatically. Snapshots are pruned once a session is restored or closed
  cleanly, and a still-running instance's session is never touched.
- **Open Recent**: the File menu lists recently opened/saved documents (entries
  whose file has disappeared are pruned) with a **Clear Recent Files** action.
- **Unsaved indicator**: a modified document shows a `●` dot on its tab and the
  platform's native modified marker in the window title, cleared on save.
- **Duplicate-open guard**: opening a file that is already open switches to its
  window instead of creating a second, independently-editable copy.

### Changed
- **Canonical Chemvas document extension**: the desktop Open and Save As
  dialogs and startup argument dispatch now advertise and recognize Chemvas
  documents only as `.chemvas`, not the old `.json` filename alias. Rename any
  Chemvas documents that still end in `.json` to `.chemvas` before upgrading;
  JSON request, inspection, patch, and machine-artifact files used by headless
  commands are unaffected.
- **Cited, immutable precomplex radius profile**: new request format v2 requires
  `chemvas-rigid-precomplex-placement/2`, whose complete supported-element
  radius table uses Cordero (2008) Table 2 covalent radii and Alvarez (2013)
  Table 1 van der Waals radii with exact dataset, DOI, selector, and table-hash
  provenance. Frozen request/profile v1 remains byte-reproducible for existing
  documents. Generation, inspection, deterministic regeneration, endpoint-pair
  validation, and `machine.json` now route and report the persisted profile;
  mixed profiles or altered provenance fail closed. The scores remain geometric
  heuristics requiring researcher review and downstream optimization.
- **Canvas atom-id labels now color by mapping state**: while the Calculation
  dialog is open, an atom's id label takes the blue reactant or orange product
  tint only once that atom is actually mapped; every unmapped atom stays gray.
  Mapping progress is visible on the drawing at a glance.
- **Mapping rings removed from the canvas**: the blue/orange rings that framed
  the selected correspondence pair (drawn on row selection and while hovering
  dropdown candidates) are gone — they read as clutter over the structure.
  The mapping-state label colors above carry that information instead.
- **Mapping markers on the canvas lost their R/P letters**: while picking an
  atom correspondence, the rings around the selected reactant and product
  atoms no longer float an "R"/"P" letter beside the atom — the letters sat
  awkwardly over the drawing. Solid blue still means reactant and dashed
  orange still means product.
- **Mapping UI grays out what cannot be mapped**: in the Calculation dialog's
  atom correspondence, a reactant row with no same-element product candidate
  reads muted until the counterpart component joins the product endpoint; a
  product candidate already mapped by another row shows muted in the other
  dropdowns (picking it still just flags the duplicate); and atoms of
  components that sit out of the step entirely now get gray id labels on the
  canvas instead of no label.
- **Locked endpoints in the Calculation dialog look locked**: when including a
  component as the step's reactant (or product) disables its opposite
  endpoint, the locked inclusion and role dropdowns are now visibly muted
  (gray background, faint text) instead of only being unclickable, and both
  carry the explanation tooltip.
- Slimmed the top toolbar down to drawing controls: the Save / Open / New
  Canvas / Molecule Info / Undo / Redo buttons and the file dropdown moved into
  the new menu bar, leaving the tool well, flip/rotate, and the SMILES
  quick-insert field. All keyboard shortcuts are unchanged.
- Copying a selection (`Ctrl+C`) now also places SVG and PDF vector flavors on
  the clipboard next to the PNG, so vector-aware apps (Illustrator, Office)
  paste vectors.
- Unified one-sided Bold double bonds with the ordinary double-bond positioning
  model: right-click now offers **Inward**, **Centered**, and **Outward** without
  dropping the Bold style, and `l` / `c` / `r` preserve it as well.
- Moved the SMILES quick-insert field from the tool-options bar up to the main top
  toolbar, so it stays visible regardless of the active tool. The field stretches to
  fill the space after the drawing and transform controls (up to a
  maximum width so it does not sprawl on wide monitors) and shrinks on narrow windows
  instead of pushing buttons into the overflow menu.
- Renamed the SMILES insert button from **Render** to **Insert**, so its label matches
  what it does — placing the typed structure on the canvas.
- Redrew the **Atom** tool icon as a periodic-table glyph (previously an `A`
  letterform) to signal "choose a specific element" and to keep it visually distinct
  from the **Text** annotation tool's `T`.
- Gave the status-bar zoom **Fit** control a subtle border and hover state so it reads
  as a button rather than plain text, matching the `−` / `+` controls beside it.
- Grouped the pick-one **mode tools** (select, bond, ring, arrow, …) inside a subtle
  painted "well" on the top toolbar, so they read as one set — visually distinct from
  the loose one-shot command buttons beside them (flip and rotate).

### Fixed
- **Colouring a ring that contains a dotted double bond did nothing**: picking a
  colour on a ring — clicking its fill with the colour tool, or recolouring a
  selection that holds the ring but not that bond's own line — failed silently
  when any bond in the ring used the dotted double style. Nothing was recoloured
  and the attempt still consumed a step of undo history. A dotted double bond is
  drawn as two graphics items and recolouring the ring correctly restyles both,
  but an internal check counted the second item as an unrelated object being
  changed and aborted the whole operation. Rings recolour normally now, at any
  bond style.
- **Terminal spam when opening menus under Wayland/WSLg**: Qt's Wayland backend
  prints `This plugin supports grabbing the mouse only for popup windows` to
  the terminal every time a menu opens. The startup stderr filter — previously
  macOS-only — now also runs on Linux and drops this known-harmless line.
- **Molecule Info title hidden behind the header buttons**: unless the window
  was stretched wide, the SMILES/InChI/InChIKey/Export 3D buttons reached over
  the painted "Molecule Info" heading and covered it. The buttons are now sized
  to their labels, which leaves the full title visible at the window's default
  width, and on narrower windows the title and subtitle elide at the button row
  instead of running underneath it.
- **Atom-correspondence dropdown could not be scrolled**: when a structure has
  many same-element atoms, the product-atom dropdown in the Calculation dialog
  showed every candidate in one over-tall popup with no scrollbar, so the lower
  atoms ran off-screen and the mouse wheel had nothing to scroll. The popup is
  now capped to a visible window with a working scrollbar.
- **Crash while using the Calculation dialog with an IME**: clicking a table
  cell in **Calculation ▸ Edit States and Steps...** while an input-method
  composition (e.g. Korean) was active could crash the whole app on Wayland,
  including WSLg. Qt reacts to a composition event by starting or focusing a
  cell editor — for cells hosting the embedded combo boxes it focuses the
  combo before even consulting the edit triggers — and the Wayland text
  input re-delivers the composition event on every such focus change, so
  the two recursed until the stack overflowed. The dialog tables take no
  text input at all: direct cell editing is now disabled and both tables
  ignore composition events outright, for item and widget cells alike.
  Unsaved work from a crashed session was already restored by autosave
  recovery.
- Windows headless document rendering now uses the native Qt platform without
  showing a window, preventing labels from turning into boxes when `offscreen`
  is selected only after the process has started.
- `chemvas --help`, `chemvas -h`, and `chemvas --version` now return root CLI
  metadata without starting Qt; the help identifies desktop startup, supported
  root options, and every dispatched headless subcommand.
- Cleared transient hover indicators before Perspective rotation captures its
  scene snapshot, preventing a false scene-mutation failure at release. Failed
  press, preview, or finalization callbacks are also contained at the PyQt6
  boundary and reported in the status bar instead of aborting the app.
- A left-click that successfully retries an interrupted Perspective rotation
  commit is now consumed instead of immediately starting another rotation;
  button-free mouse movement can no longer extend a stranded drag either.
- Perspective rotation now accepts the expected selection-state republication
  that occurs when a selected ring is restored through its atom graphics, so
  releasing the left mouse button commits instead of reporting a false global
  authority change.

### Removed
- **Painted "well" behind the modal tool buttons**: the top toolbar no longer
  draws the inset tray that grouped the pick-one mode tools apart from the
  flip/rotate command buttons. The decoration read poorly in practice, so the
  toolbar is back to a flat bar; buttons, actions, and shortcuts are unchanged.
- **Single-species `pack` command**: the Calculation Bundle v1 directory export
  (`source.chemvas`, `structure.mol`, `geometry.xyz`, `atom_map.json`,
  `manifest.json`) had no remaining consumer. Machine handoff of geometries now
  happens exclusively through the elementary-step `machine.json` written by
  `pack-step`; `inspect` remains the headless structure inventory.

## [0.1.0] - 2026-07-13

### Added
- 2D drawing canvas: bonds (single/double/triple, bold, wedge, hash) with 30° angle
  snapping and a consistent default bond length.
- Ring and conformer templates (benzene, cycloalkanes, chair/boat) with live
  preview and click-to-insert.
- Arrows: reaction, equilibrium, resonance, curved, and dashed, with adjustable
  width and head scale.
- Bracket annotations (square/round/curly) plus dagger (`†`) and double dagger (`‡`)
  objects.
- Atom labels with charges, radicals, and common alias labels
  (`Me`, `Et`, `OH`, `Ph`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `i-Pr`).
- Free **Text** annotation tool (`T`), separate from the **Atom** tool (`A`): place
  captions/labels independent of the molecule graph, edited inline on the canvas.
  Its option bar offers size, bold/italic, super-/subscript, and left/center/right
  alignment, and the toolbar Text button has a font-family dropdown; text color is set
  with the existing Color tool. Rich formatting is preserved in `.chemvas` documents
  and figure exports.
- SMILES import with cursor preview and click-to-place (requires RDKit).
- Molecule Info window with interactive 3D preview and molecular formula/weight
  (requires RDKit).
- Canonical SMILES, InChI, and InChIKey computation for the current structure;
  the Molecule Info window gained **Copy SMILES** / **Copy InChIKey** buttons that
  place the value on the clipboard (requires RDKit).
- **Export MOL** (File menu): write the **selected** structure to an MDL Molfile
  (`.mol`, V2000), preserving 2D coordinates, bond orders, and wedge/hash stereo.
  Plain-element
  structures need no RDKit; abbreviation labels (`Ph`, `CF3`, `tBu`, …) are expanded
  into explicit atoms via RDKit when it is installed.
- Figure export to SVG / PDF / PNG / TIFF with outlined glyphs and deterministic
  physical sizing (bond-length or 84/174 mm column fit).
- 2D→3D `.xyz` export of the current molecule or atom/bond selection, carrying
  charges/radicals and wedge/hash stereo (requires RDKit).
- Editing: select/move, horizontal & vertical flip, perspective rotation, and
  delta-based undo/redo.
- ChemDraw-compatible keyboard shortcut subset: atom/bond hover hotkeys
  (labels, sprouts incl. gem-dimethyl `9`, dashed `d`/`Shift+D` and double-bond
  position `l`/`c`/`r` bond styles), generic tool hotkeys (`Shift+T` brackets,
  `Shift+G` orbitals, `Shift+E` chemical symbols), selection rotate/nudge via
  `Alt`/`Shift`+arrows (also moves/rotates selected arrows, notes, brackets,
  orbitals, and shapes), view keys `F5`–`F8`, and `Ctrl+X` cut.
- **Select All** (`Ctrl+A`): selects every object on the canvas (structures,
  arrows, brackets, shapes, orbitals, marks, and text notes) and switches to the
  Select tool.
- **Group / Ungroup** (`Ctrl+G` / `Ctrl+Shift+G`): ChemDraw-style object groups.
  A selected group is outlined by a single dashed bounding box, and clicking
  anywhere inside the box drags the whole group. Selecting any member (click,
  shift-click, or marquee) extends the selection to
  the whole group so grouped fragments, arrows, and annotations move and delete
  together. Grouping is undoable, absorbs overlapping groups, and group
  membership is persisted in `.chemvas` documents (file format version 3;
  older files still load).
- `.chemvas` JSON document save/load (`{"type":"chemvas","version":4,...}`;
  older version 1–3 files still load).
- ACS 1996 default style and color palette.
- **Application icon and OS identity**: a benzene-hexagon app icon in the window,
  Dock, and taskbar, plus the application name and version reported to the OS.
- **About Chemvas** dialog, reached from a **Help** menu (the native application
  menu on macOS): shows the version, MIT license, RDKit availability, and the
  Qt/Python versions in use.
- Desktop packaging: a PyInstaller spec, a macOS `.app` that registers the
  `.chemvas` document type (double-clicking a file opens it in Chemvas), and a
  Linux `.desktop` entry with an `application/x-chemvas` MIME type.

[Unreleased]: https://github.com/dhsohn/Chemvas/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/dhsohn/Chemvas/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/dhsohn/Chemvas/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/dhsohn/Chemvas/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/dhsohn/Chemvas/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/dhsohn/Chemvas/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dhsohn/Chemvas/releases/tag/v0.1.0
