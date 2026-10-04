import {SessionClient, sessionDrawing} from './transport.mjs';
import {ChemistryClipboard, copySelection, isSelectionText} from './clipboard.mjs';
import {sceneMarkup, AtomLabelCache, clampView, itemKey, zoomView, wheelView, pointInSheet, marqueeSelection, measureDocumentLineHeight, measureNoteFont, layoutNoteText, styleNoteText, serializeNoteEditor, noteBlocks, noteBlocksHtml, noteTextOffset, noteTextPosition, formatNoteBlocks, noteFormatState, selectionFrameMarkup, gridMarkup, groupUnit, expandToGroups, groupBoxesMarkup, smilesPreviewMarkup, valenceWarningMarkup} from './scene.mjs';

const $ = id => document.getElementById(id);
const editor = new SessionClient(request => sessionRequest(request));
const chemistryClipboard = new ChemistryClipboard({clipboard: navigator.clipboard, ClipboardItem: globalThis.ClipboardItem});
// A reloading page closes its session as it leaves; the next page makes sure.
const closedSessionKey = 'chemvas-closed-session';
const canvas = $('canvas');
const labelCache = new AtomLabelCache();
const fontContext = document.createElement('canvas').getContext('2d');
const fontProbe = document.createElement('span');
fontProbe.style.cssText = 'position:fixed;visibility:hidden;white-space:pre;pointer-events:none';
document.body.append(fontProbe);
function measureLineHeight(font, text) {
  fontProbe.style.font = font;
  fontProbe.textContent = text;
  return fontProbe.getBoundingClientRect().height;
}
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get('token') ?? sessionStorage.getItem('chemvas-browser-token') ?? '';
if (fragment.has('token')) {
  sessionStorage.setItem('chemvas-browser-token', token);
  history.replaceState(null, '', location.pathname);
}
let tool = 'bond', orbitalKind = null, markKind = null, bracketKind = null, ringTemplate = null, selection = new Set(), gesture = null, preview = null, loading = false;
let view = {x: -25, y: -25, width: 645, height: 892};
const gridMode = () => grid.enabled ? grid.style : 'none';
const viewScale = () => Math.min(canvas.clientWidth / view.width, canvas.clientHeight / view.height);
let ui = null, bondStyle = null, arrowStyle = null, lineStyle = null, shapeStyle = null, shapeStroke = null, paintColor = null, ringFillColor = '#000000', contextPage = null, pointerPosition = null;
let grid = null;
let valenceChecking = true;
const markHover = {request:null, result:null, pending:false};
let chargeEdits = null;
let smilesInsert = null, smilesPreviewPending = null, smilesGeneration = 0;
let previewInfo = null, previewSerial = 0, previewPending = null, handleTarget = null;
let outlineRequest = null, outlinePending = false, outlineResult = {key:null,components:[],frame:null,groups:[]};
const supportedTools = new Set(['select', 'bond', 'benzene', 'delete', 'text', 'note', 'arrow', 'line', 'shape', 'color', 'ring_fill', 'mark', 'orbital', 'ts_bracket']);

// Embedded image pixels, fetched once per content reference as Blob URLs.
const imageUrls = new Map();
function imageUrl(ref) {
  const known = imageUrls.get(ref);
  if (typeof known === 'string') return known;
  if (!known && editor.info?.session) {
    const request = fetch(`/api/image?session=${encodeURIComponent(editor.info.session)}&ref=${encodeURIComponent(ref)}`, {headers: {'Authorization': `Bearer ${token}`}})
      .then(response => response.ok ? response.blob() : Promise.reject(new Error('The image could not be loaded.')))
      .then(blob => { imageUrls.set(ref, URL.createObjectURL(blob)); render(); })
      .catch(() => imageUrls.delete(ref));
    imageUrls.set(ref, request);
  }
  return null;
}

async function api(path, body) {
  const response = await fetch(`/api/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'},
    body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) throw Object.assign(new Error(value.error ?? 'The request failed.'), {status: response.status});
  return value;
}

const arrowProbe = document.createElement('div');
arrowProbe.className = 'arrow-label rich-probe';
const noteProbe = document.createElement('div');
noteProbe.className = 'note-text rich-probe';
document.body.append(arrowProbe, noteProbe);
const noteFonts = new Map();
// The Text tool's in-place editor: the note's own rich text, over the canvas.
const noteEditorElement = document.createElement('div');
noteEditorElement.className = 'note-editor';
noteEditorElement.contentEditable = 'true';
noteEditorElement.spellcheck = false;
noteEditorElement.hidden = true;
document.body.append(noteEditorElement);
let noteEditor = null, noteCommit = Promise.resolve();
function noteFont(font) {
  const key = JSON.stringify(font);
  if (!noteFonts.has(key)) noteFonts.set(key, measureNoteFont(fontProbe, fontContext, font));
  return noteFonts.get(key);
}
function styleArrowLabel(element, spec) {
  element.style.fontFamily = spec.family;
  element.style.fontSize = `${spec.pixels}px`;
  element.style.fontWeight = spec.weight;
  element.style.fontStyle = spec.italic ? 'italic' : 'normal';
  element.style.color = spec.color;
  fontContext.font = `${spec.italic ? 'italic ' : ''}${spec.weight} ${spec.pixels}px ${JSON.stringify(spec.family)}`;
  element.style.lineHeight = `${measureDocumentLineHeight(fontProbe, fontContext.font, 'H')}px`;
  const measured = fontContext.measureText('H');
  const height = measured.fontBoundingBoxAscent + measured.fontBoundingBoxDescent;
  element.querySelectorAll('sub, sup').forEach(run => {
    run.style.fontSize = `${spec.script_pixels}px`;
    run.style.top = `${run.tagName.toLowerCase() === 'sub' ? height / 6 : -height / 2}px`;
  });
}
function measureLabels(spec) {
  const font = labelCache.measure(spec, fontContext, (font, text) => measureDocumentLineHeight(fontProbe, font, text));
  font.label_boxes = {};
  for (const label of spec.arrow_labels ?? []) {
    if (font.label_boxes[label.key]) continue;
    if (label.pixels > 4096) throw new Error('Arrow label font is too large to display in the browser.');
    arrowProbe.innerHTML = label.html;
    styleArrowLabel(arrowProbe, label);
    const box = arrowProbe.getBoundingClientRect();
    font.label_boxes[label.key] = [box.width, box.height];
  }
  arrowProbe.replaceChildren();
  for (const note of spec.notes ?? []) {
    if (font.label_boxes[note.key]) continue;
    if (note.pixels > 4096) throw new Error('Note font is too large to display in the browser.');
    noteProbe.innerHTML = note.html;
    layoutNoteText(noteProbe, note, noteFont);
    const box = noteProbe.getBoundingClientRect();
    font.label_boxes[note.key] = [box.width, box.height];
  }
  noteProbe.replaceChildren();
  return font;
}
function sessionRequest(request) {
  return sessionDrawing(request, value => api('session', value),
    measureLabels);
}

// Each notice replaces the last; an owner may clear only a notice still its own.
let noticeSerial = 0, recoveryProblem = null;
function notice(text = '', error = false) {
  noticeSerial++;
  $('notice').textContent = text;
  $('notice').hidden = !text;
  $('notice').classList.toggle('error', error);
}

function render() {
  const busy = editor.busy || loading;
  if (smilesInsert && !currentSmilesInsert(smilesInsert)) smilesInsert = null;
  document.querySelectorAll('[data-idle]').forEach(item => { item.disabled = busy; });
  document.querySelectorAll('[data-editable]').forEach(item => { item.disabled = busy || editor.readOnly; });
  document.querySelectorAll('[data-tool]').forEach(item => {
    if (item.dataset.tool === 'ring_fill') item.removeAttribute('aria-pressed');
    else item.setAttribute('aria-pressed', String(item.dataset.tool === tool));
    item.disabled = !supportedTools.has(item.dataset.tool) || busy || (editor.readOnly && item.dataset.tool !== 'select');
  });
  $('undo').disabled = busy || !editor.canUndo;
  $('redo').disabled = busy || !editor.canRedo;
  $('delete').disabled = busy || editor.readOnly || !selection.size;
  // The Edit menu's clipboard acts on the canvas; opening it ends note editing.
  $('copy').disabled = busy || !selection.size;
  $('cut').disabled = busy || editor.readOnly || !selection.size;
  $('paste').disabled = busy || editor.readOnly || !editor.document;
  const recovery = editor.info?.recovery;
  $('recover').disabled = busy || !recovery?.available;
  $('recovery-status').textContent = {saved: 'Recovery draft saved', failed: 'Recovery draft not saved', off: recovery?.message ? 'Recovery off' : ''}[recovery?.state] ?? '';
  $('recovery-status').title = recovery?.message ?? '';
  // A draft that could not be written is reported once; the footer keeps it.
  if (recovery?.state === 'failed' && recovery.message !== recoveryProblem) notice(recovery.message, true);
  recoveryProblem = recovery?.state === 'failed' ? recovery.message : null;
  if (!editor.document) return;
  // A preview of another session or revision never mixes with the accepted drawing.
  if (previewInfo && (previewInfo.session !== editor.info.session || previewInfo.revision !== editor.info.revision)) previewInfo = null;
  view = clampView(view, {width:canvas.clientWidth, height:canvas.clientHeight}, editor.info.drawing.scene_rect);
  // The new view is in place before any layer reads the screen transform.
  canvas.setAttribute('viewBox', `${view.x} ${view.y} ${view.width} ${view.height}`);
  const state = editor.document.state;
  // The desktop tab marks unsaved changes and keeps the file name as opened.
  document.title = `${editor.dirty ? `${ui.title.unsaved_marker} ` : ''}${editor.name} — ${ui.title.suffix}`;
  $('canvas-status').textContent = `Canvas: ${editor.name}`;
  $('selection').textContent = `Selection: ${selection.size}`;
  $('tool-status').textContent = `Tool: ${ui.tool_names[tool] ?? tool}`;
  const page = contextPage ?? ui.context_pages[tool] ?? 'empty';
  document.querySelectorAll('[data-context]').forEach(item => { item.hidden = item.dataset.context !== page; });
  document.querySelectorAll('[data-bond]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.bond === bondStyle)));
  document.querySelectorAll('[data-template]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.template === `${ringTemplate.size}:${ringTemplate.style}`)));
  document.querySelectorAll('[data-arrow]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.arrow === arrowStyle)));
  document.querySelectorAll('[data-line]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.line === lineStyle)));
  document.querySelectorAll('[data-bracket-kind]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.bracketKind === bracketKind)));
  document.querySelectorAll('[data-orbital-kind]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.orbitalKind === orbitalKind)));
  document.querySelectorAll('[data-orbital-phase]').forEach(item => item.setAttribute('aria-pressed', String((item.dataset.orbitalPhase === 'true') === state.settings.orbital_phase_enabled)));
  document.querySelectorAll('[data-mark-kind]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.markKind === markKind)));
  document.querySelectorAll('[data-shape]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.shape === shapeStyle)));
  document.querySelectorAll('[data-color]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.color === paintColor)));
  document.querySelectorAll('[data-stroke]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.stroke === shapeStroke)));
  // A loaded setting beyond a slider's default range widens it instead of being
  // clamped, and the range returns to its defaults for ordinary values.
  document.querySelectorAll('[data-setting]').forEach(item => {
    const current = state.settings[item.dataset.setting], value = Math.round(current * Number(item.dataset.factor));
    item.min = Math.min(Number(item.dataset.minimum), value); item.max = Math.max(Number(item.dataset.maximum), value);
    item.value = value; item.title = String(current);
  });
  $('bond-length').value = state.settings.bond_length_px;
  const mode = gridMode();
  $('grid-mode').textContent = `Grid: ${mode[0].toUpperCase()+mode.slice(1)}`;
  $('grid-toggle').setAttribute('aria-pressed',String(grid.enabled));
  $('valence-toggle').setAttribute('aria-pressed',String(valenceChecking));
  document.querySelectorAll('[data-grid]').forEach(item => item.setAttribute('aria-checked',String(item.dataset.grid === mode)));
  document.querySelectorAll('[data-grid-strength]').forEach(item => item.setAttribute('aria-checked',String(Number(item.dataset.gridStrength) === Math.round(grid.opacity*100))));
  $('grid').innerHTML = gridMarkup(editor.info.sheet,grid,ui.grid,state.settings.bond_length_px,viewScale());
  if (tool !== 'select' || !selection.has(handleTarget)) handleTarget = null;
  outlineRequest = selection.size && !previewInfo ? {session:editor.info.session, revision:editor.info.revision, action:'selection', selection:selectedItems()} : null;
  const outlineKey = JSON.stringify(outlineRequest);
  $('drawing').innerHTML = sceneMarkup(previewInfo?.document ?? editor.document, {selection, components: previewInfo?.selection_components ?? (outlineResult.key === outlineKey ? outlineResult.components : []), preview: scenePreview(), drawing: previewInfo?.drawing ?? editor.info.drawing, handleTarget, handleStyle: ui.handles, snapMarks: previewInfo?.snap_marks, snapMarkStyle: ui.snap_mark, showMarkOwners: tool === 'select', markPreview: tool === 'mark' && !busy && markHover.result?.revision === editor.info.revision ? markHover.result : null, markHoverStyle: ui.mark_hover, scale: viewScale(), imageUrl});
  $('valence-feedback').innerHTML = valenceFeedback();
  for (const label of (previewInfo?.drawing ?? editor.info.drawing).arrow_labels ?? []) {
    const element = document.querySelector(`[data-arrow-label="${label.id}:${label.side}"]`);
    if (element) styleArrowLabel(element, label);
  }
  for (const note of (previewInfo?.drawing ?? editor.info.drawing).notes ?? []) {
    const element = document.querySelector(`[data-note-text="${note.id}"]`);
    if (!element) continue;
    layoutNoteText(element, note, noteFont);
    // The open editor replaces the note it edits.
    if (noteEditor?.id === note.id) element.closest('[data-item]').setAttribute('visibility', 'hidden');
  }
  positionNoteEditor();
  refreshTextFormatState();
  const insertPreview = templateHover.result;
  $('insert-preview').innerHTML = insertPreview && tool === 'benzene' ? (() => {
    const [r, g, b, a] = insertPreview.color, color = `rgba(${r},${g},${b},${a / 255})`;
    return `<g opacity="${insertPreview.opacity}" stroke="${color}" stroke-width="${insertPreview.width}" stroke-linecap="round" fill="${color}">${insertPreview.segments.map(([x1, y1, x2, y2]) => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`).join('')}${insertPreview.dots.map(([x, y, w, h]) => `<ellipse cx="${x + w / 2}" cy="${y + h / 2}" rx="${w / 2}" ry="${h / 2}" stroke="none"/>`).join('')}</g>`;
  })() : '';
  $('smiles-preview').innerHTML = smilesInsert?.info ? smilesPreviewMarkup(smilesInsert.info, editor.document, ui.smiles.preview_opacity) : '';
  const frame = selectionFrameMarkup(previewInfo?.selection_frame ?? (outlineResult.key === outlineKey ? outlineResult.frame : null), previewInfo?.drawing ?? editor.info.drawing, ui.handles, viewScale());
  const groupBoxes = previewInfo?.selection_groups ?? (outlineResult.key === outlineKey ? outlineResult.groups : []);
  $('selection-frame').innerHTML = frame.outline + groupBoxesMarkup(groupBoxes, previewInfo?.drawing ?? editor.info.drawing);
  $('rotation-handle').innerHTML = editor.readOnly ? '' : frame.handle;
  canvas.dataset.tool = tool;
  const [sheetWidth, sheetHeight] = editor.info.sheet;
  for (const [name, value] of Object.entries({x: -sheetWidth / 2, y: -sheetHeight / 2, width: sheetWidth, height: sheetHeight})) $('paper').setAttribute(name, value);
  $('zoom-level').textContent = `${Math.round((canvas.getScreenCTM()?.a ?? 1) * 100)}%`;
  $('status').textContent = busy ? 'Applying edit…' : smilesInsert ? 'SMILES: click to place, Esc to cancel' : editor.readOnly ? 'Read-only · incomplete preview' : (contextPage === 'ring_fill' ? ui.ring_fill_hint : tool === 'color' && paintColor !== null ? ui.color_hint.replace('{color}', paintColor) : ui.hints[tool] ?? `${ui.tool_names[tool] ?? tool}: ready`);
  if (!busy) void refreshSelectionOutline();
}

// Fit to Window: the desktop's margin of the limiting axis, clamped zoom, sheet centred.
function fitPage() {
  if (!editor.info) return;
  const [width, height] = editor.info.sheet, viewport = {width: canvas.clientWidth, height: canvas.clientHeight};
  if (width <= 0 || height <= 0 || viewport.width <= 0 || viewport.height <= 0) return;
  const {min, max, fit_margin: margin} = ui.navigation;
  const zoom = Math.max(min, Math.min(max, Math.min(viewport.width / width, viewport.height / height) * margin));
  view = {x: -viewport.width / zoom / 2, y: -viewport.height / zoom / 2, width: viewport.width / zoom, height: viewport.height / zoom};
  render();
  // As zoom() does: a held move asks again for the view now shown.
  if (gesture?.kind === 'move' && preview && !gesture.released && pointerPosition) {
    preview = {kind: 'move', end: point(pointerPosition)}; previewSerial++;
    void refreshGesturePreview();
  }
}

function zoom(factor) {
  if (!ui || !editor.info) return;
  view = zoomView(view, {width: canvas.clientWidth, height: canvas.clientHeight}, factor, ui.navigation);
  render(); refreshHover();
  // A held move joins ends within an on-screen reach: ask again at the new zoom,
  // from where the held pointer now is; a reply asked before it is not shown.
  if (gesture?.kind === 'move' && preview && !gesture.released && pointerPosition) {
    preview = {kind: 'move', end: point(pointerPosition)}; previewSerial++;
    void refreshGesturePreview();
  }
}

function point(event) {
  const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(canvas.getScreenCTM().inverse());
  return {x: p.x, y: p.y};
}

function hoverPoint() {
  const item = document.elementFromPoint(pointerPosition.clientX, pointerPosition.clientY)?.closest('[data-item]');
  const [kind, id] = (item && canvas.contains(item) ? item.dataset.item : '').split(':');
  // The server resolves the desktop's hover target from the full hit stack.
  return {...point(pointerPosition), atom_id: kind === 'atom' ? Number(id) : null,
    hits: hitsAt(pointerPosition.clientX, pointerPosition.clientY), scale: viewScale()};
}

function cancelGesture() {
  cancelSmilesInsert();
  const pointer = gesture?.pointer;
  if (gesture?.kind === 'marquee' && !gesture.accepted) selection = new Set(gesture.initialSelection);
  gesture = preview = previewInfo = null;
  markHover.request = markHover.result = null;
  previewSerial++;
  if (pointer !== undefined && canvas.hasPointerCapture(pointer)) canvas.releasePointerCapture(pointer);
  render();
}

function groupUnits() { return editor.info?.drawing?.groups ?? []; }

// Shift-click toggles a group as one unit: off if any member is selected.
function toggleUnit(key) {
  const unit = groupUnit(key, groupUnits());
  if (unit.some(member => selection.has(member))) unit.forEach(member => selection.delete(member));
  else unit.forEach(member => selection.add(member));
}

async function edit(change) {
  if (loading || editor.busy || editor.readOnly) return;
  cancelSmilesInsert();
  notice();
  const pending = editor.perform(change);
  render();
  try { await pending; if (change.kind === 'bond_length') handleTarget = null; if (editor.info.edit_notice) notice(editor.info.edit_notice); return true; }
  catch (error) { notice(error.message, true); return false; }
  finally { render(); refreshHover(); }
}

async function loadDocument(infoPromise, name) {
  closeNoteEditor();
  loading = true;
  selection = new Set();
  cancelGesture();
  render();
  try {
    const info = await infoPromise;
    await editor.load(info, name);
    resetForDocument();
    notice(info.unsupported.length ? `Incomplete, read-only preview: ${info.unsupported.join(', ')}. These elements are not faithfully displayed. Save copy preserves their data, and Export MOL writes selected structures; use the desktop app to edit this drawing or export a figure.` : '');
    actualSize();
  } catch (error) { notice(error.message, true); }
  finally { loading = false; render(); }
}

// Each opened drawing starts with the desktop's per-canvas tool and view state.
function resetForDocument() {
  tool = 'bond'; paintColor = null; contextPage = null;
  grid = {enabled:false,style:ui.grid.style,opacity:ui.grid.opacity};
  valenceChecking = true;
}

// File > Recover Unsaved Work: drafts the server kept for closed or earlier
// windows, across reloads and restarts. Recovering takes that one draft over,
// so it never becomes a second copy; it replaces this window's drawing only
// after the usual unsaved-changes question, and an open window holding the
// draft is closed only after its own confirmation.
function describeDraft(entry) {
  if (entry.problem) return entry.problem;
  const saved = entry.saved_at ? `Saved ${new Date(entry.saved_at * 1000).toLocaleString()}.` : '';
  if (!entry.open) return saved;
  const idle = entry.idle_seconds === null ? '' : `, last active ${Math.round(entry.idle_seconds / 60)} min ago`;
  return `${saved} Still open in another browser window${idle}.`;
}

function fillRecoveryDialog(listing) {
  $('recover-summary').textContent = !listing.available
    ? listing.message ?? 'Automatic recovery is not available in this window.'
    : listing.drafts.length ? 'Recovering replaces the drawing in this window. A discarded draft cannot be restored.' : 'There is no unsaved work to recover.';
  $('recover-list').replaceChildren(...listing.drafts.map(entry => {
    const row = document.createElement('li'), title = document.createElement('strong'), detail = document.createElement('span');
    title.textContent = entry.name ?? 'Unreadable draft';
    detail.textContent = describeDraft(entry);
    const recover = document.createElement('button'), discard = document.createElement('button');
    recover.type = discard.type = 'button';
    recover.textContent = 'Recover'; discard.textContent = 'Discard';
    recover.disabled = Boolean(entry.problem);
    discard.disabled = entry.open;
    recover.onclick = () => { $('recover-dialog').close('cancel'); void recoverDraft(entry); };
    discard.onclick = () => void discardDraft(entry);
    row.append(title, detail, recover, discard);
    return row;
  }));
}

async function showRecovery() {
  if (!editor.info?.session || editor.busy || loading) return;
  try { fillRecoveryDialog(await api('session', {session: editor.info.session, action: 'drafts'})); }
  catch (error) { notice(error.message, true); return; }
  void openDialog($('recover-dialog'));
}

async function discardDraft(entry) {
  if (!confirm(`Permanently discard the unsaved work in “${entry.name ?? 'this unreadable draft'}”?`)) return;
  try { fillRecoveryDialog(await api('session', {session: editor.info.session, action: 'discard_draft', draft: entry.id})); }
  catch (error) { notice(error.message, true); }
}

async function recoverDraft(entry) {
  if (entry.open && !confirm(`“${entry.name}” is still open in another browser window. Recover it here and close it there?`)) return;
  if (!mayReplace()) return;
  closeNoteEditor();
  loading = true;
  selection = new Set();
  cancelGesture();
  render();
  try {
    await editor.recover(entry.id, entry.open);
    resetForDocument();
    notice(`Recovered ${editor.name}. It stays unsaved until you save a copy.`);
    actualSize();
  } catch (error) { notice(error.message, true); }
  finally { loading = false; render(); }
}

// After startup, say truthfully whether earlier work waits for recovery; the
// drawing in this window is never replaced without the user's choice.
async function offerRecovery() {
  const previous = sessionStorage.getItem(closedSessionKey);
  sessionStorage.removeItem(closedSessionKey);
  if (previous && previous !== editor.info?.session) await api('session', {session: previous, action: 'close'}).catch(() => {});
  if (!editor.info?.session) return;
  let listing;
  try { listing = await api('session', {session: editor.info.session, action: 'drafts'}); }
  catch (error) { notice(error.message, true); return; }
  if (!listing.available) { if (listing.message) notice(listing.message, true); return; }
  // Drafts held by windows still open are theirs, not earlier work.
  const ready = listing.drafts.filter(entry => !entry.problem && !entry.open).length;
  if (ready && $('notice').hidden) notice(`Unsaved work from ${ready === 1 ? 'an earlier window' : `${ready} earlier windows`} can be recovered. Choose File > Recover Unsaved Work… to restore or discard it.`);
}

// Edit > Copy and Cut of the canvas selection. The server's copy reply is
// requested inside the user gesture, so the system clipboard write starts
// before it arrives; Cut then deletes through the usual one-step edit.
async function copyChemistry(cut) {
  if (!editor.document || editor.busy || loading || gesture || !selection.size || (cut && editor.readOnly)) return;
  const items = selectedItems(), {session, revision} = editor.info;
  const payload = api('session', {session, revision, action: 'copy', selection: items}).then(reply => reply.payload);
  const isCurrent = () => !editor.busy && !loading && editor.info?.session === session && editor.info?.revision === revision;
  let outcome;
  try {
    outcome = await copySelection({store: chemistryClipboard, payload, cut, isCurrent, remove: () => edit({kind: 'delete_selection', selection: items})});
  } catch (error) { notice(error.message, true); return; }
  if (outcome.removed) { selection.clear(); render(); }
  if (outcome.stale) notice('The drawing changed before Cut finished. The selection was copied but not removed.', true);
  else if ((!cut || outcome.removed) && !outcome.copied.system) notice('Copied for pasting in this browser window only: the browser did not allow access to the system clipboard.');
}

// Edit > Paste: a Chemvas selection from the system clipboard, else this
// window's own copy (see pasteText). The server validates, offsets and remaps
// it in one Undo/Redo step, and the pasted items become the selection.
async function pasteChemistry(systemText) {
  if (!editor.document || editor.busy || loading) return;
  if (editor.readOnly) { notice('This drawing is read-only in the browser adapter.', true); return; }
  const text = chemistryClipboard.textFor(systemText);
  if (text === null) {
    notice(systemText === null ? 'The browser did not allow reading the clipboard. Press ⌘/Ctrl+V on the canvas to paste.' : 'The clipboard does not contain a Chemvas selection.', true);
    return;
  }
  if (new Blob([text]).size > ui.max_clipboard_bytes) { notice('The Chemvas clipboard selection is too large to paste.', true); return; }
  cancelGesture();
  if (await edit({kind: 'paste', payload: text})) {
    selection = new Set((editor.info.pasted ?? []).map(item => `${item.target}:${item.id}`));
    render();
  }
}

// Edit > Paste reads the system clipboard first, which can wait on the
// browser's permission prompt; it pastes only into the drawing it was chosen
// for, never into one loaded, recovered or edited meanwhile.
async function pasteFromMenu() {
  if (!editor.document || editor.busy || loading) return;
  const {session, revision} = editor.info;
  const systemText = await chemistryClipboard.read();
  if (editor.info?.session !== session || editor.info?.revision !== revision) {
    notice('The drawing changed while the clipboard was being read. Nothing was pasted.', true);
    return;
  }
  await pasteChemistry(systemText);
}

// The canvas takes clipboard keys and events unless text is being edited or
// selected outside it, so fields, notes and page text keep the browser's own
// clipboard. Label text dragged over inside the drawing is not a text selection.
function canvasOwnsClipboard(target) {
  if (!editor.document || noteEditor || document.querySelector('dialog[open]')) return false;
  if (target instanceof Element && target.closest('input, textarea, select, [contenteditable]')) return false;
  const text = getSelection();
  return !text || text.isCollapsed || canvas.contains(text.anchorNode);
}
for (const kind of ['copy', 'cut']) {
  document.addEventListener(kind, event => {
    if (!selection.size || !canvasOwnsClipboard(event.target)) return;
    event.preventDefault();
    void copyChemistry(kind === 'cut');
  });
}
document.addEventListener('paste', event => {
  if (!canvasOwnsClipboard(event.target)) return;
  event.preventDefault();
  void pasteChemistry(event.clipboardData?.getData('text/plain') ?? null);
});

// Whether the open note holds text its commit would save, or an emptied note it
// would delete, read as finishNoteEdit reads it; nothing is committed or closed.
function pendingNoteChanges() {
  if (!noteEditor) return false;
  const active = noteEditor, empty = !noteEditorElement.textContent.trim();
  const typed = active.typing && typedBlocks(active.typing);
  const html = noteBlocksHtml(typed || noteBlocks(noteEditorElement, active.style), active.style);
  return html !== active.original && !(active.id === null && empty);
}

function mayReplace() {
  return !editor.busy && !loading && (!(editor.dirty || pendingNoteChanges()) || confirm('Discard unsaved changes? Their recovery draft is removed too. Save a copy first if you want to keep them.'));
}

function download(text, name, type) {
  const url = URL.createObjectURL(new Blob([text], {type}));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

async function atomInput(change) {
  loading = true;
  render();
  let text;
  try {
    const plan = await api('session', {session: editor.info.session, revision: editor.info.revision, action: 'atom_input', edit: change, symbol: $('atom-symbol').value});
    if (change.kind === 'atom_prompt') {
      if (!plan.needs_prompt) return;
      change = {...change, atom_id: plan.atom_id};
    }
    text = plan.text;
    if (plan.needs_prompt) {
      const dialog = $('atom-dialog');
      $('atom-label').value = plan.initial;
      const closed = openDialog(dialog);
      $('atom-label').focus();
      $('atom-label').select();
      text = await closed === 'ok' ? $('atom-label').value : null;
    }
  } catch (error) { notice(error.message, true); }
  finally { loading = false; render(); }
  if (text !== null && text !== undefined) await edit({...change, text});
}

// Resolves with the dialog's return value; only the OK submit returns 'ok'.
function openDialog(dialog) {
  dialog.returnValue = 'cancel';
  const closed = new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue), {once: true}));
  dialog.showModal();
  return closed;
}

function hitsAt(clientX, clientY) {
  return selectedItems(new Set(document.elementsFromPoint(clientX, clientY)
    .filter(element => canvas.contains(element)).map(itemKey).filter(Boolean)));
}

function selectedItems(keys = selection) {
  return [...keys].map(key => {
    const [target, id] = key.split(':');
    return {target, id: Number(id)};
  });
}

async function deleteSelection(allowHover = false) {
  if (!selection.size && (!allowHover || !pointerPosition)) return;
  cancelGesture();
  const items = selectedItems();
  const change = items.length ? {kind: 'delete_selection', selection: items} : {kind: 'delete_hover', ...hoverPoint()};
  if (await edit(change)) selection.clear();
  render();
}

function selectAll() {
  if (!editor.document || editor.readOnly || editor.busy || loading) return;
  cancelGesture();
  tool = 'select';
  const model = editor.document.state.model;
  selection = new Set([
    ...Object.keys(model.atoms).map(id => `atom:${id}`),
    ...model.bonds.flatMap((bond, id) => bond ? [`bond:${id}`] : []),
    ...editor.document.state.arrows.map((_, id) => `arrow:${id}`),
    ...editor.document.state.shapes.map((_, id) => `shape:${id}`),
    ...editor.document.state.ring_fills.map((_, id) => `ring:${id}`),
    ...editor.document.state.marks.map((_, id) => `mark:${id}`),
    ...editor.document.state.orbitals.map((_, id) => `orbital:${id}`),
    ...editor.document.state.ts_brackets.map((_, id) => `ts_bracket:${id}`),
    ...editor.document.state.notes.map((_, id) => `note:${id}`),
    ...(editor.document.state.images ?? []).map((_, id) => `image:${id}`),
  ]);
  render();
}

// A shape or bracket guide styles the preview document's newest item, so it
// waits for that document; the committed drawing keeps its own colours.
function scenePreview() {
  if (gesture?.kind === 'bond' && previewInfo) return null;
  if (['shape', 'ts_bracket'].includes(preview?.kind) && !previewInfo) return null;
  return preview;
}

// Native tool hotkeys reset the tool's kind; Shift variants name their default.
function switchByHotkey(next, shifted) {
  if (shifted) {
    if (shifted.tool !== next) return;
    if (next === 'ts_bracket') bracketKind = shifted.value;
    else if (next === 'orbital') orbitalKind = shifted.value;
    else if (next === 'mark') markKind = shifted.value;
  } else if (next === 'bond') bondStyle = ui.default_bond_style;
  else if (next === 'arrow') arrowStyle = ui.default_arrow_style;
  setTool(next);
}

function setTool(next) { if (supportedTools.has(next)) { if (next !== 'note') finishNoteEdit(); if (next === 'benzene') ringTemplate = ui.templates[0]; handleTarget = null; cancelGesture(); contextPage = next === 'ring_fill' ? next : null; tool = next === 'ring_fill' ? 'select' : next; render(); refreshHover(); } }

canvas.addEventListener('pointerdown', event => {
  if (!editor.document || editor.busy || loading || gesture || event.button !== 0
      || (ui.navigation.zoom_modifier === 'meta' && event.ctrlKey)) return;
  canvas.focus();
  pointerPosition = {clientX: event.clientX, clientY: event.clientY};
  const p = point(event);
  if (smilesInsert) {
    event.preventDefault();
    void commitSmilesInsert(p);
    return;
  }
  const item = event.target.closest('[data-item]')?.dataset.item ?? null;
  const [kind, rawId] = item?.split(':') ?? [];
  const id = Number(rawId);
  const hits = hitsAt(event.clientX, event.clientY);
  const scale = viewScale();
  const handle = event.target.closest('[data-handle]');
  if (tool === 'select' && handle?.dataset.handle === ui.handles.rotation_type && !editor.readOnly) {
    gesture = {kind:'rotate', start:p, shift:event.shiftKey, selection:selectedItems(), pointer:event.pointerId,
      session:editor.info.session, revision:editor.info.revision};
  } else if (tool === 'select' && handle && !editor.readOnly) {
    gesture = {kind: 'handle', target: handle.dataset.orbitalId !== undefined ? 'orbital' : handle.dataset.shapeId === undefined ? 'arrow' : 'shape', id: Number(handle.dataset.orbitalId ?? handle.dataset.shapeId ?? handle.dataset.arrowId), handle: handle.dataset.handle,
      pointer: event.pointerId, end: p, previous: null, moved: false, scale,
      session: editor.info.session, revision: editor.info.revision};
  } else if (tool === 'select') {
    gesture = {kind: 'pick', start: p, end: p, pointer: event.pointerId, shift: event.shiftKey, additive: ui.navigation.zoom_modifier === 'meta' ? event.metaKey : event.ctrlKey, initialSelection: [...selection], hits, scale,
      session: editor.info.session, revision: editor.info.revision, released: false};
    void resolveSelection(gesture);
  } else if (!editor.readOnly) {
    if (!['delete', 'color'].includes(tool) && !pointInSheet(p, editor.info.sheet)) {
      notice(ui.off_sheet_guidance, true);
      return;
    }
    if (tool === 'color') {
      if (paintColor === null) notice(ui.color_messages.choose);
      else void edit({kind: 'color', color: paintColor, selection: selectedItems(), x: p.x, y: p.y, hits, scale});
    } else if (tool === 'delete') { selection.clear(); void edit({kind: 'erase', x: p.x, y: p.y, hits, scale}); }
    else if (tool === 'text') void atomInput({kind: 'atom', x: p.x, y: p.y, atom_id: kind === 'atom' ? id : null});
    else if (tool === 'note') void noteToolPress(event);
    else if (tool === 'benzene') void edit({kind: 'ring', x: p.x, y: p.y, atom_id: kind === 'atom' ? id : null, size: ringTemplate.size, style: ringTemplate.style});
    else if (tool === 'orbital') void edit({kind:'orbital',x:p.x,y:p.y,orbital_kind:orbitalKind});
    else if (tool === 'mark') void editWithMarkMeasurements({kind:'mark',x:p.x,y:p.y,mark_kind:markKind,hits,scale});
    else {
      gesture = {kind: tool, start: p, pointer: event.pointerId, pressX: event.clientX, pressY: event.clientY, dragged: false, shift: event.shiftKey, style: tool === 'shape' ? shapeStyle : tool === 'line' ? lineStyle : tool === 'ts_bracket' ? bracketKind : arrowStyle, stroke: shapeStroke, scale, hits, session: editor.info.session, revision: editor.info.revision};
    }
  }
  if (gesture) canvas.setPointerCapture(event.pointerId);
  render();
});

function textFormatButton(spec, action, checkable = false) {
  const button = document.createElement('button');
  button.innerHTML = spec.icon; button.title = spec.tip;
  button.setAttribute('aria-label', spec.tip); button.dataset.editable = '';
  if (checkable) { button.dataset.textFormat = action.key; button.setAttribute('aria-pressed', 'false'); }
  // Keep the note editor focused, as the desktop's NoFocus tool buttons do.
  button.addEventListener('pointerdown', event => event.preventDefault());
  button.onclick = () => void applyTextFormat(action.key && ['left', 'center', 'right'].includes(action.key) ? {align: action.key} : action);
  return button;
}

// The editor selection as document offsets, anchor first.
function editorSelection() {
  const selected = getSelection();
  if (!noteEditor || !selected.rangeCount || !noteEditorElement.contains(selected.anchorNode)) return null;
  const a = noteTextOffset(noteEditorElement, noteEditor.style, selected.anchorNode, selected.anchorOffset);
  const b = noteTextOffset(noteEditorElement, noteEditor.style, selected.focusNode, selected.focusOffset);
  return [a, b];
}

function editorRange() {
  const offsets = editorSelection();
  return offsets && [Math.min(...offsets), Math.max(...offsets)];
}

// A new note's placeholder line break is not text: selecting it is the caret.
function editorCaret() {
  const range = editorRange();
  return range && !noteEditorElement.textContent ? [range[0], range[0]] : range;
}

function selectedNoteBlocks() {
  const style = {...editor.info.drawing.note_style, color: editor.document.state.settings.text_color};
  return [...selection].filter(key => key.startsWith('note:')).map(key => {
    const id = Number(key.split(':')[1]);
    const note = editor.info.drawing.notes?.find(item => item.id === id);
    if (!note) return null;
    const probe = document.createElement('div');
    probe.innerHTML = note.html;
    styleNoteText(probe, style, noteFont);
    return {id, style, blocks: noteBlocks(probe, style)};
  }).filter(Boolean);
}

const documentLength = blocks => blocks.reduce((total, block, index) => total + (index ? 1 : 0) + block.runs.reduce((n, run) => n + (run.br ? 1 : run.text.length), 0), 0);

// The desktop formats the open editor's selection, else each selected note whole.
async function applyTextFormat(action) {
  if (editor.readOnly || editor.busy || loading) return;
  if (noteEditor) {
    if (noteEditor.composing) return;
    const range = editorCaret();
    if (!range) return;
    const [start, end] = range;
    const blocks = noteBlocks(noteEditorElement, noteEditor.style);
    if (start === end && !action.align) {
      // QTextCursor::mergeCharFormat without a selection: toggles and size steps
      // accumulate on the format the next typed text takes, and no text changes.
      const base = caretCharFormat(blocks, start);
      const [low, high] = ui.text_format.size_range;
      const next = {...base};
      if (action.delta) next.pt = Math.max(low, Math.min(high, base.pt + action.delta));
      else if (action.key === 'bold') next.bold = !base.bold;
      else if (action.key === 'italic') next.italic = !base.italic;
      else { const sc = action.key === 'superscript' ? 'super' : 'sub'; next.script = base.script === sc ? null : sc; }
      noteEditor.caretFormat = next;
      noteEditor.caretAt = start;
      noteEditor.run = null;
      refreshTextFormatState();
      return;
    }
    // The selection takes its format in the editor at once; note_markup only
    // renders it, so input made meanwhile keeps its text and this format.
    const before = noteSnapshot();
    formatNoteBlocks(blocks, start, end, action, ui.text_format.size_range);
    showNoteBlocks(blocks, editorSelection());
    commitNoteStep(before);
    refreshTextFormatState();
    return;
  }
  const targets = selectedNoteBlocks();
  if (!targets.length) { notice(ui.text_format.target_message); return; }
  const notes = targets.map(({id, style, blocks}) => {
    formatNoteBlocks(blocks, 0, documentLength(blocks), action, ui.text_format.size_range);
    return {id, html: noteBlocksHtml(blocks, style)};
  });
  await edit({kind: 'note_format', notes});
}

function refreshTextFormatState() {
  if (!ui || tool !== 'note') return;
  const align = editor.document?.state.settings.text_alignment ?? 'left';
  let state = null;
  if (noteEditor) {
    const range = editorCaret();
    if (range) {
      const blocks = noteBlocks(noteEditorElement, noteEditor.style);
      state = noteFormatState(blocks, ...range, align);
      // A caret shows the format typed text would take.
      if (range[0] === range[1]) {
        const format = caretCharFormat(blocks, range[0]);
        state = {...state, bold: format.bold, italic: format.italic, superscript: format.script === 'super', subscript: format.script === 'sub'};
      }
    }
  } else {
    const states = selectedNoteBlocks().map(({blocks}) => noteFormatState(blocks, 0, documentLength(blocks), align));
    if (states.length) state = Object.fromEntries(Object.keys(states[0]).map(key => [key, states.every(item => item[key])]));
  }
  document.querySelectorAll('[data-text-format]').forEach(button => button.setAttribute('aria-pressed', String(Boolean(state?.[button.dataset.textFormat]))));
}
document.addEventListener('selectionchange', () => {
  if (!noteEditor) return;
  // Moving the caret forgets the typing format, as QTextCursor::setPosition does;
  // restoring the same caret after the editor re-renders keeps it. An IME moves
  // the caret over its own uncommitted text.
  const range = editorCaret(), at = noteEditor.caretAt;
  if (noteEditor.caretFormat && !noteEditor.composing && !(range?.[0] === at && range[1] === at)) noteEditor.caretFormat = noteEditor.typing = null;
  refreshTextFormatState();
});

function positionNoteEditor() {
  if (!noteEditor) { noteEditorElement.hidden = true; return; }
  // Screen transform of the note: canvas CTM, then its position and rotation.
  const m = canvas.getScreenCTM(), angle = noteEditor.rotation * Math.PI / 180;
  const cos = Math.cos(angle), sin = Math.sin(angle);
  noteEditorElement.style.transform = `matrix(${m.a * cos + m.c * sin},${m.b * cos + m.d * sin},${m.c * cos - m.a * sin},${m.d * cos - m.b * sin},${m.a * noteEditor.x + m.c * noteEditor.y + m.e},${m.b * noteEditor.x + m.d * noteEditor.y + m.f})`;
  noteEditorElement.hidden = false;
}

function beginNoteEdit(id, x, y) {
  const drawing = editor.info.drawing, style = {...drawing.note_style, color: editor.document.state.settings.text_color};
  const note = id === null ? null : drawing.notes?.find(item => item.id === id);
  if (id !== null && !note) return;
  noteEditor = {id, x: note?.x ?? x, y: note?.y ?? y, rotation: note?.rotation ?? 0, style,
    session: editor.info.session, revision: editor.info.revision, caretFormat: null, normalized: true,
    undoSteps: [], redoSteps: [], run: null};
  noteEditorElement.innerHTML = note ? note.html : '<p data-style="margin-top:0px; margin-bottom:0px; white-space:pre-wrap"><br></p>';
  styleNoteText(noteEditorElement, style, noteFont);
  const base = noteFont(style);
  noteEditorElement.style.lineHeight = `${Math.ceil(base.ascent + base.descent + base.leading) * style.line_spacing}px`;
  noteEditor.original = serializeNoteEditor(noteEditorElement, style);
  selection = id === null ? new Set() : new Set([`note:${id}`]);
  render();
  document.execCommand('defaultParagraphSeparator', false, 'p');
  noteEditorElement.focus();
  // The desktop selects the whole note when editing begins.
  const range = document.createRange();
  range.selectNodeContents(noteEditorElement);
  getSelection().removeAllRanges();
  getSelection().addRange(range);
}

function closeNoteEditor() {
  noteEditor = null;
  noteEditorElement.hidden = true;
  noteEditorElement.replaceChildren();
  noteEditorElement.removeAttribute('style');
}

// NoteItem's focus out: save changed text once, delete an emptied note, and
// drop a new note that never received text. The commit resolves false when the
// text was not saved: the note then reopens with it where that is still safe.
function finishNoteEdit() {
  if (!noteEditor) return noteCommit;
  const active = noteEditor, empty = !noteEditorElement.textContent.trim();
  // Text an IME is still composing is saved with its pending format; the
  // editor itself is not rewritten under the IME.
  const typed = active.typing && typedBlocks(active.typing);
  const blocks = typed || noteBlocks(noteEditorElement, active.style);
  const html = noteBlocksHtml(blocks, active.style), kept = noteEditorMarkup(blocks), offsets = editorSelection();
  closeNoteEditor();
  render();
  if (html === active.original || (active.id === null && empty)) return noteCommit;
  if (editor.info.session !== active.session || editor.info.revision !== active.revision) {
    notice('The drawing changed while the note was open; its text was not saved.', true);
    return trackNoteCommit(Promise.resolve(false));
  }
  const change = active.id === null ? {kind: 'note_text', id: null, x: active.x, y: active.y, html} : {kind: 'note_text', id: active.id, html};
  return trackNoteCommit(edit(change).then(saved => {
    if (saved === true) return true;
    reopenNoteEditor(active, kept, offsets);
    return false;
  }));
}

// Callers arriving while a commit is pending share its outcome; once it settles,
// later callers start from a settled success rather than that failure.
function trackNoteCommit(outcome) {
  const commit = outcome.then(saved => {
    if (noteCommit === commit) noteCommit = Promise.resolve(true);
    return saved;
  });
  noteCommit = commit;
  return commit;
}

// A note whose text was not saved reopens holding that text, selection, original
// and Undo/Redo steps, as a fresh editor, so work still bound to the closed one
// (its normalization reply or error) cannot act on it. It never reopens over a
// load, a newer note, SMILES insertion or a changed drawing: a revision change
// may mean the text was applied after all. A tool switch that ended the note
// returns to the Text tool, and focus stays where the user put it.
function reopenNoteEditor(active, markup, offsets) {
  if (noteEditor || loading || smilesInsert || editor.info?.session !== active.session || editor.info?.revision !== active.revision) return;
  const {id, x, y, rotation, style, session, revision, original} = active;
  noteEditor = {id, x, y, rotation, style, session, revision, original, caretFormat: null, normalized: true,
    undoSteps: [...active.undoSteps], redoSteps: [...active.redoSteps], run: null};
  if (tool !== 'note') { tool = 'note'; contextPage = null; }
  showNoteHtml(markup, offsets);
  const base = noteFont(style);
  noteEditorElement.style.lineHeight = `${Math.ceil(base.ascent + base.descent + base.leading) * style.line_spacing}px`;
  selection = id === null ? new Set() : new Set([`note:${id}`]);
  render();
}

async function noteToolPress(event) {
  // A note that could not be saved stays open instead of a new one opening.
  if (await finishNoteEdit() === false) return;
  if (smilesInsert) return;
  if (editor.busy || loading || editor.readOnly || tool !== 'note') return;
  const p = point(event), session = editor.info.session, revision = editor.info.revision, generation = smilesGeneration;
  let target = null;
  try {
    ({target} = await api('session', {session, revision, action: 'pick', ...p,
      hits: hitsAt(event.clientX, event.clientY), scale: viewScale(), preferred: false}));
  } catch (error) { notice(error.message, true); return; }
  if (generation !== smilesGeneration || smilesInsert || editor.info.session !== session || editor.info.revision !== revision || tool !== 'note') return;
  if (target?.target === 'note') {
    const key = `note:${target.id}`;
    const toggle = ui.navigation.zoom_modifier === 'meta' ? event.metaKey : event.ctrlKey;
    if (toggle) { toggleUnit(key); render(); }
    else if (event.shiftKey) { groupUnit(key, groupUnits()).forEach(member => selection.add(member)); render(); }
    else beginNoteEdit(target.id);
    return;
  }
  beginNoteEdit(null, p.x, p.y);
}
noteEditorElement.addEventListener('focusout', event => {
  // Moving focus inside the editor, or back to it, keeps the session open.
  if (!noteEditorElement.contains(event.relatedTarget)) void finishNoteEdit();
});
// A copied Chemvas selection is clipboard text too; it belongs on the canvas,
// never inside a note as raw data. Other pasted text stays the browser's.
noteEditorElement.addEventListener('paste', event => {
  if (!isSelectionText(event.clipboardData?.getData('text/plain'))) return;
  event.preventDefault();
  notice('A copied Chemvas selection pastes onto the canvas, not into a note. Finish the note, then paste.', true);
});

// QTextCursor::charFormat: the pending typing format at its caret, else the
// character before the caret, or after it at the start of a nonempty paragraph.
function caretCharFormat(blocks, position) {
  if (noteEditor.caretFormat && noteEditor.caretAt === position) return noteEditor.caretFormat;
  let offset = 0;
  for (const [index, block] of blocks.entries()) {
    if (index) offset += 1;
    const length = documentLength([block]);
    if (position <= offset + length) {
      const at = position === offset && length ? position + 1 : position;
      for (const run of block.runs) {
        const size = run.br ? 1 : run.text.length;
        if (!run.br && at > offset && at <= offset + size) return run.format;
        offset += size;
      }
      break;
    }
    offset += length;
  }
  const style = noteEditor.style;
  return {pt: style.point_size, bold: Number(style.weight) > 400, italic: style.italic, script: null};
}

// One character format over document offsets [start, end), splitting runs.
function setRunsFormat(blocks, start, end, format) {
  let offset = 0;
  blocks.forEach((block, index) => {
    if (index) offset += 1;
    const runs = [];
    for (const run of block.runs) {
      const length = run.br ? 1 : run.text.length, from = offset, to = offset + length;
      offset = to;
      if (run.br || to <= start || from >= end) { runs.push(run); continue; }
      const a = Math.max(start, from) - from, b = Math.min(end, to) - from;
      if (a > 0) runs.push({text: run.text.slice(0, a), format: run.format});
      runs.push({text: run.text.slice(a, b), format: {...format}});
      if (b < length) runs.push({text: run.text.slice(b), format: run.format});
    }
    block.runs = runs;
  });
}

// Replace the editor's markup, keeping its selection by document offset. A
// placeholder keeps an empty or break-ended line editable, as the browser does.
function showNoteHtml(html, offsets) {
  noteEditorElement.innerHTML = html.replace(/(<p[^>]*>|<br>)<\/p>/g, '$1<br></p>');
  styleNoteText(noteEditorElement, noteEditor.style, noteFont);
  if (offsets) getSelection().setBaseAndExtent(...noteTextPosition(noteEditorElement, offsets[0]), ...noteTextPosition(noteEditorElement, offsets[1]));
}

// The adapter's Qt pixel sizes (browser_font_pixels, qt_script_pixels): QFont's
// rounded 96-dpi em, and QTextEngine's two-thirds script size.
const notePixels = point => Math.max(1, Math.floor(point * 96 / 72 + 0.5));
const noteScriptPixels = point => notePixels(Math.max(1, Math.floor(Math.floor(point + 0.5) * 2 / 3)));

// noteBlocksHtml's flat runs in the markup note_markup returns for them, so
// sizes and script offsets show before its reply as they will after it.
function noteEditorMarkup(blocks) {
  const style = noteEditor.style;
  return noteBlocksHtml(blocks, style).replace(/<(p|span) style="([^"]*)"/g, (_, tag, css) => {
    const declarations = css ? css.split('; ') : [];
    const pt = declarations.map(item => /^font-size:([\d.]+)pt$/.exec(item)?.[1]).find(Boolean);
    const script = declarations.map(item => /^vertical-align:(sub|super)$/.exec(item)?.[1]).find(Boolean);
    const kept = declarations.filter(item => !/^(font-size|vertical-align):/.test(item)), size = Number(pt ?? style.point_size);
    if (script) kept.push(`font-size:${noteScriptPixels(size)}px`);
    else if (pt) kept.push(`font-size:${notePixels(size)}px`);
    return `<${tag}${kept.length ? ` data-style="${kept.join('; ')}"` : ''}`
      + (script ? ` data-script="${script}" data-base-pixels="${notePixels(size)}"` : '') + (pt ? ` data-pt="${pt}"` : '');
  });
}

// The editor holds formatted runs at once; note_markup then only confirms them.
function showNoteBlocks(blocks, offsets) {
  showNoteHtml(noteEditorMarkup(blocks), offsets);
  noteEditor.normalized = false;
  void normalizeNoteEditor(noteEditor);
}

// This note-edit session's own Undo and Redo. The browser's native history
// cannot follow the editor re-rendering formatted runs, so every change is
// recorded here as the editor's markup and selection before it. A step is one
// change, except that contiguous typing, or contiguous deletion in one
// direction, extends the step before it; a caret move, format action,
// composition, Undo or Redo ends that grouping. Caret formats, cancelled
// compositions and note_markup replies change no content and record nothing.
const noteRunKinds = {insertText: 'text', deleteContentBackward: 'back', deleteContentForward: 'forward'};
function noteSnapshot() {
  return {html: noteEditorMarkup(noteBlocks(noteEditorElement, noteEditor.style)), selection: editorSelection()};
}

function commitNoteStep(before) {
  const active = noteEditor, range = editorRange();
  const grouped = before.kind && active.run?.kind === before.kind && active.run.at === before.at;
  if (!grouped) {
    if (before.html === noteSnapshot().html) { active.run = null; return; }
    active.undoSteps.push({html: before.html, selection: before.selection});
  }
  active.redoSteps = [];
  active.run = before.kind && range && range[0] === range[1] ? {kind: before.kind, at: range[0]} : null;
}

function stepNoteHistory(redo) {
  const active = noteEditor;
  if (!active || active.composing) return;
  // Undo and Redo end any input still waiting for its own input event.
  active.before = active.typing = null;
  const step = (redo ? active.redoSteps : active.undoSteps).pop();
  if (!step) return;
  (redo ? active.undoSteps : active.redoSteps).push(noteSnapshot());
  active.run = active.caretFormat = null;
  active.normalized = true;
  showNoteHtml(step.html, step.selection);
  refreshTextFormatState();
}

// note_markup renders the editor's runs. Input while a reply is pending is
// already in the runs, so an obsolete reply is dropped and the current runs
// are rendered instead; no reply replaces text or formats made after it.
async function normalizeNoteEditor(active) {
  if (active.normalizing) return;
  active.normalizing = true;
  try {
    while (noteEditor === active && !active.normalized && !active.composing) {
      const html = serializeNoteEditor(noteEditorElement, active.style);
      let markup;
      try {
        ({html: markup} = await api('session', {session: active.session, revision: active.revision, action: 'note_markup', html}));
      } catch (error) { if (noteEditor === active) notice(error.message, true); return; }
      if (noteEditor !== active || active.composing || serializeNoteEditor(noteEditorElement, active.style) !== html) continue;
      active.normalized = true;
      showNoteHtml(markup, editorSelection());
      refreshTextFormatState();
    }
  } finally { active.normalizing = false; }
}

// Qt types with the caret's format: inserted text takes the pending format in
// the editor at once, and later input continues inside it. IME text takes it
// once committed; the editor is never rewritten while an IME composes.
function beginTyping() {
  if (!noteEditor) return;
  const format = noteEditor.caretFormat, range = editorCaret(), at = noteEditor.caretAt;
  noteEditor.typing = format && range?.[0] === at && range[1] === at ? {format, start: at} : null;
}

// The editor's runs with the text its input reported inserted given the pending
// format, or null when nothing was inserted or that format is no longer pending.
// A later caret never decides what gets formatted.
function typedBlocks(typing) {
  if (noteEditor.caretFormat !== typing.format || !(typing.end > typing.start)) return null;
  const blocks = noteBlocks(noteEditorElement, noteEditor.style);
  setRunsFormat(blocks, typing.start, typing.end, typing.format);
  return blocks;
}

function finishTyping() {
  const typing = noteEditor?.typing;
  if (!typing) return;
  noteEditor.typing = null;
  const blocks = typedBlocks(typing);
  if (!blocks) return;
  noteEditor.caretFormat = null;
  showNoteBlocks(blocks, editorSelection());
}

noteEditorElement.addEventListener('compositionstart', () => {
  if (!noteEditor) return;
  noteEditor.composing = true;
  // A committed composition is one step; a cancelled one is none. It owns that
  // step, so a beforeinput still waiting for its input event ends here.
  noteEditor.compositionBefore = noteSnapshot();
  noteEditor.run = noteEditor.before = null;
  beginTyping();
});
noteEditorElement.addEventListener('compositionend', event => {
  if (!noteEditor) return;
  noteEditor.composing = false;
  // The committed text, or none when the IME cancelled.
  if (noteEditor.typing && typeof event.data === 'string') noteEditor.typing.end = noteEditor.typing.start + event.data.length;
  finishTyping();
  const before = noteEditor.compositionBefore;
  noteEditor.compositionBefore = null;
  if (before) commitNoteStep(before);
  void normalizeNoteEditor(noteEditor);
});
noteEditorElement.addEventListener('beforeinput', event => {
  if (!noteEditor || event.isComposing || noteEditor.composing) return;
  noteEditor.before = null;
  if (event.inputType === 'historyUndo' || event.inputType === 'historyRedo') {
    // The browser's own Undo and Redo, from any menu, take this session's steps.
    event.preventDefault();
    stepNoteHistory(event.inputType === 'historyRedo');
    return;
  }
  // Only typing at the caret takes the pending format; a replacement or any
  // other edit may change a range that does not start there.
  if (['insertText', 'insertParagraph', 'insertLineBreak'].includes(event.inputType)) beginTyping();
  else noteEditor.typing = null;
  const range = editorRange();
  noteEditor.before = {...noteSnapshot(), kind: noteRunKinds[event.inputType], at: range && range[0] === range[1] ? range[0] : null};
});
noteEditorElement.addEventListener('input', event => {
  if (!noteEditor) return;
  const typing = noteEditor.typing;
  // The inserted text ends where this input's own data says, as the input
  // happens; an IME's data is its whole uncommitted text. Without data the
  // range is unknown, and nothing is formatted.
  if (typing && typeof event.data === 'string') typing.end = typing.start + event.data.length;
  if (event.isComposing || noteEditor.composing) return;
  const before = noteEditor.before;
  noteEditor.before = null;
  if (typing && event.inputType === 'insertText') finishTyping();
  else if (typing && ['insertParagraph', 'insertLineBreak'].includes(event.inputType)) {
    // A new line keeps the pending format for the text typed on it.
    noteEditor.typing = null;
    noteEditor.caretAt = editorCaret()?.[0];
  } else {
    // Pasted, dropped, deleted and replaced content keeps the browser's own
    // runs; any other edit ends the typing format rather than restyling it.
    noteEditor.typing = null;
    forgetCaretFormat();
  }
  if (before) commitNoteStep(before);
  else {
    // An input without a beforeinput of its own has no state recorded before
    // it: it records no step, and Redo can no longer restore over it.
    noteEditor.redoSteps = [];
    noteEditor.run = null;
  }
});
// Navigation keys and pointer presses place the caret even where its offset
// ends up unchanged, and each forgets the typing format as
// QTextCursor::setPosition does. An IME owns navigation while it composes.
const noteNavigationKeys = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown']);
function forgetCaretFormat() {
  if (!noteEditor || noteEditor.composing) return;
  noteEditor.typing = null;
  if (!noteEditor.caretFormat) return;
  noteEditor.caretFormat = null;
  refreshTextFormatState();
}
// Undo and Redo keys take this session's steps rather than the browser's own
// history; an input method keeps every key while it composes.
noteEditorElement.addEventListener('keydown', event => {
  if (!noteEditor || event.isComposing || noteEditor.composing) return;
  const key = event.key.toLowerCase(), command = (event.ctrlKey || event.metaKey) && !event.altKey;
  if (command && (key === 'z' || (key === 'y' && event.ctrlKey && !event.shiftKey))) {
    event.preventDefault();
    stepNoteHistory(key === 'y' || event.shiftKey);
  } else if (noteNavigationKeys.has(event.key)) {
    noteEditor.run = null;
    forgetCaretFormat();
  }
});
noteEditorElement.addEventListener('pointerdown', () => {
  if (noteEditor) noteEditor.run = null;
  forgetCaretFormat();
});

// SMILES insertion is one disposable server candidate, separate from tool state.
function currentSmilesInsert(active) {
  return smilesInsert === active && active.session === editor.info?.session
    && active.revision === editor.info?.revision && !editor.readOnly;
}

function cancelSmilesInsert() { smilesInsert = null; smilesGeneration++; }

async function beginSmilesInsert() {
  if (!ui || !editor.document || loading || editor.busy || editor.readOnly) return;
  const smiles = $('smiles-input').value.trim();
  if (!smiles) return;
  const session = editor.info.session;
  const finishing = finishNoteEdit(), generation = smilesGeneration;
  const saved = await finishing;
  if (saved === false || generation !== smilesGeneration || session !== editor.info.session || loading || editor.busy || editor.readOnly) return;
  cancelGesture();
  templateHover.request = templateHover.result = null;
  notice();
  const [x, y, width, height] = visibleSceneRect();
  const center = {x: x + width / 2, y: y + height / 2};
  smilesInsert = {smiles, session: editor.info.session, revision: editor.info.revision,
    position: pointInSheet(center, editor.info.sheet) ? center : null, info: null, committing: false};
  canvas.focus(); render();
  void refreshSmilesPreview();
}

function smilesRequest(active, position) {
  return {kind: 'smiles', smiles: active.smiles, x: position.x, y: position.y};
}

function moveSmilesPreview(position) {
  const active = smilesInsert;
  if (!active || active.committing) return;
  active.position = position && pointInSheet(position, editor.info.sheet) ? position : null;
  // A previous position must not linger while a newer candidate is pending.
  active.info = null;
  render();
  void refreshSmilesPreview();
}

async function refreshSmilesPreview() {
  if (smilesPreviewPending) return;
  const run = async () => {
    while (smilesInsert?.position && !smilesInsert.committing && !loading && !editor.busy) {
      const active = smilesInsert, position = active.position;
      if (!currentSmilesInsert(active)) { cancelSmilesInsert(); render(); break; }
      try {
        const info = await sessionRequest({session: active.session, revision: active.revision,
          action: 'preview', edit: smilesRequest(active, position)});
        if (currentSmilesInsert(active) && !active.committing && active.position === position) {
          active.info = info; render(); break;
        }
      } catch (error) {
        if (currentSmilesInsert(active) && !active.committing) {
          cancelSmilesInsert(); render(); notice(error.message, true); break;
        }
      }
    }
  };
  smilesPreviewPending = run();
  try { await smilesPreviewPending; }
  finally { smilesPreviewPending = null; }
}

async function commitSmilesInsert(position) {
  const active = smilesInsert;
  if (!active || active.committing || loading || editor.busy || !currentSmilesInsert(active)) return;
  if (!pointInSheet(position, editor.info.sheet)) {
    moveSmilesPreview(null); notice(ui.off_sheet_guidance, true); return;
  }
  active.committing = true; active.info = null; render();
  // A preview may be completing the bounded font exchange. Never race it with
  // commit, and never replay an edit after a lost response.
  // Cancelled gesture and mark previews may still replace the session's font
  // set. Drain those older requests before preparing this insertion's glyphs.
  await Promise.allSettled([smilesPreviewPending, previewPending, markHover.pending]);
  if (!currentSmilesInsert(active)) return;
  loading = true; render();
  const change = smilesRequest(active, position);
  let prepared = false;
  try {
    await sessionRequest({session: active.session, revision: active.revision, action: 'preview', edit: change});
    prepared = currentSmilesInsert(active);
  } catch (error) {
    if (currentSmilesInsert(active)) notice(error.message, true);
  } finally { loading = false; }
  if (!currentSmilesInsert(active)) { render(); return; }
  cancelSmilesInsert();
  if (prepared) await edit(change);
  else render();
}

$('smiles-insert').onclick = () => void beginSmilesInsert();
$('smiles-input').onkeydown = event => {
  if (event.isComposing) return;
  if (event.key === 'Enter') { event.preventDefault(); void beginSmilesInsert(); }
  else if (event.key === 'Escape' && smilesInsert) { event.preventDefault(); cancelSmilesInsert(); render(); canvas.focus(); }
};

// Mark placement also needs the H metrics and +/- ink the labels may not use.
function markFont(spec) {
  const queries = [...new Map([...spec.queries, ...spec.mark_queries].map(query => [query.key, query])).values()];
  return measureLabels({...spec, queries});
}

async function editWithMarkMeasurements(change) {
  if (loading || editor.busy || editor.readOnly) return;
  loading = true; render();
  try {
    await api('session',{session:editor.info.session,revision:editor.info.revision,action:'measure',font:markFont(editor.info.drawing.label_measurements)});
  } catch (error) { notice(error.message,true); return; }
  finally { loading = false; render(); }
  return await edit(change);
}

function queueChargeEdit(change) {
  if (editor.readOnly || (!chargeEdits && (loading || editor.busy))) return Promise.resolve(false);
  const session = editor.info.session;
  const pending = (chargeEdits ?? Promise.resolve(true)).then(ok =>
    ok && editor.info.session === session ? editWithMarkMeasurements(change) : false
  ).catch(error => { notice(error.message,true); return false; });
  chargeEdits = pending;
  void pending.then(() => { if (chargeEdits === pending) chargeEdits = null; });
  return pending;
}

// The Ring tool's template preview under the pointer, as InsertController draws it.
const templateHover = {request: null, result: null, pending: false};
async function refreshTemplateHover() {
  if (!pointerPosition || tool !== 'benzene' || !editor.document || editor.readOnly || loading || editor.busy || gesture) {
    const visible = Boolean(templateHover.result);
    templateHover.request = templateHover.result = null; if (visible) render(); return;
  }
  const hit = document.elementFromPoint(pointerPosition.clientX, pointerPosition.clientY)?.closest('[data-item^="atom:"]');
  templateHover.request = {session: editor.info.session, revision: editor.info.revision, action: 'template_preview', ...point(pointerPosition),
    atom_id: hit && canvas.contains(hit) ? Number(hit.dataset.item.split(':')[1]) : null, size: ringTemplate.size, style: ringTemplate.style};
  if (templateHover.pending) return;
  templateHover.pending = true;
  try {
    while (templateHover.request) {
      const current = templateHover.request;
      let result = null;
      try { ({preview: result} = await api('session', current)); } catch { result = null; }
      if (templateHover.request === current && current.revision === editor.info.revision && tool === 'benzene') { templateHover.result = result; render(); }
      if (templateHover.request === current) break;
    }
  } finally { templateHover.pending = false; }
}

// Hover previews follow the pointer for the Mark and Ring tools.
function refreshHover() {
  if (smilesInsert) {
    markHover.request = markHover.result = templateHover.request = templateHover.result = null;
    moveSmilesPreview(pointerPosition ? point(pointerPosition) : null);
    return;
  }
  void refreshMarkHover();
  void refreshTemplateHover();
}

async function refreshMarkHover() {
  if (!pointerPosition || tool !== 'mark' || !editor.document || editor.readOnly || loading || editor.busy || gesture || !pointInSheet(point(pointerPosition),editor.info.sheet)) {
    const visible = Boolean(markHover.result);
    markHover.request = markHover.result = null; if (visible) render(); return;
  }
  const p = point(pointerPosition);
  const hits = hitsAt(pointerPosition.clientX, pointerPosition.clientY);
  const request = {session:editor.info.session,revision:editor.info.revision,action:'mark_preview',x:p.x,y:p.y,kind:markKind,hits,scale:viewScale()};
  markHover.request = request;
  if (markHover.pending) return;
  const run = async () => {
    while (markHover.request) {
      const current = markHover.request;
      let result;
      try { result = await api('session',{...current,font:markFont(editor.info.drawing.label_measurements)}); }
      catch { if (markHover.request === current) { markHover.request = markHover.result = null; render(); break; } else continue; }
      if (markHover.request && current.session === editor.info.session && current.revision === editor.info.revision && current.kind === markKind && tool === 'mark' && !loading && !editor.busy) {
        markHover.result = result; render();
      }
      if (markHover.request === current) break;
    }
  };
  markHover.pending = run();
  try { await markHover.pending; }
  finally { markHover.pending = false; }
}

async function resolveSelection(active) {
  try {
    const result = await api('session', {session: active.session, revision: active.revision,
      action: 'pick', x: active.start.x, y: active.start.y, hits: active.hits, scale: active.scale, preferred: !active.shift});
    if (gesture !== active) return;
    if (editor.info.session !== active.session || editor.info.revision !== active.revision) {
      cancelGesture();
      return;
    }
    const item = result.target ? `${result.target.target}:${result.target.id}` : null;
    // Control on an unselected object or arrow toggles it, with no drag.
    const itemKind = result.target?.target;
    if (item && active.additive && !active.shift && !selection.has(item)
        && (ui.direct_select_kinds.includes(itemKind) || itemKind === 'arrow')) {
      groupUnit(item, groupUnits()).forEach(key => selection.add(key));
      cancelGesture();
      return;
    }
    active.toggleHandle = !active.shift && (item?.startsWith('shape:') || ((item?.startsWith('arrow:') || item?.startsWith('orbital:')) && selection.has(item))) ? item : null;
    if (active.toggleHandle === null) handleTarget = null;
    if (!item) {
      if (!active.additive) selection.clear();
    } else if (active.shift) {
      toggleUnit(item);
    } else if (!selection.has(item)) selection = new Set(groupUnit(item, groupUnits()));
    if (!item) {
      active.kind = 'marquee';
      updateMarquee(active, active.end);
      if (active.released) { active.accepted = true; cancelGesture(); }
      return;
    }
    if (active.shift || editor.readOnly) { cancelGesture(); return; }
    active.kind = 'move'; active.selection = selectedItems(); active.hasArrows = active.selection.some(item => item.target === 'arrow');
    if (active.released) {
      finishSelection(active, active.end);
    } else {
      if (selectionGestureMoved(active, active.end)) {
        preview = {kind: 'move', end: active.end}; previewSerial++;
        void refreshGesturePreview();
      }
      render();
    }
  } catch (error) {
    if (gesture === active) { cancelGesture(); notice(error.message, true); }
  }
}

canvas.addEventListener('pointerenter', event => {
  pointerPosition = {clientX: event.clientX, clientY: event.clientY};
  refreshHover();
});
canvas.addEventListener('pointermove', event => {
  pointerPosition = {clientX: event.clientX, clientY: event.clientY};
  if (!editor.document) return;
  const p = point(event);

  if (!gesture) { refreshHover(); return; }
  if (gesture.kind === 'pick') {
    gesture.end = p;
    return;
  }
  if (gesture.kind === 'marquee') {
    updateMarquee(gesture, p);
  } else if (gesture.kind === 'rotate') {
    gesture.shift = event.shiftKey;
    preview = {kind:'rotate', end:p}; previewSerial++;
    void refreshGesturePreview();
  } else if (gesture.kind === 'handle') {
    if (gesture.released) return;
    gesture.end = p; gesture.moved = true;
    preview = {kind: 'handle', end: p}; previewSerial++;
    void refreshGesturePreview();
  } else if (gesture.kind === 'move') {
    if (!selectionGestureMoved(gesture, p)) return;
    handleTarget = null;
    preview = {kind: 'move', end: p};
    previewSerial++;
    void refreshGesturePreview();
  } else if (['bond', 'arrow', 'line', 'shape', 'ts_bracket'].includes(gesture.kind)) {
    if (!pointInSheet(p, editor.info.sheet)) {
      cancelGesture();
      notice(ui.off_sheet_guidance, true);
      return;
    }
    gesture.dragged ||= Math.abs(event.clientX - gesture.pressX) + Math.abs(event.clientY - gesture.pressY) >= ui.drag_distance;
    gesture.shift = event.shiftKey;
    preview = {kind: gesture.kind === 'bond' ? 'line' : ['shape', 'ts_bracket'].includes(gesture.kind) ? gesture.kind : 'arrow', start: gesture.start, end: p};
    previewSerial++;
    void refreshGesturePreview();
  }
  render();
});

canvas.addEventListener('pointerup', event => {
  if (!gesture) return;
  const completed = gesture, p = point(event);
  if (completed.kind === 'pick') { completed.end = p; completed.released = true; return; }
  if (completed.kind === 'marquee') { updateMarquee(completed, p); completed.accepted = true; cancelGesture(); return; }
  if (completed.kind === 'rotate') {
    completed.shift = event.shiftKey;
    cancelGesture();
    if (editor.info.session === completed.session && editor.info.revision === completed.revision) void edit(rotationRequest(completed,p));
    return;
  }
  if (completed.kind === 'handle') { void finishHandle(completed); return; }
  if (completed.kind === 'move') { finishSelection(completed, p); return; }
  cancelGesture();
  if (completed.kind === 'shape') {
    void edit(shapeRequest(completed, p));
  } else if (completed.kind === 'ts_bracket') {
    // Native brackets commit on release; a click places the default size.
    void edit(bracketRequest(completed, p));
  } else if (completed.kind === 'arrow' || completed.kind === 'line') {
    completed.dragged ||= Math.abs(event.clientX - completed.pressX) + Math.abs(event.clientY - completed.pressY) >= ui.drag_distance;
    completed.shift = event.shiftKey;
    // Native clicks on existing items do not publish an arrow/line edit.
    // Keep the second click available for the label dialog.
    if (!completed.dragged && (completed.kind === 'arrow' || completed.hits.length)) return;
    void edit(arrowRequest(completed, p));
  } else if (completed.kind === 'bond') {
    void edit(bondRequest(completed, p));
  }
});
// Qt opens labels on the second press. Rendering can replace an SVG child
// before release, so the later browser dblclick event is not reliable here.
canvas.addEventListener('mousedown', async event => {
  if (smilesInsert || event.detail !== 2 || event.button !== 0 || !['select', 'arrow', 'line'].includes(tool) || editor.readOnly || editor.busy || loading
      || (ui.navigation.zoom_modifier === 'meta' && event.ctrlKey)) return;
  cancelGesture();
  const p = point(event);
  const hits = hitsAt(event.clientX, event.clientY);
  const session = editor.info.session, revision = editor.info.revision;
  loading = true; render();
  try {
    const result = await api('session', {session, revision, action: 'pick', ...p, hits,
      preferred: false, scale: viewScale()});
    if (result.target?.target !== 'arrow' || editor.info.revision !== revision) return;
    const id = result.target.id, original = editor.document.state.arrows[id].labels ?? {};
    const initial = {};
    for (const side of ['above', 'below']) {
      const field = $(`arrow-label-${side}`);
      field.value = original[side] ?? '';
      initial[side] = field.value;
    }
    const values = () => Object.fromEntries(['above', 'below'].map(side => [side,
      $(`arrow-label-${side}`).value === initial[side] ? original[side] ?? '' : $(`arrow-label-${side}`).value]));
    const dialog = $('arrow-label-dialog');
    let serial = 0;
    const update = async () => {
      const current = ++serial, labels = values();
      let over = false;
      for (const side of ['above', 'below']) {
        const count = Array.from(labels[side]).length;
        over ||= count > ui.arrow_labels.limit;
        $(`arrow-label-${side}-count`).textContent = `${count}/${ui.arrow_labels.limit} characters${count > ui.arrow_labels.limit ? ' — shorten before OK' : ''}`;
      }
      $('arrow-label-ok').disabled = over;
      try {
        const response = await api('session', {session, revision, action: 'label_preview', labels});
        if (serial !== current) return;
        for (const side of ['above', 'below']) {
          const element = $(`arrow-label-${side}-preview`);
          element.innerHTML = response.html[side] || 'No label';
          styleArrowLabel(element, {...ui.arrow_labels.preview, family: getComputedStyle(document.documentElement).fontFamily});
          element.style.background = ui.arrow_labels.preview.background;
        }
      } catch (error) { if (serial === current) notice(error.message, true); }
    };
    for (const side of ['above', 'below']) $(`arrow-label-${side}`).oninput = update;
    $('arrow-label-hint').textContent = ui.arrow_labels.hint;
    const closed = openDialog(dialog);
    $('arrow-label-above').focus();
    void update();
    const accepted = await closed === 'ok';
    serial++;
    const labels = values();
    loading = false;
    if (accepted) await edit({kind: 'arrow_labels', id, labels});
  } catch (error) { notice(error.message, true); }
  finally { loading = false; render(); canvas.focus(); }
});
$('arrow-label-cancel').onclick = () => $('arrow-label-dialog').close('cancel');
canvas.addEventListener('contextmenu', event => {
  event.preventDefault();
  if (editor.readOnly || editor.busy || loading || gesture || smilesInsert) return;
  const stack = document.elementsFromPoint(event.clientX,event.clientY)
    .filter(element => canvas.contains(element));
  if (stack.some(element => element.closest('[data-handle]'))) return;
  const mark = stack.map(element => element.closest('[data-item^="mark:"]')).find(Boolean);
  if (!mark) { void showBondMenu(event); return; }
  const id = Number(mark.dataset.item.split(':')[1]);
  const session = editor.info.session, revision = editor.info.revision;
  const menu = $('mark-menu');
  menu.hidden = false;
  menu.style.left = `${Math.min(event.clientX, innerWidth - menu.offsetWidth)}px`;
  menu.style.top = `${Math.min(event.clientY, innerHeight - menu.offsetHeight)}px`;
  $('reassign-mark').onclick = async () => {
    menu.hidden = true;
    if (editor.info.session !== session || editor.info.revision !== revision) return;
    const state = editor.document.state, owner = state.marks[id].atom_id;
    const atoms = state.model.atoms, field = $('mark-owner-atom');
    field.replaceChildren();
    if (owner === null) field.add(new Option('Free mark (unchanged)', ''));
    for (const [atomId, atom] of Object.entries(atoms).sort(([a],[b]) => Number(a)-Number(b))) {
      field.add(new Option(`${atom.element} #${atomId}  (${Number(atom.x).toFixed(2)}, ${Number(atom.y).toFixed(2)})${Number(atomId) === owner ? ' — current owner' : ''}`, atomId));
    }
    field.value = owner === null ? '' : String(owner);
    $('mark-owner-current').textContent = editor.info.drawing.mark_owners[id].text;
    const originalView = {...view};
    const highlight = () => {
      $('mark-candidate').replaceChildren();
      render();
      if (field.value === '') return;
      const rect = editor.info.drawing.mark_owner_rects[field.value];
      if (!rect) return;
      const [x,y,w,h] = rect;
      const scale = viewScale();
      const margin = 80/scale, left = view.x, top = view.y;
      // QGraphicsView ensureVisible rounds each requested scrollbar value.
      if (x <= left+margin) view.x = Math.trunc(x*scale-80-0.5)/scale;
      if (x+w >= left+view.width-margin) view.x = Math.trunc((x+w-view.width)*scale+80+0.5)/scale;
      if (y <= top+margin) view.y = Math.trunc(y*scale-80-0.5)/scale;
      if (y+h >= top+view.height-margin) view.y = Math.trunc((y+h-view.height)*scale+80+0.5)/scale;
      view = clampView(view, {width:canvas.clientWidth, height:canvas.clientHeight}, editor.info.drawing.scene_rect);
      canvas.setAttribute('viewBox', `${view.x} ${view.y} ${view.width} ${view.height}`);
      const ellipse = document.createElementNS('http://www.w3.org/2000/svg','ellipse');
      for (const [key,value] of Object.entries({cx:x+w/2,cy:y+h/2,rx:w/2+2,ry:h/2+2,fill:'none',stroke:'#a21caf','stroke-width':editor.info.drawing.selection_style.screen_width,'vector-effect':'non-scaling-stroke','pointer-events':'none'})) ellipse.setAttribute(key,String(value));
      $('mark-candidate').append(ellipse);
    };
    const dialog = $('mark-owner-dialog');
    loading = true;
    field.onchange = highlight;
    const closed = openDialog(dialog);
    highlight(); field.focus();
    const accepted = await closed === 'ok';
    $('mark-candidate').replaceChildren();
    view = originalView; loading = false;
    if (accepted && field.value !== '') await edit({kind:'mark_owner',id,atom_id:Number(field.value)});
    render(); canvas.focus();
  };
  $('reassign-mark').focus();
});
$('mark-owner-cancel').onclick = () => $('mark-owner-dialog').close('cancel');
// The desktop's double-bond position menu, for the bond the native context hit finds.
async function showBondMenu(event) {
  const session = editor.info.session, revision = editor.info.revision, generation = smilesGeneration;
  let menu;
  try {
    ({menu} = await api('session', {session, revision, action: 'bond_menu', ...point(event),
      hits: hitsAt(event.clientX, event.clientY), scale: viewScale()}));
  } catch (error) { notice(error.message, true); return; }
  if (!menu || generation !== smilesGeneration || smilesInsert || editor.info.session !== session || editor.info.revision !== revision || editor.busy || gesture) return;
  const element = $('bond-menu');
  element.replaceChildren(...menu.entries.map(entry => {
    const button = document.createElement('button');
    button.setAttribute('role', 'menuitemradio');
    button.setAttribute('aria-checked', String(entry.checked));
    button.textContent = entry.label;
    button.onclick = () => {
      element.hidden = true;
      if (editor.info.revision === revision && !entry.checked) void edit({kind: 'double_position', id: menu.bond, position: entry.position});
    };
    return button;
  }));
  element.hidden = false;
  element.style.left = `${Math.min(event.clientX, innerWidth - element.offsetWidth)}px`;
  element.style.top = `${Math.min(event.clientY, innerHeight - element.offsetHeight)}px`;
  element.querySelector('button')?.focus();
}
document.addEventListener('pointerdown', event => {
  for (const id of ['mark-menu', 'bond-menu']) if (!$(id).contains(event.target)) $(id).hidden = true;
});
document.addEventListener('keydown', event => { if (event.key === 'Escape') { $('mark-menu').hidden = true; $('bond-menu').hidden = true; } });

canvas.addEventListener('pointerleave', () => { pointerPosition = null; refreshHover(); });
canvas.addEventListener('pointercancel', cancelGesture);
canvas.addEventListener('lostpointercapture', () => { if (gesture && !(['pick', 'handle'].includes(gesture.kind) && gesture.released)) cancelGesture(); });
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  if (gesture || !ui || !editor.info) return;
  const rect = canvas.getBoundingClientRect();
  const deltaMode = event.deltaMode;
  view = wheelView(view, {width: canvas.clientWidth, height: canvas.clientHeight}, {
    deltaX: event.deltaX, deltaY: event.deltaY, deltaMode, ctrlKey: event.ctrlKey, metaKey: event.metaKey,
    position: {x: event.clientX - rect.left, y: event.clientY - rect.top},
  }, ui.navigation, measureLineHeight(getComputedStyle(canvas).font, 'M'));
  render(); refreshHover();
}, {passive: false});
window.addEventListener('blur', cancelGesture);
document.addEventListener('pointerdown', event => {
  const control = event.target.closest('button, summary');
  if (event.button !== 0 || !control || control.closest('dialog')) return;
  // Match native pointer focus policies without changing keyboard activation.
  event.preventDefault();
  if (control.closest('.menus, footer')) canvas.focus();
});


function setGrid(mode) {
  cancelGesture();
  if (mode !== 'none') grid.style = mode;
  grid.enabled = mode !== 'none';
  render();
}
$('grid-mode').onclick = () => setGrid(ui.grid.modes[(ui.grid.modes.indexOf(gridMode())+1)%ui.grid.modes.length]);
$('grid-toggle').onclick = () => setGrid(grid.enabled ? 'none' : grid.style);
// View > Valence Checking: the desktop's per-canvas view switch, on for each
// opened drawing. Its ids come only from the accepted drawing, placed where the
// canvas shows those atoms, so a move preview carries them while a drawing
// preview adds none until it is accepted. It changes no document or history.
function valenceFeedback() {
  if (!valenceChecking) return '';
  return valenceWarningMarkup(previewInfo?.document ?? editor.document, editor.info.drawing.valence_warnings, previewInfo?.drawing ?? editor.info.drawing, ui.valence_warning, viewScale(), visibleSceneRect());
}
$('valence-toggle').onclick = () => { valenceChecking = !valenceChecking; render(); };

function updateSheetFields() {
  const custom = $('sheet-size').value === ui.sheet_setup.custom;
  $('sheet-orientation').disabled = custom;
  for (const axis of ['width','height']) $(`sheet-${axis}`).disabled = !custom;
  document.querySelectorAll('[data-sheet-step]').forEach(button => { button.disabled = !custom; });
  if (!custom) {
    let [width,height] = ui.sheet_setup.dimensions[$('sheet-size').value];
    if ($('sheet-orientation').value === 'landscape') [width,height] = [height,width];
    $('sheet-width').value = width.toFixed(ui.sheet_setup.decimals);
    $('sheet-height').value = height.toFixed(ui.sheet_setup.decimals);
  }
}

function stepSheetDimension(input, direction) {
  if (input.disabled) return;
  const spec = ui.sheet_setup, value = Number(input.value);
  input.value = Math.max(spec.minimum,Math.min(spec.maximum,value+direction*spec.step)).toFixed(spec.decimals);
}

$('sheet-setup').onclick = async () => {
  if (loading || editor.busy || editor.readOnly) return;
  cancelGesture(); loading = true; render();
  const settings = editor.document.state.settings, dialog = $('sheet-dialog');
  $('sheet-size').value = settings.sheet_size;
  $('sheet-orientation').value = settings.sheet_orientation;
  if (settings.sheet_custom_size_mm) {
    const [width,height] = settings.sheet_custom_size_mm;
    $('sheet-width').value = width.toFixed(ui.sheet_setup.decimals);
    $('sheet-height').value = height.toFixed(ui.sheet_setup.decimals);
  }
  updateSheetFields();
  const closed = openDialog(dialog);
  $('sheet-size').focus();
  const accepted = await closed === 'ok';
  loading = false;
  if (accepted) await edit({kind:'sheet_setup',size:$('sheet-size').value,orientation:$('sheet-orientation').value,custom_size_mm:$('sheet-size').value === ui.sheet_setup.custom ? ['width','height'].map(axis=>Number(Number($(`sheet-${axis}`).value).toFixed(ui.sheet_setup.decimals))) : null});
  render(); canvas.focus();
};
$('sheet-size').onchange = $('sheet-orientation').onchange = updateSheetFields;
$('sheet-cancel').onclick = () => $('sheet-dialog').close('cancel');

let canvasCount = 0;
const newCanvasName = () => ui.canvas_name.replace('{}', ++canvasCount);
// Like a new desktop canvas, continue the active drawing's settings.
$('new').onclick = () => {
  if (!mayReplace()) return;
  const current = editor.document?.state.settings;
  void loadDocument(api('new').then(info => {
    for (const key of ui.new_canvas_settings) {
      if (current && key in current) info.document.state.settings[key] = current[key];
      else if (current) delete info.document.state.settings[key];
    }
    return info;
  }), newCanvasName());
};
$('open').onclick = () => { if (mayReplace()) $('file').click(); };
$('file').onchange = async () => {
  const file = $('file').files[0];
  $('file').value = '';
  if (!file) return;
  if (file.size > ui.max_document_bytes) { notice(`The browser adapter opens files up to ${ui.max_document_bytes / 1048576} MiB.`, true); return; }
  await loadDocument(file.text().then(text => api('open', text)), file.name);
};
// File > Save copy: the session's document, as a download. An open note is
// committed first, as leaving it would, and a note that was not saved stops the
// copy; one copy runs at a time, and a reply for a document since replaced,
// renamed, edited or busy is not its copy.
let savingCopy = false;
$('save').onclick = async () => {
  if (savingCopy || !editor.document || editor.busy || loading) return;
  savingCopy = true;
  try {
    if (await finishNoteEdit() === false) return;
    if (!editor.document || editor.busy || loading) return;
    const {session, revision} = editor.info, name = editor.name;
    const current = () => !editor.busy && !loading && editor.info?.session === session && editor.info?.revision === revision && editor.name === name;
    // The session holds embedded images; the browser's copy carries references.
    try {
      const {document} = await api('session', {session, revision, action: 'export'});
      if (current()) {
        download(JSON.stringify(document, null, 2) + '\n', name.replace(/\.chemvas$/i, '') + '-web-copy.chemvas', 'application/json');
        notice('Save copy requested. Check your downloads before closing; the original file has not changed.');
      }
    } catch (error) { if (current()) notice(error.message, true); }
  } finally { savingCopy = false; }
};
// File > Export Figure: the whole canvas as the desktop's plain SVG figure, as a
// download. Like Export MOL, an open note is committed first and a note that was
// not saved stops the export; one export runs at a time, a reply for a document
// since replaced, renamed, edited or busy is not its figure, and a download
// clears only the export's own refusal while that is still the notice shown.
let exportingFigure = false, figureRefusal = null;
$('export-figure').onclick = async () => {
  if (exportingFigure || !editor.document || editor.busy || loading) return;
  exportingFigure = true;
  try {
    if (await finishNoteEdit() === false) return;
    if (!editor.document || editor.busy || loading) return;
    const {session, revision} = editor.info, name = editor.name;
    const current = () => !editor.busy && !loading && editor.info?.session === session && editor.info?.revision === revision && editor.name === name;
    try {
      const {svg} = await api('session', {session, revision, action: 'export_figure', format: 'svg', scope: 'sheet'});
      if (current()) {
        download(svg, name.replace(/\.chemvas$/i, '') + '.svg', 'image/svg+xml');
        if (figureRefusal === noticeSerial) notice();
        figureRefusal = null;
      }
    } catch (error) { if (current()) { notice(error.message, true); figureRefusal = noticeSerial; } }
  } finally { exportingFigure = false; }
};
// File > Export MOL: the desktop's selected-only Molfile, as a download. An open
// note is committed first, as leaving it would, and a note that was not saved
// stops the export; one export runs at a time, and a reply for a document since
// replaced, renamed, edited or busy is not its MOL. A download clears only the
// export's own refusal, and only while that is still the notice shown.
let exportingMol = false, molRefusal = null;
$('export-mol').onclick = async () => {
  if (exportingMol || !editor.document || editor.busy || loading) return;
  exportingMol = true;
  try {
    if (await finishNoteEdit() === false) return;
    if (!editor.document || editor.busy || loading) return;
    const {session, revision} = editor.info, name = editor.name;
    const current = () => !editor.busy && !loading && editor.info?.session === session && editor.info?.revision === revision && editor.name === name;
    try {
      const {molfile} = await api('session', {session, revision, action: 'export_mol', selection: selectedItems()});
      if (current()) {
        download(molfile, name.replace(/\.chemvas$/i, '') + '.mol', 'chemical/x-mdl-molfile');
        if (molRefusal === noticeSerial) notice();
        molRefusal = null;
      }
    } catch (error) { if (current()) { notice(error.message, true); molRefusal = noticeSerial; } }
  } finally { exportingMol = false; }
};
for (const action of ['undo', 'redo']) $(action).onclick = async () => {
  cancelGesture(); const pending = editor[action](); render();
  try { await pending; selection = new Set(); } catch (error) { notice(error.message, true); } finally { render(); refreshHover(); }
};
$('delete').onclick = () => void deleteSelection();
$('select-all').onclick = selectAll;
// The menu reads the clipboard through the browser's permission prompt; the
// keyboard's paste event needs none.
$('copy').onclick = () => void copyChemistry(false);
$('cut').onclick = () => void copyChemistry(true);
$('paste').onclick = () => void pasteFromMenu();
$('recover').onclick = () => void showRecovery();
// The scene area the canvas shows, for the desktop's image placement.
function visibleSceneRect() {
  const box = canvas.getBoundingClientRect(), matrix = canvas.getScreenCTM()?.inverse();
  if (!matrix) return [view.x, view.y, view.width, view.height];
  const corner = (x, y) => new DOMPoint(x, y).matrixTransform(matrix);
  const a = corner(box.left, box.top), b = corner(box.right, box.bottom);
  return [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y)];
}
function base64Bytes(buffer) {
  const bytes = new Uint8Array(buffer), chunks = [];
  for (let start = 0; start < bytes.length; start += 0x8000) chunks.push(String.fromCharCode(...bytes.subarray(start, start + 0x8000)));
  return btoa(chunks.join(''));
}
$('insert-image').onclick = () => { if (!editor.readOnly) $('image-file').click(); };
$('image-file').onchange = async event => {
  const [file] = event.target.files;
  event.target.value = '';
  if (!file) return;
  if (file.size > ui.max_image_bytes) { notice(`The image exceeds the ${ui.max_image_bytes / 1048576} MiB limit.`, true); return; }
  const data = base64Bytes(await file.arrayBuffer());
  if (await edit({kind: 'insert_image', data_base64: data, view: visibleSceneRect()})) {
    // The desktop selects the new image and returns to Select.
    setTool('select');
    selection = new Set([`image:${editor.document.state.images.length - 1}`]);
    render();
  }
};
$('image-properties').onclick = async () => {
  const spec = ui.image_properties, images = editor.document?.state.images ?? [];
  const selected = images.flatMap((_, id) => selection.has(`image:${id}`) ? [id] : []);
  if (!selected.length) { notice(spec.none_selected); return; }
  const dialog = $('image-dialog'), choice = $('image-choice'), round = (value, digits) => Number(value.toFixed(digits));
  $('image-title').textContent = spec.title;
  $('image-choice-label').textContent = spec.choose;
  $('image-choice-row').hidden = selected.length < 2;
  choice.replaceChildren(...selected.map((id, index) => {
    const image = images[id];
    const format = spec.choice.replace('{index}', index + 1).replace('{width}', image.pixel_width).replace('{height}', image.pixel_height).replace('{x:g}', image.x).replace('{y:g}', image.y);
    return new Option(format, String(id));
  }));
  $('image-lock-label').textContent = spec.lock_aspect;
  $('image-opacity-label').textContent = spec.opacity;
  $('image-opacity-suffix').textContent = spec.opacity_suffix;
  const fields = $('image-fields');
  fields.replaceChildren(...spec.fields.map(([key, label]) => {
    const row = document.createElement('label'), input = document.createElement('input');
    input.type = 'number'; input.id = `image-${key}`; input.step = String(10 ** -spec.decimals);
    input.min = String(['width', 'height'].includes(key) ? spec.size_minimum : spec.coordinate_minimum); input.max = String(spec.maximum);
    row.append(spec.field_label.replace('{label}', label), input);
    return row;
  }));
  let initial = {};
  const fill = () => {
    const image = images[Number(choice.value)];
    $('image-original').textContent = spec.original.replace('{width}', image.pixel_width).replace('{height}', image.pixel_height);
    initial = Object.fromEntries(spec.fields.map(([key]) => [key, round(image[key], spec.decimals)]));
    for (const [key, value] of Object.entries(initial)) $(`image-${key}`).value = value;
    $('image-lock').checked = image.lock_aspect;
    $('image-opacity').value = round(image.opacity * 100, spec.opacity_decimals);
  };
  // The desktop's aspect lock: width drives height through the pixel ratio.
  const sync = changed => {
    const image = images[Number(choice.value)];
    if (!$('image-lock').checked) return;
    const ratio = image.pixel_width / image.pixel_height, value = Number($(`image-${changed}`).value);
    if (changed === 'width') $('image-height').value = round(value / ratio, spec.decimals);
    else $('image-width').value = round(value * ratio, spec.decimals);
  };
  choice.onchange = fill;
  $('image-width').oninput = () => sync('width');
  $('image-height').oninput = () => sync('height');
  $('image-lock').onchange = () => { if ($('image-lock').checked) sync('width'); };
  fill();
  if (await openDialog(dialog) !== 'ok') return;
  const image = images[Number(choice.value)], changes = {lock_aspect: $('image-lock').checked};
  // Accepting unchanged fields is an exact no-op despite display rounding.
  for (const [key] of spec.fields) {
    const value = Number($(`image-${key}`).value);
    if (value !== initial[key]) changes[key] = value;
  }
  const opacity = Number($('image-opacity').value);
  if (opacity !== round(image.opacity * 100, spec.opacity_decimals)) changes.opacity = opacity / 100;
  void edit({kind: 'image_properties', id: Number(choice.value), changes});
};
$('image-cancel').onclick = () => $('image-dialog').close('cancel');
for (const [id, kind] of [['group', 'group'], ['ungroup', 'ungroup']]) {
  $(id).onclick = async () => {
    if (!selection.size) return;
    if (await edit({kind, selection: selectedItems()})) { selection = expandToGroups(selection, groupUnits()); render(); }
  };
}
for (const [id,horizontal] of [['flip-horizontal',true],['flip-vertical',false]]) $(id).onclick = () => void edit({kind:'flip',selection:selectedItems(),horizontal});
$('rotate-menu').onclick = () => { setTool('select'); $('rotate-angle').focus(); $('rotate-angle').select(); };
$('rotate-up').onclick = () => $('rotate-angle').stepUp();
$('rotate-down').onclick = () => $('rotate-angle').stepDown();
function rotateSelected() {
  const input = $('rotate-angle');
  if (input.value && input.reportValidity()) void edit({kind:'rotate',selection:selectedItems(),value:Number(input.value)});
}
$('rotate-apply').onclick = rotateSelected;
$('rotate-angle').onkeydown = event => { if(event.key === 'Enter') { event.preventDefault(); rotateSelected(); } };
$('bring-front').onclick = () => void edit({kind: 'stack', selection: selectedItems(), front: true});
$('send-back').onclick = () => void edit({kind: 'stack', selection: selectedItems(), front: false});
$('zoom-in').onclick = () => zoom(1 / ui.navigation.step);
$('zoom-out').onclick = () => zoom(ui.navigation.step);
$('fit').onclick = fitPage;
$('fit-menu').onclick = fitPage;
$('actual-size').onclick = $('zoom-level').onclick = actualSize;
$('zoom-in-menu').onclick = () => zoom(1 / ui.navigation.step);
$('zoom-out-menu').onclick = () => zoom(ui.navigation.step);
$('save-as').onclick = () => $('save').click();
$('more-colors').onclick = () => { $('custom-color').value = paintColor ?? '#000000'; $('custom-color').click(); };
$('custom-color').onchange = () => chooseColor($('custom-color').value);
$('ring-more-colors').onclick = () => { $('custom-ring-color').value = ringFillColor; $('custom-ring-color').click(); };
$('custom-ring-color').onchange = () => chooseRingFill($('custom-ring-color').value);
// The desktop field commits a changed positive value and restores anything else.
function commitBondLength(value) {
  const field = $('bond-length'), current = editor.document?.state.settings.bond_length_px;
  const rounded = Number(value.toFixed(ui.bond_length_input.decimals));
  if (!Number.isFinite(rounded) || rounded <= 0 || rounded > ui.bond_length_input.max || rounded === current) { field.value = current; return; }
  void edit({kind: 'bond_length', value: rounded});
}
$('bond-length').onchange = () => commitBondLength(Number($('bond-length').value));
$('bond-length-up').onclick = () => commitBondLength(Number($('bond-length').value) + ui.bond_length_input.step);
$('bond-length-down').onclick = () => commitBondLength(Number($('bond-length').value) - ui.bond_length_input.step);
$('atom-label-cancel').onclick = () => $('atom-dialog').close('cancel');
$('help').onclick = () => $('help-dialog').showModal();
$('close-help').onclick = () => $('help-dialog').close();
window.addEventListener('beforeunload', event => { if (editor.dirty || editor.busy || pendingNoteChanges()) { event.preventDefault(); event.returnValue = ''; } });
document.addEventListener('keydown', event => {
  if (event.isComposing || document.querySelector('dialog[open]')) return;
  const popup = document.querySelector('.arrow-popup[open], #grid-options[open]');
  if (event.key === 'Escape' && popup) { event.preventDefault(); popup.open = false; canvas.focus(); return; }
  if (event.target.matches('input, textarea, select')) return;
  // The note editor owns its keys; Escape ends it like the desktop Text tool.
  if (noteEditorElement.contains(event.target) && event.key !== 'Escape') return;
  // Focused controls own activation, even while the pointer stays over the canvas.
  if (['Enter', ' '].includes(event.key) && event.target.closest('button, summary, a[href]')) return;
  if (event.key === 'Escape') { event.preventDefault(); setTool('select'); return; }
  const queuedCharge = chargeEdits && !event.ctrlKey && !event.metaKey && !event.altKey && ['+','-'].includes(event.key);
  if ((editor.busy || loading) && !queuedCharge) return;
  const key = event.key.toLowerCase(), command = event.ctrlKey || event.metaKey;
  // Copy and Cut start here, inside the key gesture; Paste arrives as the
  // browser's paste event, the only way to read the clipboard without asking.
  if (command && !event.altKey && !event.shiftKey && ['c', 'x'].includes(key) && selection.size && canvasOwnsClipboard(event.target)) {
    event.preventDefault(); void copyChemistry(key === 'x');
  }
  else if (command && key === 'a') { event.preventDefault(); selectAll(); }
  else if (command && event.shiftKey && !event.altKey && ['h','v'].includes(key)) { event.preventDefault(); if (!editor.readOnly) $(key === 'h' ? 'flip-horizontal' : 'flip-vertical').click(); }
  else if (command && key === 'n') { event.preventDefault(); $('new').click(); }
  else if (command && key === 'g' && !event.altKey) { event.preventDefault(); if (!editor.readOnly) $(event.shiftKey ? 'ungroup' : 'group').click(); }
  // The desktop's view keys: Control with a zoom key, or a bare function key.
  else if ((command && ui.navigation.zoom_keys[event.key]) || (!command && !event.shiftKey && !event.altKey && ui.navigation.function_keys[event.key])) {
    event.preventDefault();
    const action = command ? ui.navigation.zoom_keys[event.key] : ui.navigation.function_keys[event.key];
    $({actual_size: 'actual-size', fit: 'fit', zoom_in: 'zoom-in', zoom_out: 'zoom-out'}[action]).click();
  }
  else if (command && key === 'z') { event.preventDefault(); $(event.shiftKey ? 'redo' : 'undo').click(); }
  // Qt's standard Redo is also Ctrl+Y where Control is the command key.
  else if (command && key === 'y' && ui.navigation.zoom_modifier === 'control') { event.preventDefault(); $('redo').click(); }
  // Selection keys: Alt+arrow turns, Shift+arrow moves by the desktop's steps.
  else if (event.key.startsWith('Arrow') && !command && (event.altKey !== event.shiftKey)) {
    const name = event.key.slice('Arrow'.length);
    event.preventDefault();
    if (editor.readOnly || !selection.size) return;
    if (event.altKey) void edit({kind: 'rotate', value: ui.navigation.rotate_keys[name], selection: selectedItems()});
    else {
      const [dx, dy] = ui.navigation.nudge_keys[name];
      void edit({kind: 'move', selection: selectedItems(), dx, dy});
    }
  }
  else if (command && key === 's') { event.preventDefault(); $('save').click(); }
  else if (command && key === 'o') { event.preventDefault(); $('open').click(); }
  else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); if (!editor.readOnly) void deleteSelection(true); }
  else if (event.key === 'Enter' && !command && !event.altKey && !editor.readOnly && pointerPosition) {
    event.preventDefault(); cancelGesture();
    const {hits, scale, ...target} = hoverPoint();
    void atomInput({kind: 'atom_prompt', ...target});
  }
  else if (!command && !event.altKey) {
    const text = event.shiftKey ? event.key.toUpperCase() : key;
    if (pointerPosition && !editor.readOnly && ui.hover_shortcuts.includes(text)) {
      event.preventDefault();
      cancelGesture();
      const apply = ['+','-'].includes(text) ? queueChargeEdit : edit;
      void apply({kind: 'hover_shortcut', ...hoverPoint(), key: text}).then(ok => {
        const tool = editor.info.shortcut_tool;
        if (ok && tool) switchByHotkey(tool, event.shiftKey ? ui.shift_tool_hotkeys[text] : null);
      });
      return;
    }
    // Qt Shift+T/G/E: switch tool and reset its kind, after hover shortcuts.
    const shifted = event.shiftKey ? ui.shift_tool_hotkeys[event.key.toUpperCase()] : null;
    if (shifted && !editor.readOnly) {
      event.preventDefault();
      switchByHotkey(shifted.tool, shifted);
      return;
    }
    const next = ui.tool_hotkeys[key];
    if (next && !event.shiftKey && (!editor.readOnly || next === 'select')) {
      event.preventDefault();
      switchByHotkey(next, null);
    }
  }
});
new ResizeObserver(() => render()).observe(canvas);
try { ui = await api('ui'); buildControls(); await loadDocument(api('new'), newCanvasName()); void offerRecovery(); } catch (error) { notice(error.message, true); }


function actualSize() {
  if (!editor.info) return;
  view = {x: -canvas.clientWidth / 2, y: -canvas.clientHeight / 2, width: canvas.clientWidth, height: canvas.clientHeight};
  render();
  // As zoom() does: a held move asks again for the view now shown.
  if (gesture?.kind === 'move' && preview && !gesture.released && pointerPosition) {
    preview = {kind: 'move', end: point(pointerPosition)}; previewSerial++;
    void refreshGesturePreview();
  }
}

function chooseRingFill(value) {
  ringFillColor = value;
  void edit({kind: 'ring_fill', color: value, selection: selectedItems()});
}

function chooseColor(value) {
  paintColor = value;
  setTool('color');
  if (selection.size) void edit({kind: 'color', color: value, selection: selectedItems()});
}

function buildControls() {
  $('smiles-label').textContent = ui.smiles.label;
  $('smiles-input').placeholder = ui.smiles.placeholder;
  $('smiles-input').title = ui.smiles.tooltip;
  $('smiles-input').maxLength = ui.smiles.maximum_length;
  $('smiles-insert').textContent = ui.smiles.button_label;
  $('smiles-insert').title = ui.smiles.button_tooltip;
  $('grid-mode').title = $('grid-options').title = ui.grid.hint;
  for (const mode of ui.grid.modes) {
    const button = document.createElement('button'); button.dataset.grid = mode; button.dataset.idle = '';
    button.textContent = mode[0].toUpperCase()+mode.slice(1); button.setAttribute('role','menuitemradio');
    button.onclick = () => { setGrid(mode); $('grid-options').open = false; };
    $('grid-menu').append(button);
  }
  $('grid-menu').append(document.createElement('hr'));
  for (const percent of ui.grid.strengths) {
    const button = document.createElement('button'); button.dataset.gridStrength = percent; button.dataset.idle = '';
    button.textContent = `Strength ${percent}%`; button.setAttribute('role','menuitemradio');
    button.onclick = () => { grid.opacity = percent/100; $('grid-options').open = false; render(); };
    $('grid-menu').append(button);
  }
  const sheet = ui.sheet_setup;
  for (const [key,text] of Object.entries(sheet.text)) $(['title','explanation'].includes(key) ? `sheet-${key}` : `sheet-${key}-label`).textContent = text;
  $('sheet-dialog').setAttribute('aria-label',sheet.text.title);
  for (const size of sheet.sizes) $('sheet-size').add(new Option(size,size));
  for (const [value,label] of sheet.orientations) $('sheet-orientation').add(new Option(label,value));
  for (const axis of ['width','height']) {
    const input = $(`sheet-${axis}`); input.min = sheet.minimum; input.max = sheet.maximum;
    input.onchange = () => { if (input.value && input.checkValidity()) input.value = Number(input.value).toFixed(sheet.decimals); };
    input.onkeydown = event => { if (['ArrowUp','ArrowDown'].includes(event.key)) { event.preventDefault(); stepSheetDimension(input,event.key === 'ArrowUp' ? 1 : -1); } };
  }
  document.querySelectorAll('[data-sheet-step]').forEach(button => {
    const [axis,direction] = button.dataset.sheetStep.split(':');
    button.onclick = () => stepSheetDimension($(`sheet-${axis}`),Number(direction));
  });
  for (const [kind,actions] of Object.entries(ui.arrange_actions)) {
    for (const action of actions) {
      for (const surface of ['menu','options']) {
        const button = document.createElement('button');
        button.dataset.editable = ''; button.title = action.tip;
        button.setAttribute('aria-label',surface === 'menu' ? action.label : action.tip);
        if (surface === 'menu') button.textContent = action.label; else button.innerHTML = action.icon;
        button.onclick = () => void edit({kind,selection:selectedItems(),mode:action.mode});
        $(`${kind}-${surface}`).append(button);
      }
    }
  }
  // Each page's caption is the desktop's.
  document.querySelectorAll('[data-context] > .caption').forEach(caption => { caption.textContent = ui.context_captions[caption.parentElement.dataset.context] ?? ''; });
  // The desktop Text page: size steps, then format groups between dividers.
  const textFormat = $('text-format');
  for (const size of ui.text_format.sizes) textFormat.append(textFormatButton(size, {delta: size.delta}));
  for (const group of ui.text_format.groups) {
    const divider = document.createElement('span'); divider.className = 'context-divider'; textFormat.append(divider);
    for (const action of group) textFormat.append(textFormatButton(action, {key: action.key}, true));
  }
  for (const action of ui.flip_actions) {
    const button = document.createElement('button');
    button.innerHTML = action.icon; button.title = `${action.label} (${action.shortcut.replace('Ctrl','⌘/Ctrl')})`;
    button.setAttribute('aria-label',action.label); button.dataset.editable = '';
    button.onclick = () => void edit({kind:'flip',selection:selectedItems(),horizontal:action.horizontal});
    $('flip-options').append(button);
  }
  $('rotate-angle').min = ui.rotation.minimum;
  $('rotate-angle').max = ui.rotation.maximum;
  $('rotate-angle').value = ui.rotation.default;
  const lengthField = $('bond-length'), lengthSpec = ui.bond_length_input;
  lengthField.step = lengthSpec.step; lengthField.max = lengthSpec.max; lengthField.title = lengthSpec.tooltip;
  $('bond-length-up').title = lengthSpec.up_tooltip; $('bond-length-down').title = lengthSpec.down_tooltip;
  const atomInput = $('atom-symbol');
  atomInput.value = ui.atom_input.value;
  atomInput.placeholder = ui.atom_input.placeholder;
  atomInput.title = ui.atom_input.tooltip;
  atomInput.maxLength = $('atom-label').maxLength = ui.atom_input.max_length;
  atomInput.style.minWidth = `${ui.atom_input.min_width}px`;
  atomInput.style.maxWidth = `${ui.atom_input.max_width}px`;
  // Existing desktop declarations drive order, naming and artwork. This is a DOM adapter.
  function button(spec) {
    const element = document.createElement('button');
    element.title = spec.tip ?? spec.label;
    element.setAttribute('aria-label', spec.label);
    element.innerHTML = spec.icon;
    return element;
  }
  for (const entries of ui.groups) {
    const group = document.createElement('div');
    group.className = 'tool-group';
    for (const spec of entries) {
      const element = button(spec);
      element.dataset.tool = spec.key;
      element.onclick = () => {
        // A toolbar click resets Bond and Mark to their defaults, as on the desktop.
        if (spec.key === 'bond') bondStyle = ui.tool_defaults.bond;
        if (spec.key === 'mark') markKind = ui.tool_defaults.mark;
        setTool(spec.key);
      };
      group.append(element);
    }
    $('tools').append(group);
  }
  const spacer = document.createElement('span'); spacer.className = 'spacer'; $('tools').append(spacer);
  for (const spec of ui.panels) { const element = button(spec); element.disabled = true; $('tools').append(element); }
  for (const entries of ui.bond_groups) {
    const group = document.createElement('div'); group.className = 'segments';
    for (const spec of entries) {
      const element = button(spec);
      element.dataset.bond = spec.key;
      element.dataset.editable = '';
      element.onclick = () => { bondStyle = spec.key; render(); };
      group.append(element);
    }
    $('bond-options').append(group);
  }
  for (const mode of ['color', 'ring-fill']) {
    for (const spec of ui.color_palette) {
      const element = document.createElement('button');
      const prefix = mode === 'color' ? 'Color' : 'Ring Fill';
      element.className = 'color-swatch'; element.title = `${prefix}: ${spec.label}`;
      element.setAttribute('aria-label', spec.label);
      if (mode === 'color') element.dataset.color = spec.color;
      element.dataset.editable = ''; element.style.setProperty('--swatch-color', spec.color);
      element.onclick = () => mode === 'color' ? chooseColor(spec.color) : chooseRingFill(spec.color);
      $(`${mode}-options`).append(element);
    }
  }
  for (const spec of ui.line_options) {
    const element = button(spec); element.dataset.line = spec.key; element.dataset.editable = '';
    element.onclick = () => { lineStyle = spec.key; render(); };
    $('line-options').append(element);
  }
  bracketKind = ui.default_bracket_kind;
  ({bond: bondStyle, mark: markKind, orbital: orbitalKind, line: lineStyle, shape: shapeStyle, stroke: shapeStroke} = ui.tool_defaults);
  arrowStyle = ui.default_arrow_style;
  ringTemplate = ui.templates[0];
  for (const spec of ui.bracket_options) {
    const element = button(spec); element.dataset.bracketKind = spec.key; element.dataset.editable = '';
    element.onclick = () => { bracketKind = spec.key; render(); };
    $('bracket-options').append(element);
  }
  for (const spec of ui.orbital_options) {
    const element = button(spec); element.dataset.orbitalKind = spec.key; element.dataset.editable = '';
    if (spec.text) { element.textContent = spec.text; element.style.width = '40px'; }
    element.onclick = () => { orbitalKind = spec.key; render(); };
    $('orbital-options').append(element);
  }
  for (const spec of ui.orbital_phases) {
    const element = button(spec); element.dataset.orbitalPhase = String(spec.key); element.dataset.editable = '';
    element.onclick = () => void edit({kind:'orbital_phase',enabled:spec.key});
    $('orbital-phases').append(element);
  }
  for (const spec of ui.mark_options) {
    const element = button(spec); element.dataset.markKind = spec.key; element.dataset.editable = '';
    element.onclick = () => { markKind = spec.key; markHover.result = null; render(); refreshHover(); };
    $('mark-options').append(element);
  }
  for (const [specs, attribute] of [[ui.shape_options, 'shape'], [ui.shape_strokes, 'stroke']]) {
    const group = document.createElement('div'); group.className = 'segments';
    for (const spec of specs) {
      const element = button(spec); element.dataset[attribute] = spec.key; element.dataset.editable = '';
      element.onclick = () => { if (attribute === 'shape') shapeStyle = spec.key; else shapeStroke = spec.key; render(); };
      group.append(element);
    }
    $('shape-options').append(group);
  }
  const arrows = document.createElement('div'); arrows.className = 'segments';
  const more = document.createElement('details'); more.id = 'arrow-more'; more.className = 'arrow-popup';
  const summary = document.createElement('summary'); summary.title = 'More arrows'; summary.setAttribute('aria-label', 'More arrows');
  const menu = document.createElement('div'); menu.className = 'menu';
  more.append(summary, menu);
  for (const spec of ui.arrow_options) {
    const element = button(spec); element.dataset.arrow = spec.key; element.dataset.editable = '';
    element.onclick = () => {
      arrowStyle = spec.key;
      if (spec.more) { summary.innerHTML = spec.icon; summary.dataset.arrow = spec.key; more.open = false; }
      render();
    };
    if (spec.more) {
      const label = document.createElement('span'); label.textContent = spec.label; element.append(label); menu.append(element);
      if (!summary.dataset.arrow) { summary.innerHTML = spec.icon; summary.dataset.arrow = spec.key; }
    } else arrows.append(element);
  }
  more.addEventListener('toggle', () => {
    if (more.open) { const rect = summary.getBoundingClientRect(); menu.style.left = `${Math.max(0, Math.min(rect.left, innerWidth - 240))}px`; menu.style.top = `${rect.bottom}px`; }
  });
  $('arrow-options').append(arrows, more);
  for (const [index, spec] of ui.arrow_style_controls.entries()) {
    if (index === 0 || (spec.setting && ui.arrow_style_controls[index - 1].preset)) {
      const divider = document.createElement('span'); divider.className = 'context-divider'; $('arrow-options').append(divider);
    }
    if (spec.preset) {
      const element = button(spec); element.dataset.editable = '';
      element.onclick = () => void edit({kind: 'arrow_style', preset: spec.preset});
      $('arrow-options').append(element);
    } else {
      const popup = document.createElement('details'); popup.className = 'arrow-popup arrow-slider';
      const trigger = document.createElement('summary'); trigger.title = spec.label; trigger.setAttribute('aria-label', spec.label); trigger.innerHTML = spec.icon;
      const panel = document.createElement('div'); panel.className = 'menu';
      const slider = document.createElement('input'); slider.type = 'range'; slider.min = spec.minimum; slider.max = spec.maximum; slider.step = 1;
      slider.dataset.setting = spec.setting; slider.dataset.factor = spec.factor; slider.dataset.minimum = spec.minimum; slider.dataset.maximum = spec.maximum; slider.dataset.editable = ''; slider.setAttribute('aria-label', spec.label);
      slider.onchange = async () => {
        const focused = document.activeElement === slider;
        await edit({kind: 'arrow_style', setting: spec.setting, value: Number(slider.value)});
        if (focused && popup.open && document.activeElement === document.body) slider.focus();
      };
      const stepSlider = delta => {
        slider.value = Math.max(Number(slider.min), Math.min(Number(slider.max), Number(slider.value) + delta));
        void slider.onchange();
      };
      slider.onkeydown = event => {
        if (event.key === 'PageUp' || event.key === 'PageDown') { event.preventDefault(); stepSlider(event.key === 'PageUp' ? spec.page_step : -spec.page_step); }
      };
      slider.onpointerdown = event => {
        if (event.button !== 0) return;
        const rect = slider.getBoundingClientRect();
        const thumb = rect.left + 6 + (rect.width - 12) * (Number(slider.value) - Number(slider.min)) / (Number(slider.max) - Number(slider.min));
        if (Math.abs(event.clientX - thumb) > 6) {
          event.preventDefault(); slider.focus(); stepSlider(event.clientX > thumb ? spec.page_step : -spec.page_step);
        }
      };
      panel.append(slider); popup.append(trigger, panel); $('arrow-options').append(popup);
      popup.addEventListener('toggle', () => {
        if (popup.open) { const rect = trigger.getBoundingClientRect(); panel.style.left = `${Math.max(0, Math.min(rect.left, innerWidth - 138))}px`; panel.style.top = `${rect.bottom}px`; }
      });
    }
  }
  // The desktop Ring page: one button per template; the session starts on benzene.
  for (const template of ui.templates) {
    const element = button({key: template.label, label: template.label, icon: template.icon});
    element.dataset.template = `${template.size}:${template.style}`; element.dataset.editable = '';
    element.onclick = () => { ringTemplate = template; render(); };
    $('ring-options').append(element);
  }
  document.querySelectorAll('.menus details, .arrow-popup, #grid-options').forEach(menu => {
    menu.addEventListener('toggle', () => {
      if (!menu.open) return;
      document.querySelectorAll('.menus details, .arrow-popup, #grid-options').forEach(other => { if (other !== menu && !other.contains(menu) && !menu.contains(other)) other.open = false; });
      if (menu.classList.contains('submenu')) {
        const rect = menu.querySelector('summary').getBoundingClientRect(), popup = menu.querySelector('.menu');
        popup.style.left = `${Math.min(rect.right,innerWidth-popup.offsetWidth)}px`;
        popup.style.top = `${Math.min(rect.top,innerHeight-popup.offsetHeight)}px`;
      }
    });
    menu.querySelectorAll('button').forEach(item => item.addEventListener('click', () => { menu.open = false; }));
  });
  document.addEventListener('pointerdown', event => { if (!event.target.closest('.menus, .arrow-popup, .grid-control')) document.querySelectorAll('.menus details, .arrow-popup, #grid-options').forEach(menu => { menu.open = false; }); });
}

// The closed window's draft stays on the server for explicit recovery; a
// reload of this tab finishes this close if the request did not arrive.
window.addEventListener('pagehide', () => { if (editor.info?.session) sessionStorage.setItem(closedSessionKey, editor.info.session); });
window.addEventListener('pagehide', () => { if (editor.info?.session) fetch('/api/session', {method: 'POST', headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'}, body: JSON.stringify({session: editor.info.session, action: 'close'}), keepalive: true}).catch(() => {}); });


function bondRequest(active, end) {
  return {kind: 'bond', start: [active.start.x, active.start.y], end: [end.x, end.y], style: bondStyle};
}

// The snap reach is on screen, so each request takes the zoom shown when it is made.
function arrowRequest(active, end) {
  return {kind: active.kind, grid: gridMode(), start: [active.start.x, active.start.y], end: [end.x, end.y], style: active.style, dragged: active.dragged, shift: active.shift, scale: viewScale(), ...(active.kind === 'line' ? {hits: active.hits} : {})};
}

function bracketRequest(active, end) {
  return {kind: 'ts_bracket', start: [active.start.x, active.start.y], end: [end.x, end.y], style: active.style};
}

function shapeRequest(active, end) {
  return {kind: 'shape', start: [active.start.x, active.start.y], end: [end.x, end.y], style: active.style, stroke: active.stroke};
}

async function refreshGesturePreview() {
  if (previewPending || !['bond', 'move', 'arrow', 'line', 'shape', 'ts_bracket', 'handle', 'rotate'].includes(gesture?.kind) || gesture.released || !preview) return;
  // A preview belongs to its gesture and to the accepted session and revision
  // that gesture began on: it is asked for that base, and its reply counts only
  // while the same gesture and base are current and the reply carries them. A
  // gesture whose base has gone is never asked for against a newer one.
  const serial = previewSerial, projected = preview, active = gesture, {session, revision} = active;
  if (editor.info.session !== session || editor.info.revision !== revision) return;
  const change = gesture.kind === 'rotate' ? rotationRequest(gesture,projected.end) : gesture.kind === 'handle' ? handleRequest(gesture, projected.end) : gesture.kind === 'move' ? moveRequest(gesture, projected.end) : ['arrow', 'line'].includes(gesture.kind) ? arrowRequest(gesture, projected.end) : gesture.kind === 'shape' ? shapeRequest(gesture, projected.end) : gesture.kind === 'ts_bracket' ? bracketRequest(gesture, projected.end) : bondRequest(gesture, projected.end);
  try {
    previewPending = sessionRequest({session, revision, action: 'preview', edit: change, selection: selectedItems()});
    const info = await previewPending;
    if (gesture !== active || editor.info.session !== session || editor.info.revision !== revision || info.session !== session || info.revision !== revision) return;
    // A Line or Arrow snap reach is on screen: a reply asked at another zoom is stale.
    if (['arrow', 'line'].includes(active.kind) && change.scale !== arrowRequest(active, projected.end).scale) return;
    // A reply after a later move still carries the handle point its release waits for.
    if (active.kind === 'handle' && active.target === 'arrow') {
      active.previous = info.drawing.arrows[active.id].handles.find(item => item.handle === active.handle).point;
    }
    if (serial === previewSerial) { previewInfo = info; render(); }
  } catch { /* A release reports errors through the committed edit path. */ }
  finally {
    previewPending = null;
    // A moved or new gesture asks again, entirely from its own state.
    if ((serial !== previewSerial || gesture !== active) && gesture) void refreshGesturePreview();
  }
}


function rotationRequest(active,end) {
  return {kind:'rotate', selection:active.selection, start:[active.start.x,active.start.y], end:[end.x,end.y], shift:active.shift};
}

// A moved arrow end joins another within an on-screen reach, at the zoom shown now.
function moveRequest(active, end) {
  return {kind: 'move', selection: active.selection, dx: end.x - active.start.x, dy: end.y - active.start.y, scale: viewScale()};
}

function updateMarquee(active, end) {
  active.end = end;
  active.dragged ||= (Math.abs(end.x - active.start.x) + Math.abs(end.y - active.start.y)) * active.scale >= ui.drag_distance;
  if (!active.dragged) { render(); return; }
  const selected = marqueeSelection(canvas, active.start, end, active.initialSelection, active.additive);
  if (selected === null) {
    cancelGesture();
    notice('Area selection is not supported in this browser. Use Shift-click or Select All, or open this document in the desktop app.', true);
    return;
  }
  selection = expandToGroups(selected, groupUnits());
  preview = {kind: 'marquee', start: active.start, end};
  render();
}

function selectionGestureMoved(active, end) {
  active.dragged ||= active.hasArrows
    ? (Math.abs(end.x - active.start.x) + Math.abs(end.y - active.start.y)) * active.scale >= ui.drag_distance
    : end.x !== active.start.x || end.y !== active.start.y;
  return active.dragged;
}

function finishSelection(active, end) {
  const moved = selectionGestureMoved(active, end);
  if (moved) handleTarget = null;
  else if (active.toggleHandle !== null) handleTarget = handleTarget === active.toggleHandle ? null : active.toggleHandle;
  cancelGesture();
  // A move held across another edit or a document change belongs to a document
  // that is gone, as a rotation's does.
  if (moved && editor.info.session === active.session && editor.info.revision === active.revision) void edit(moveRequest(active, end));
}

function handleRequest(active, end) {
  if (['shape', 'orbital'].includes(active.target)) return {kind: `${active.target}_handle`, id: active.id, handle: active.handle, position: [end.x, end.y]};
  return {kind: 'arrow_handle', grid: gridMode(), id: active.id, handle: active.handle,
    position: [end.x, end.y], previous: active.previous, scale: active.scale};
}

async function finishHandle(active) {
  active.released = true;
  // An in-flight preview owns the last valid endpoint; a too-short final
  // frame must retain that endpoint, as the native handle mutation does.
  try { await previewPending; } catch { /* The final edit reports failures. */ }
  if (gesture !== active) return;
  cancelGesture();
  if (active.moved && editor.info.session === active.session && editor.info.revision === active.revision) {
    void edit(handleRequest(active, active.end));
  }
}


async function refreshSelectionOutline() {
  const request = outlineRequest, key = JSON.stringify(request);
  if (outlinePending || !request || outlineResult.key === key) return;
  outlinePending = true;
  try {
    const result = await api('session', request);
    if (JSON.stringify(outlineRequest) === key) {
      outlineResult = {key, components:result.components, frame:result.frame, groups:result.groups ?? []};
      render();
    }
  } catch (error) {
    if (JSON.stringify(outlineRequest) === key) {
      outlineResult = {key, components:[], frame:null, groups:[]};
      if (!editor.busy && !loading) notice(error.message, true);
    }
  } finally {
    outlinePending = false;
    if (outlineRequest && JSON.stringify(outlineRequest) !== outlineResult.key && !editor.busy && !loading) void refreshSelectionOutline();
  }
}
