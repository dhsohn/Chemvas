// Browser transport only. Chemvas's Python CanvasHistoryService owns undo/redo.
export class SessionClient {
  #info = null;
  #busy = false;
  #send;
  name = 'Canvas 1.chemvas';

  constructor(send) { this.#send = send; }
  get info() { return this.#info; }
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
      const result = await this.#send({session: this.info?.session, revision: this.info?.revision ?? 0, action, ...extra});
      this.#info = result;
    } finally { this.#busy = false; }
  }
  async load(info, name = 'Canvas 1.chemvas') {
    await this.#dispatch('load', {document: info.document});
    this.name = name;
  }
  async perform(edit) {
    if (this.readOnly) throw new Error('This drawing is read-only in the browser adapter.');
    await this.#dispatch('edit', {edit});
  }
  async undo() { if (this.canUndo) await this.#dispatch('undo'); }
  async redo() { if (this.canRedo) await this.#dispatch('redo'); }
}
