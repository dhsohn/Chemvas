// Browser transport only. Chemvas's Python CanvasHistoryService owns undo/redo.
export class SessionClient {
  #info = null;
  #busy = false;
  #send;
  #needsSync = false;

  constructor(send) { this.#send = send; }
  get info() { return this.#info; }
  get name() { return this.info?.name ?? 'Canvas 1.chemvas'; }
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
      if (this.#needsSync) {
        this.#info = await this.#send({session: this.info.session, action: 'read'});
        this.#needsSync = false;
        throw new Error('Connection restored. Check the drawing before editing again.');
      }
      try {
        this.#info = await this.#send({session: this.info?.session, revision: this.info?.revision ?? 0, action, ...extra});
      } catch (error) {
        if (error.status && error.status < 500 && error.status !== 409 && !error.uncertain) throw error;
        if (!this.info?.session) throw error;
        this.#needsSync = true;
        try {
          this.#info = await this.#send({session: this.info.session, action: 'read'});
          this.#needsSync = false;
        } catch {
          throw new Error(`${error.message} The current drawing could not be refreshed; the next action will only reconnect.`);
        }
        throw new Error(`${error.message} The current drawing has been refreshed. Check it before editing again.`);
      }
    } finally { this.#busy = false; }
  }
  async load(info, name = 'Canvas 1.chemvas') {
    await this.#dispatch('load', {document: info.document, name});
  }
  async perform(edit) {
    if (this.readOnly) throw new Error('This drawing is read-only in the browser adapter.');
    await this.#dispatch('edit', {edit});
  }
  async undo() { if (this.canUndo) await this.#dispatch('undo'); }
  async redo() { if (this.canRedo) await this.#dispatch('redo'); }
}
