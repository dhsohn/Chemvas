# ADR 0017: Explicit recovery and editor state policies

- Status: Accepted
- Date: 2026-09-25
- Related: [ADR 0002](0002-single-rollback-kernel.md), [ADR 0010](0010-document-owned-notes-and-marks.md)

## Context

The audit left four behavior choices open: how to expose recovery, whether to
retain the last SMILES input in document history, whether atom merges should
transfer marks, and how Bold drags should match clicks. These choices affect
visible behavior and cannot be decided as internal cleanup alone. The user
approved the following policies.

## Decision

1. **Explicit recovery.** Startup opens a fresh workspace. File → Recover Unsaved
   Work… offers dirty snapshots from interrupted sessions as new unsaved copies,
   without binding them to existing file paths. Live or uncertain process owners
   remain untouched. The recovery service opens documents and publishes notices;
   the store owns session files and the pure policy chooses eligible entries.
   Recovery originals can be pruned only after every offered copy has opened and
   the current session has persisted. Partial open failures remember successful
   copies for retry; autosave or cleanup failures retain pending cleanup and do
   not reopen copies. Unreadable snapshots retain their source session and show
   a warning. Recovery, autosave and Quit notices have independent lifetimes.
2. **Completed close choices are final.** A completed clean exit records Save or
   Discard decisions before deleting redundant snapshots. Failed clean-manifest
   writes retain the prior recovery data. Clean sessions are not reopened, and
   known leftover snapshots from older clean sessions are discarded only after
   their process is gone. Unknown contents and symbolic links remain untouched.
3. **Retire last-input state.** The SMILES input remains a transient insertion UI.
   The molecular graph and annotations own the resulting drawing. Remove the
   redundant last-input canvas state, history commands, rollback authority and
   edit invalidation calls. v7/v8 readers still validate and accept the old
   `last_smiles_input` key; current saves write `null` at the shared document
   boundary. Opening never mutates the source file. Removing the schema key
   would require a future format generation.
4. **Do not transfer merged marks.** Keep the established atom merge policy.
   A mark attached to a removed atom is not reassigned to the survivor and does
   not contribute charge or radical metadata to it. A retained mark serializes
   as detached; explicit group membership remains valid. Undo restores the
   original attachment and Redo restores the merged state.
5. **One Bold rule.** Click and drag over an existing bond use the same rendering
   policy. Preserve its order and double-bond alignment; non-double Bold bonds
   retain the existing inward/outward toggle. Keep the refusal to replace
   `double_either` with a display-only style. Real changes remain one undoable
   document edit, while no-op edits create no history entry.

## Validation

Exercise recovery through the File menu on a real window, including Cancel,
partial open failure, snapshot failure and retry without duplicate windows.
Verify clean-exit write failure preserves sources and successful discard removes
them. Existing process-identity, corrupt-file and multi-session tests remain.
Frozen v7/v8 fixtures verify acceptance, null-on-write and unchanged source bytes.
Real canvas tests compare Bold click/drag results and Undo/Redo, and cover merge
marks without transfer. Run the required file-isolated repository gate and the
affected real canvas/window tests with the native Cocoa backend.
