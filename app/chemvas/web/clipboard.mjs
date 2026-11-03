// Chemistry clipboard of the browser adapter. A copy is the desktop's
// chemvas-selection payload, built and validated by the server. It travels as
// system clipboard text where the browser allows that, and this window keeps
// it too, so a refused or unavailable system clipboard still leaves a usable
// copy here. Pastes go back to the server, which validates them again.

export const SELECTION_FORMAT = 'chemvas-selection';

// Whether clipboard text claims to be a Chemvas selection. Only recognition:
// the server still validates every paste in full.
export function isSelectionText(text) {
  if (typeof text !== 'string' || !text.trimStart().startsWith('{')) return false;
  try {
    const value = JSON.parse(text);
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value) && value.format === SELECTION_FORMAT;
  } catch { return false; }
}

// The text a paste uses. A selection on the system clipboard wins. This
// window's own copy is used when the system clipboard could not be read
// (systemText null) or never received that copy; otherwise the system
// clipboard holds something newer that is not chemistry, and nothing pastes.
export function pasteText(systemText, local) {
  if (isSelectionText(systemText)) return systemText;
  if (local && (systemText === null || !local.system)) return local.text;
  return null;
}

// `payload` is the server's copy reply, requested inside the user gesture.
// The system write starts before any await, as browsers require, with the
// reply as a pending clipboard item; without ClipboardItem it falls back to
// writeText once the reply arrives. A refused reply rejects: nothing copied.
export async function writeSelection(payload, {clipboard, ClipboardItem}) {
  let system = null;
  if (clipboard?.write && ClipboardItem) {
    const blob = payload.then(text => new Blob([text], {type: 'text/plain'}));
    // A refused reply is reported below; the pending item must not also be.
    blob.catch(() => {});
    try {
      system = clipboard.write([new ClipboardItem({'text/plain': blob})]).then(() => true, () => false);
    } catch { system = null; }
  }
  const text = await payload;
  if (system === null) system = clipboard?.writeText ? clipboard.writeText(text).then(() => true, () => false) : Promise.resolve(false);
  return {text, system: await system};
}

export class ChemistryClipboard {
  #local = null;
  #env;
  constructor(env) { this.#env = env; }
  get local() { return this.#local; }
  // A failed copy keeps the previous one, as a refused desktop copy does.
  async copy(payload) {
    const copied = await writeSelection(payload, this.#env);
    this.#local = copied;
    return copied;
  }
  // The system clipboard text, or null when the browser does not allow reading it.
  async read() {
    try { return await this.#env.clipboard.readText(); } catch { return null; }
  }
  textFor(systemText) { return pasteText(systemText, this.#local); }
}

// Edit > Copy and Cut. Cut removes the selection only after a usable copy
// exists, and only while the drawing it was copied from is still current; a
// newer or replaced drawing keeps everything.
export async function copySelection({store, payload, cut = false, isCurrent, remove}) {
  const copied = await store.copy(payload);
  if (!cut) return {copied, removed: false, stale: false};
  if (!isCurrent()) return {copied, removed: false, stale: true};
  return {copied, removed: Boolean(await remove()), stale: false};
}

// The page's Edit > Copy, Cut and Paste of the canvas selection. The page passes
// its live state as functions, so each check reads it at that moment.
export function clipboardActions({editor, isLoading, activeGesture, selection, setSelection, selectedItems, api, edit, notice, render, cancelGesture, store, maxBytes}) {
  // The server's copy reply is requested inside the user gesture, so the system
  // clipboard write starts before it arrives; Cut then deletes through the
  // usual one-step edit.
  async function copyChemistry(cut) {
    if (!editor.document || editor.busy || isLoading() || activeGesture() || !selection().size || (cut && editor.readOnly)) return;
    const items = selectedItems(), {session, revision} = editor.info;
    const payload = api('session', {session, revision, action: 'copy', selection: items}).then(reply => reply.payload);
    const isCurrent = () => !editor.busy && !isLoading() && editor.info?.session === session && editor.info?.revision === revision;
    let outcome;
    try {
      outcome = await copySelection({store, payload, cut, isCurrent, remove: () => edit({kind: 'delete_selection', selection: items})});
    } catch (error) { notice(error.message, true); return; }
    if (outcome.removed) { selection().clear(); render(); }
    if (outcome.stale) notice('The drawing changed before Cut finished. The selection was copied but not removed.', true);
    else if ((!cut || outcome.removed) && !outcome.copied.system) notice('Copied for pasting in this browser window only: the browser did not allow access to the system clipboard.');
  }
  // A Chemvas selection from the system clipboard, else this window's own copy
  // (see pasteText). The server validates, offsets and remaps it in one
  // Undo/Redo step, and the pasted items become the selection.
  async function pasteChemistry(systemText) {
    if (!editor.document || editor.busy || isLoading()) return;
    if (editor.readOnly) { notice('This drawing is read-only in the browser adapter.', true); return; }
    const text = store.textFor(systemText);
    if (text === null) {
      notice(systemText === null ? 'The browser did not allow reading the clipboard. Press ⌘/Ctrl+V on the canvas to paste.' : 'The clipboard does not contain a Chemvas selection.', true);
      return;
    }
    if (new Blob([text]).size > maxBytes()) { notice('The Chemvas clipboard selection is too large to paste.', true); return; }
    cancelGesture();
    if (await edit({kind: 'paste', payload: text})) {
      setSelection(new Set((editor.info.pasted ?? []).map(item => `${item.target}:${item.id}`)));
      render();
    }
  }
  // Edit > Paste reads the system clipboard first, which can wait on the
  // browser's permission prompt; it pastes only into the drawing it was chosen
  // for, never into one loaded, recovered or edited meanwhile.
  async function pasteFromMenu() {
    if (!editor.document || editor.busy || isLoading()) return;
    const {session, revision} = editor.info;
    const systemText = await store.read();
    if (editor.info?.session !== session || editor.info?.revision !== revision) {
      notice('The drawing changed while the clipboard was being read. Nothing was pasted.', true);
      return;
    }
    await pasteChemistry(systemText);
  }
  return {copyChemistry, pasteChemistry, pasteFromMenu};
}
