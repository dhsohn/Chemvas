import {SessionClient} from './transport.mjs';
import {sceneMarkup, measureAtomLabels, zoomView, wheelView} from './scene.mjs';

const $ = id => document.getElementById(id);
const editor = new SessionClient(request => api('session', request));
const canvas = $('canvas');
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
let tool = 'bond', selection = new Set(), gesture = null, preview = null, loading = false;
let view = {x: -25, y: -25, width: 645, height: 892};
let ui = null, bondStyle = 'single';
let previewInfo = null, previewSerial = 0, previewPending = false;
const supportedTools = new Set(['select', 'bond', 'benzene', 'delete', 'text']);

async function api(path, body) {
  const response = await fetch(`/api/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'},
    body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) throw Object.assign(new Error(value.error ?? 'The request failed.'), {status: response.status});
  if (value.document && value.drawing) {
    const spec = value.drawing.label_measurements;
    try {
      value.drawing.atom_layouts = spec.queries.length ? await api('labels', {
        document: value.document, measurements: measureAtomLabels(spec, fontContext, measureLineHeight),
      }) : {};
    } catch (error) {
      // The document request already succeeded; only its presentation failed.
      error.uncertain = true;
      throw error;
    }
  }
  return value;
}

function notice(text = '', error = false) {
  $('notice').textContent = text;
  $('notice').hidden = !text;
  $('notice').classList.toggle('error', error);
}

function render() {
  const busy = editor.busy || loading;
  document.querySelectorAll('[data-idle]').forEach(item => { item.disabled = busy; });
  document.querySelectorAll('[data-editable]').forEach(item => { item.disabled = busy || editor.readOnly; });
  document.querySelectorAll('[data-tool]').forEach(item => {
    item.setAttribute('aria-pressed', String(item.dataset.tool === tool));
    item.disabled = !supportedTools.has(item.dataset.tool) || busy || (editor.readOnly && item.dataset.tool !== 'select');
  });
  $('undo').disabled = busy || !editor.canUndo;
  $('redo').disabled = busy || !editor.canRedo;
  $('delete').disabled = busy || editor.readOnly || !selection.size;
  if (!editor.document) return;
  const state = editor.document.state;
  const name = editor.name.replace(/\.chemvas$/i, '');
  document.title = `${editor.dirty ? '• ' : ''}${name} — Chemvas`;
  $('canvas-status').textContent = `Canvas: ${name}`;
  $('selection').textContent = `Selection: ${selection.size}`;
  $('tool-status').textContent = `Tool: ${ui?.groups.flat().find(item => item.key === tool)?.label ?? tool}`;
  document.querySelectorAll('[data-context]').forEach(item => { item.hidden = item.dataset.context !== tool; });
  document.querySelectorAll('[data-bond]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.bond === bondStyle)));
  $('bond-length').value = state.settings.bond_length_px;
  $('drawing').innerHTML = sceneMarkup(previewInfo?.document ?? editor.document, {selection, preview: gesture?.kind === 'bond' && previewInfo ? null : preview, drawing: previewInfo?.drawing ?? editor.info.drawing});
  canvas.dataset.tool = tool;
  canvas.setAttribute('viewBox', `${view.x} ${view.y} ${view.width} ${view.height}`);
  for (const id of ['paper']) {
    $(id).setAttribute('width', editor.info.sheet[0]);
    $(id).setAttribute('height', editor.info.sheet[1]);
  }
  $('zoom-level').textContent = `${Math.round((canvas.getScreenCTM()?.a ?? 1) * 100)}%`;
  $('status').textContent = busy ? 'Applying edit…' : editor.readOnly ? 'Read-only · incomplete preview' : (ui?.hints[tool] ?? 'Eraser: click to erase');
}

function fitPage() {
  if (!editor.info) return;
  const [width, height] = editor.info.sheet;
  view = {x: -25, y: -25, width: width + 50, height: height + 50};
  render();
}

function zoom(factor) {
  if (!ui || !editor.info) return;
  view = zoomView(view, {width: canvas.clientWidth, height: canvas.clientHeight}, factor, ui.navigation);
  render();
}

function point(event) {
  const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(canvas.getScreenCTM().inverse());
  return {x: p.x, y: p.y};
}

function cancelGesture() {
  const pointer = gesture?.pointer;
  gesture = preview = previewInfo = null;
  previewSerial++;
  if (pointer !== undefined && canvas.hasPointerCapture(pointer)) canvas.releasePointerCapture(pointer);
  render();
}

async function edit(change) {
  if (loading || editor.busy || editor.readOnly) return;
  notice();
  const pending = editor.perform(change);
  render();
  try { await pending; return true; }
  catch (error) { notice(error.message, true); return false; }
  finally { render(); }
}

async function loadDocument(infoPromise, name) {
  loading = true;
  selection = new Set();
  cancelGesture();
  render();
  try {
    const info = await infoPromise;
    await editor.load(info, name);
    tool = 'bond';
    notice(info.unsupported.length ? `Incomplete, read-only preview: ${info.unsupported.join(', ')}. These elements are not faithfully displayed. Save copy preserves their data; use the desktop app to edit or export this drawing.` : '');
    actualSize();
  } catch (error) { notice(error.message, true); }
  finally { loading = false; render(); }
}

function mayReplace() {
  return !editor.busy && !loading && (!editor.dirty || confirm('Discard unsaved changes? Save a copy first if you want to keep them.'));
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
    const plan = await api('atom-input', {document: editor.document, edit: change, symbol: $('atom-symbol').value});
    text = plan.text;
    if (plan.needs_prompt) {
      const dialog = $('atom-dialog');
      $('atom-label').value = plan.initial;
      dialog.returnValue = 'cancel';
      const closed = new Promise(resolve => dialog.addEventListener('close', resolve, {once: true}));
      dialog.showModal();
      $('atom-label').focus();
      $('atom-label').select();
      await closed;
      text = dialog.returnValue === 'ok' ? $('atom-label').value : null;
    }
  } catch (error) { notice(error.message, true); }
  finally { loading = false; render(); }
  if (text !== null && text !== undefined) await edit({...change, text});
}

function selectedItems(keys = selection) {
  return [...keys].map(key => {
    const [target, id] = key.split(':');
    return {target, id: Number(id)};
  });
}

async function deleteSelection() {
  if (!selection.size) return;
  cancelGesture();
  const items = selectedItems();
  const change = {kind: 'delete_selection', selection: items};
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
  ]);
  render();
}

function setTool(next) { if (supportedTools.has(next)) { cancelGesture(); tool = next; render(); } }

canvas.addEventListener('pointerdown', event => {
  if (!editor.document || editor.busy || loading || gesture || event.button !== 0) return;
  canvas.focus();
  const p = point(event), item = event.target.closest('[data-item]')?.dataset.item ?? null;
  const [kind, rawId] = item?.split(':') ?? [];
  const id = Number(rawId);
  if (tool === 'select') {
    if (event.shiftKey && item) {
      if (selection.has(item)) selection.delete(item); else selection.add(item);
    } else {
      if (!item) selection.clear();
      else {
        if (!selection.has(item)) selection = new Set([item]);
        if (!editor.readOnly) gesture = {kind: 'move', start: p, selection: selectedItems(), pointer: event.pointerId};
      }
    }
  } else if (!editor.readOnly) {
    if (tool === 'delete') { selection = new Set(item ? [item] : []); void deleteSelection(); }
    else if (tool === 'text') void atomInput({kind: 'atom', x: p.x, y: p.y, atom_id: kind === 'atom' ? id : null, bond_id: kind === 'bond' ? id : null});
    else if (tool === 'benzene') void edit({kind: 'ring', x: p.x, y: p.y, atom_id: kind === 'atom' ? id : null});
    else {
      gesture = {kind: tool, start: p, pointer: event.pointerId};
    }
  }
  if (gesture) canvas.setPointerCapture(event.pointerId);
  render();
});

canvas.addEventListener('pointermove', event => {
  if (!editor.document) return;
  const p = point(event);

  if (!gesture) return;
  if (gesture.kind === 'move') {
    preview = {kind: 'move', end: p};
    previewSerial++;
    void refreshGesturePreview();
  } else if (gesture.kind === 'bond') {
    preview = {kind: 'line', start: gesture.start, end: p};
    previewSerial++;
    void refreshGesturePreview();
  }
  render();
});

canvas.addEventListener('pointerup', event => {
  if (!gesture) return;
  const completed = gesture, p = point(event);
  cancelGesture();
  if (completed.kind === 'bond') {
    void edit(bondRequest(completed, p));
  } else if (completed.kind === 'move' && (p.x !== completed.start.x || p.y !== completed.start.y)) {
    void edit(moveRequest(completed, p));
  }
});
canvas.addEventListener('pointercancel', cancelGesture);
canvas.addEventListener('lostpointercapture', () => { if (gesture) cancelGesture(); });
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  if (gesture || !ui || !editor.info) return;
  const rect = canvas.getBoundingClientRect();
  const deltaMode = event.deltaMode;
  view = wheelView(view, {width: canvas.clientWidth, height: canvas.clientHeight}, {
    deltaX: event.deltaX, deltaY: event.deltaY, deltaMode, ctrlKey: event.ctrlKey,
    position: {x: event.clientX - rect.left, y: event.clientY - rect.top},
  }, ui.navigation, measureLineHeight(getComputedStyle(canvas).font, 'M'));
  render();
}, {passive: false});
window.addEventListener('blur', cancelGesture);


$('new').onclick = () => { if (mayReplace()) void loadDocument(api('new'), 'Canvas 1.chemvas'); };
$('open').onclick = () => { if (mayReplace()) $('file').click(); };
$('file').onchange = async () => {
  const file = $('file').files[0];
  $('file').value = '';
  if (!file) return;
  if (file.size > 2 * 1024 * 1024) { notice('The browser adapter opens files up to 2 MiB.', true); return; }
  await loadDocument(file.text().then(text => api('open', text)), file.name);
};
$('save').onclick = () => {
  if (!editor.document) return;
  download(JSON.stringify(editor.document, null, 2) + '\n', editor.name.replace(/\.chemvas$/i, '') + '-web-copy.chemvas', 'application/json');
  notice('Save copy requested. Check your downloads before closing; the original file has not changed.');
};
for (const action of ['undo', 'redo']) $(action).onclick = async () => {
  cancelGesture(); const pending = editor[action](); render();
  try { await pending; selection = new Set(); } catch (error) { notice(error.message, true); } finally { render(); }
};
$('delete').onclick = deleteSelection;
$('select-all').onclick = selectAll;
$('zoom-in').onclick = () => zoom(1 / ui.navigation.step);
$('zoom-out').onclick = () => zoom(ui.navigation.step);
$('fit').onclick = fitPage;
$('fit-menu').onclick = fitPage;
$('actual-size').onclick = $('zoom-level').onclick = actualSize;
$('zoom-in-menu').onclick = () => zoom(1 / ui.navigation.step);
$('zoom-out-menu').onclick = () => zoom(ui.navigation.step);
$('save-as').onclick = () => $('save').click();
$('bond-length').onchange = () => void edit({kind: 'bond_length', value: Number($('bond-length').value)});
$('atom-label-cancel').onclick = () => $('atom-dialog').close('cancel');
$('help').onclick = () => $('help-dialog').showModal();
$('close-help').onclick = () => $('help-dialog').close();
window.addEventListener('beforeunload', event => { if (editor.dirty || editor.busy) { event.preventDefault(); event.returnValue = ''; } });
document.addEventListener('keydown', event => {
  if (event.isComposing || event.target.matches('input, textarea, select') || document.querySelector('dialog[open]')) return;
  if (event.key === 'Escape') { cancelGesture(); return; }
  if (editor.busy || loading) return;
  const key = event.key.toLowerCase(), command = event.ctrlKey || event.metaKey;
  if (command && key === 'a') { event.preventDefault(); selectAll(); }
  else if (command && key === 'n') { event.preventDefault(); $('new').click(); }
  else if (['F5', 'F6', 'F7', 'F8'].includes(event.key)) { event.preventDefault(); $({'F5': 'actual-size', 'F6': 'fit', 'F7': 'zoom-in', 'F8': 'zoom-out'}[event.key]).click(); }
  else if (command && key === 'z') { event.preventDefault(); $(event.shiftKey ? 'redo' : 'undo').click(); }
  else if (command && key === 's') { event.preventDefault(); $('save').click(); }
  else if (command && key === 'o') { event.preventDefault(); $('open').click(); }
  else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); if (!editor.readOnly) void deleteSelection(); }
  else if (!command) {
    const next = {' ': 'select', x: 'bond', a: 'text', j: 'benzene', e: 'arrow', t: 'note'}[key];
    if (next && !event.shiftKey && !event.altKey && (!editor.readOnly || next === 'select')) { event.preventDefault(); setTool(next); }
    if (tool === 'bond' && !editor.readOnly) {
      const style = {'1': 'single', '2': 'double', '3': 'triple', b: 'bold_in', w: 'wedge', ...(event.shiftKey ? {h: 'hash'} : {})}[key];
      if (style) { bondStyle = style; render(); }
    }
  }
});
new ResizeObserver(() => render()).observe(canvas);
try { ui = await api('ui'); buildControls(); await loadDocument(api('new'), 'Canvas 1.chemvas'); } catch (error) { notice(error.message, true); }


function actualSize() {
  if (!editor.info) return;
  const [width, height] = editor.info.sheet;
  view = {x: (width - canvas.clientWidth) / 2, y: (height - canvas.clientHeight) / 2, width: canvas.clientWidth, height: canvas.clientHeight};
  render();
}

function buildControls() {
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
      element.onclick = () => setTool(spec.key);
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
  const ring = button(ui.groups.flat().find(item => item.key === 'benzene'));
  ring.setAttribute('aria-pressed', 'true');
  $('ring-options').append(ring);
  document.querySelectorAll('.menus details').forEach(menu => {
    menu.addEventListener('toggle', () => { if (menu.open) document.querySelectorAll('.menus details').forEach(other => { if (other !== menu) other.open = false; }); });
    menu.querySelectorAll('button').forEach(item => item.addEventListener('click', () => { menu.open = false; }));
  });
  document.addEventListener('pointerdown', event => { if (!event.target.closest('.menus')) document.querySelectorAll('.menus details').forEach(menu => { menu.open = false; }); });
}

window.addEventListener('pagehide', () => { if (editor.info?.session) fetch('/api/session', {method: 'POST', headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'}, body: JSON.stringify({session: editor.info.session, action: 'close'}), keepalive: true}).catch(() => {}); });


function bondRequest(active, end) {
  return {kind: 'bond', start: [active.start.x, active.start.y], end: [end.x, end.y], style: bondStyle};
}

async function refreshGesturePreview() {
  if (previewPending || !['bond', 'move'].includes(gesture?.kind) || !preview) return;
  const serial = previewSerial, projected = preview;
  const change = gesture.kind === 'move' ? moveRequest(gesture, projected.end) : bondRequest(gesture, projected.end);
  previewPending = true;
  try {
    const info = await api('preview', {document: editor.document, edit: change});
    if (serial === previewSerial && gesture) { previewInfo = info; render(); }
  } catch { /* A release reports errors through the committed edit path. */ }
  finally {
    previewPending = false;
    if (serial !== previewSerial && gesture) void refreshGesturePreview();
  }
}


function moveRequest(active, end) {
  return {kind: 'move', selection: active.selection, dx: end.x - active.start.x, dy: end.y - active.start.y};
}
