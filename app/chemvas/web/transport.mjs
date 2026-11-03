// Complete presentation without replaying an accepted edit or sending its document back.
export async function sessionDrawing(request, send, measure) {
  const result = await send(request);
  if (!result.drawing?.needs_measurements) return result;
  try {
    const rendered = await send({
      session: result.session, revision: result.revision, action: 'measure',
      font: measure(result.drawing.label_measurements),
      ...(request.action === 'preview' ? {edit: request.edit, ...(request.selection ? {selection:request.selection} : {})} : {}),
    });
    if (rendered.drawing?.needs_measurements) throw new Error('The font measurements did not complete the drawing.');
    return {...rendered, shortcut_tool: result.shortcut_tool, edit_notice: result.edit_notice, pasted: result.pasted};
  } catch (error) {
    // The initial request succeeded; resynchronize its document, never repeat it.
    error.uncertain = true;
    error.session = result.session;
    throw error;
  }
}

// Browser transport only. Chemvas's Python CanvasHistoryService owns undo/redo.
export class SessionClient {
  #info = null;
  #busy = false;
  #send;
  #syncSession = null;

  constructor(send) { this.#send = send; }
  get info() { return this.#info; }
  get name() { return this.info?.name ?? 'Canvas 1.cdxml'; }
  get document() { return this.info?.document ?? null; }
  get busy() { return this.#busy; }
  get readOnly() { return Boolean(this.info?.unsupported.length); }
  get canUndo() { return !this.#busy && Boolean(this.info?.can_undo); }
  get canRedo() { return !this.#busy && Boolean(this.info?.can_redo); }
  get dirty() { return Boolean(this.info?.dirty); }

  async #dispatch(action, extra = {}) {
    if (this.#busy) throw new Error('Wait for the current edit to finish.');
    this.#busy = true;
    try {
      if (this.#syncSession) {
        this.#info = await this.#send({session: this.#syncSession, action: 'read'});
        this.#syncSession = null;
        throw new Error('Connection restored. Check the drawing before editing again.');
      }
      try {
        this.#info = await this.#send({session: this.info?.session, revision: this.info?.revision ?? 0, action, ...extra});
      } catch (error) {
        if (error.status && error.status < 500 && error.status !== 409 && !error.uncertain) throw error;
        const session = this.info?.session ?? error.session;
        if (!session) throw error;
        this.#syncSession = session;
        try {
          this.#info = await this.#send({session, action: 'read'});
          this.#syncSession = null;
        } catch {
          throw new Error(`${error.message} The current drawing could not be refreshed; the next action will only reconnect.`);
        }
        throw new Error(`${error.message} The current drawing has been refreshed. Check it before editing again.`);
      }
    } finally { this.#busy = false; }
  }
  async load(info, name = 'Canvas 1.cdxml') {
    await this.#dispatch('load', {document: info.document, name});
  }
  async perform(edit) {
    if (this.readOnly) throw new Error('This drawing is read-only in the browser adapter.');
    await this.#dispatch('edit', {edit});
  }
  // File > Recover Unsaved Work: this window takes over a draft. With takeover,
  // the server closes another window that still holds it, only once this
  // request and the draft are valid and that window's draft is up to date.
  async recover(draft, takeover = false) {
    await this.#dispatch('recover_draft', {draft, ...(takeover ? {takeover: true} : {})});
  }
  async undo() { if (this.canUndo) await this.#dispatch('undo'); }
  async redo() { if (this.canRedo) await this.#dispatch('redo'); }
}

// After startup, say truthfully whether earlier work waits for recovery; the
// drawing in this window is never replaced without the user's choice. A page
// that reloaded closes the session it left behind first.
export async function offerRecovery({storage, closedSessionKey, session, api, notice, noticeShown}) {
  const previous = storage.getItem(closedSessionKey);
  storage.removeItem(closedSessionKey);
  if (previous && previous !== session()) await api('session', {session: previous, action: 'close'}).catch(() => {});
  if (!session()) return;
  let listing;
  try { listing = await api('session', {session: session(), action: 'drafts'}); }
  catch (error) { notice(error.message, true); return; }
  if (!listing.available) { if (listing.message) notice(listing.message, true); return; }
  // Drafts held by windows still open are theirs, not earlier work.
  const ready = listing.drafts.filter(entry => !entry.problem && !entry.open).length;
  if (ready && !noticeShown()) notice(`Unsaved work from ${ready === 1 ? 'an earlier window' : `${ready} earlier windows`} can be recovered. Choose File > Recover Unsaved Work… to restore or discard it.`);
}
