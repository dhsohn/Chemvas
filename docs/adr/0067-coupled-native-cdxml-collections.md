# ADR 0067: Coupled native CDXML collections

- Status: Accepted
- Date: 2026-11-02

## Problem

Saved `cdxml_source` ([ADR 0058](0058-desktop-cdxml-documents.md)) binds native
CDXML object IDs to saved annotations through parallel per-collection lists
(`items` and `baseline_items`), while `groups` references collection items by
zero-based index. `domain/document/cdxml_source.py` validated those invariants on
read and save, but callers mutated the coupled structures directly:
`features/document_patch/service.py` ([ADR 0056](0056-snapshot-bound-note-patches.md))
appended to `notes` and separately populated `items["notes"]`,
`features/cdxml_editable_arrows.py`
([ADR 0060](0060-editable-native-arrows-and-local-platform-gates.md)) rewrote
`images`, `arrows`, binding lists and `groups` in place across live state and
`baseline`, and `ui/canvas/canvas_cdxml_source.py` paired bindings with runtime
collection order directly. Updating one side without staging the coupled arrays
risked length mismatches, misinterpreting omitted collection bindings (which mean
every item in that collection is unbound), or leaving partial live mutations when
baseline promotion failed.

## Decision

Make Qt-free `domain/document/cdxml_source.py` the owner of coupled
annotation-array, parallel native-ID, and positional group-reference mutations
for note appends and native image-to-arrow promotion:

- Define `CdxmlSource` (`TypedDict`) for the existing seven persisted provenance
  fields (`xml`, `offset`, `atoms`, `bonds`, `items`, `baseline`,
  `baseline_items`) and `ImageArrowPromotion` (`TypedDict`) pairing distinct
  `live` and `baseline` arrow records per promoted native image ID.
- Resolve parallel collection bindings through `native_ids_for_collection`. An
  omitted per-collection entry continues to mean every item in that collection is
  unbound; present lists must match the collection length without duplicate
  native IDs.
- Own note appends in `append_unbound_note(state, note)`. When `cdxml_source` is
  present, stage and validate `items["notes"]`—extending existing bindings with
  `None` or materializing `[None] * (index + 1)` when `notes` was omitted—before
  appending to `notes` and publishing the updated bindings. Leave `baseline`,
  `baseline_items`, `xml` and `groups` unchanged.
- Own snapshot stroke promotion in
  `promote_linked_images_to_arrows(state, promotions)`. Stage retained `images`,
  extended `arrows`, parallel native-ID lists, and remapped positional `groups`
  for both the live document and `baseline` before mutating either projection, so
  any preparation or validation failure leaves the input state unchanged.
  Retained images keep their relative order, and promoted arrows append after
  existing arrows in each projection's own image order.

`features/document_patch/service.py` retains SHA-256-bound snapshot validation,
`next_note_index` checks and `_compose_note`, delegating `add_note` appends to
`append_unbound_note` without serializing permanent runtime IDs.
`features/cdxml_editable_arrows.py` retains native stroke representability,
raster/opacity eligibility against `baseline` and scaled endpoint math, preparing
distinct current and baseline arrow records before calling
`promote_linked_images_to_arrows`. `ui/canvas/canvas_cdxml_source.py` retains the
boundary between transient runtime `AnnotationCollection` record IDs
(`cdxml_item_bindings`) and persisted positional arrays, staging restored
bindings and validating normalized initial baselines through
`native_ids_for_collection`.

Persisted CDXML and JSON schemas, `xml`, `offset`, `atoms` and `bonds` bindings,
and unsupported native XML preservation are unchanged. The operations stay
specialized to note appends and image-to-arrow promotion rather than introducing
generic linked-item wrappers or a general collection-migration framework.

## Verification and limits

`tests/test_cdxml_source_linked_mutations.py` covers unbound note appends with
absent, omitted and explicit bindings, length-mismatch rejection without partial
mutation, unchanged `baseline` and `groups`, `apply_document_patch` `add_note`
delegation, mixed image-to-arrow promotion with retained images and group
remapping, independent live and baseline image orders, raster/opacity and
unsupported-stroke non-promotion, idempotent repeat promotion, and unchanged
state when second-projection staging fails. Existing regression suites in
`tests/test_document_patch_notes.py`,
`tests/test_document_patch_external_cdxml.py`,
`tests/test_cdxml_editable_arrows.py` and `tests/test_cdxml_preservation.py`
cover snapshot-bound note patches, external CDXML edits, editable native strokes
and untouched native XML subtrees. `tests/test_document_patch_note_workflow.py`
exercises patched notes in the native editor serially via `scripts/check.sh`.

Full local `make check` and host-native workflow execution remain separate
integration gates. Only note appends and snapshot image-to-arrow promotion are
centralized here; other annotation kinds, atom/bond source maps and native XML
serialization retain their existing owners and limits, and no persistent
annotation IDs are introduced.
