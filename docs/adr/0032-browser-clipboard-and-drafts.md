# ADR 0032: Browser chemical clipboard and recovery drafts

- Status: Accepted
- Date: 2026-10-03
- Extends: [ADR 0005](0005-responsibility-based-editor-boundaries.md), [ADR 0029](0029-browser-adapter.md)

## Problem

The browser presentation adapter previously had no automatic draft or recovery
mechanism and lacked chemical clipboard operations:

1. **Recovery across loopback restarts**: Chemvas binds its local web server to
   an ephemeral loopback port. Origin-bound browser storage (`localStorage`,
   `IndexedDB`) can persist through server restart, but a different port makes
   it inaccessible to the new origin. Storing drafts in browser-origin storage
   would isolate unsaved work whenever the server is relaunched on a new port.
2. **Clipboard consistency without parallel schemas**: Chemical Copy, Cut and
   Paste require atom ID remapping, cascade offsets, group preservation, image
   budget enforcement, and perspective coordinate reprojection. Implementing
   a browser-specific serialization or mutation path would violate ADR 0005, which
   mandates a single mutation owner and prohibits parallel editing logic. In
   addition, browser API capabilities vary, and this adapter uses an
   asynchronous plain-text clipboard transport subject to browser permissions
   and user gestures; native Qt custom MIME is
   `application/x-chemvas-selection+json`, with no direct implemented
   cross-adapter OS clipboard exchange.

## Decision

### Canonical chemistry clipboard over existing services (extending ADR 0005)

The browser adapter reuses the desktop's v3 selection payload format
(`chemvas-selection`) and canonical services without introducing a parallel
chemistry schema:

- **Payload generation and validation**: For supported selections, Copy and Cut
  invoke `build_selection_clipboard_payload` and validate selections through
  `decode_clipboard_selection_payload`. The payload encompasses atoms, bonds,
  complete rings, attached and isolated marks, arrows, decorative shapes, orbitals,
  text notes, groups, embedded images (respecting collection budgets), and
  perspective 3D points; the existing validator may refuse unsupported, corrupt,
  or oversized payloads atomically. Cut deletes the selection as a single edit
  only after a valid payload is confirmed and the source document revision matches.
- **Paste execution**: Incoming JSON text is decoded by
  `decode_clipboard_selection_payload`, planned with
  `build_clipboard_paste_plan`, and applied via `apply_paste_payload`. Atom IDs
  remap past the target document's `next_atom_id`, repeated pastes cascade with
  bond-length offsets, groups keep remapped membership, and only perspective
  depth points reproject through the target camera. A paste executes as
  exactly one Undo/Redo command.
- **Transport and fallback**: When permitted by the browser, selections travel as
  plain text (`text/plain`) on the system clipboard. If the browser denies or
  lacks clipboard permission, a validated copy is retained in window-local memory
  with an explicit notification; this fallback copy is discarded on page reload.
- **MIME boundary**: Because native Qt uses `application/x-chemvas-selection+json`
  and the web adapter uses system text, direct OS clipboard exchange between Qt
  and web windows is not implemented despite format compatibility.
- **Text note editing**: Active text note editing retains native text shortcut
  semantics. Opening the Edit menu concludes note editing and routes clipboard
  commands to the canvas.

### Durable recovery drafts with single-server ownership (extending ADR 0029)

To ensure drafts survive port changes on server restart without introducing Qt
dependencies, draft persistence is owned by `bootstrap/web_drafts.py`:

- **Single-server folder lock**: Drafts reside in a per-user application
  directory (or a CLI-specified `--drafts-dir`). A single running server process
  owns the drafts folder by holding an OS lock on `owner.lock` (`msvcrt.locking`
  on Windows, `fcntl.flock` on POSIX). A second server launched concurrently runs
  with automatic recovery disabled and reports this status to the user.
- **Envelope format**: After each accepted edit, the complete `.chemvas` drawing
  is written atomically inside a versioned JSON envelope containing `format`
  (`chemvas-browser-draft`), `version` (`1`), `name`, `saved_at`, and the
  `document` payload. Drafts store no launch tokens, origins, or session
  identifiers. Files are stored unencrypted and are capped at a 96 MiB document
  budget plus a 64 KiB envelope.
- **Stable draft identifier**: Each unsaved document is assigned a stable random
  draft file ID. Upon recovery via File > Recover Unsaved Work, the recovering
  window adopts the existing draft file ID without creating duplicate files.
  Recovered drawings remain unsaved; downloading a copy via File > Save does not
  guarantee a disk write and never clears dirty state or removes a draft. A draft
  is removed only when its document is discarded, replaced after discard
  confirmation, or undone to a clean baseline. Closing a window or stopping the
  server keeps drafts on disk.
- **Window takeover**: Recovering a draft currently open in another window
  requires explicit confirmation, which claims the draft and terminates the other
  window's session. Takeover is refused if the holder is busy beyond the
  bounded wait (5 seconds) or if its latest accepted changes failed to reach
  the recovery draft; the other window remains open so the user can switch to it
  and save a copy or resolve draft-write failure. A crashed tab whose server
  remains running can still be listed as open until the user explicitly takes
  over its draft or restarts the server, as idle session cleanup occurs only when
  the session cap is reached.
- **Capacity and write failures**: Up to 16 drafts are retained without
  age-based expiration. A failed atomic write preserves the previous valid draft
  file on disk and reports an error, meaning in-memory edits from a failed write
  are not yet recoverable. Damaged or incompatible draft files are retained for
  explicit user discard. Filesystem and folder access failures are reported
  directly.

## Verification and limits

- **Automated tests**: `tests/test_web_clipboard.py` verifies selection payload
  construction, round-trip decoding, atom ID remapping, cascade offsets, group and
  mark preservation, and single-step Undo/Redo. `tests/test_web_drafts.py`
  validates process folder locking, multi-server lockout, restart persistence,
  takeover semantics, clean-baseline deletion, and corrupt-envelope handling.
  `tests/web_adapter.test.mjs` verifies client-side clipboard fallbacks, paste text
  handling, and SessionClient recovery operations.
- **Test scope distinction**: Python tests create actual server objects and HTTP
  requests to verify persistence and session contracts, rather than simulating
  physical crashes or browser reloads. Client test cases verify client actions and
  recovery workflows without rendering full browser dialogs or testing native OS
  permission prompts.
- **Lifecycle limits**: Recovery durability requires an accepted edit and a
  successful draft write. On a failed write, the previous valid draft file
  remains on disk, and latest in-memory edits may not be recoverable.
  Uncommitted text in an open note and edits in flight that have not been accepted
  by the server at page unload may be lost; the browser leave-page warning
  (`beforeunload`) remains active.
- **Platform limits**: Direct physical OS clipboard exchange between Qt and web
  is not supported. Clipboard permission behavior varies by browser. Full UI
  parity and Qt retirement are not claimed.
