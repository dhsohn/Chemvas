import {SessionClient, sessionDrawing} from './transport.mjs';
import {sceneMarkup, AtomLabelCache, zoomView, wheelView, pointInSheet} from './scene.mjs';

const $ = id => document.getElementById(id);
const editor = new SessionClient(request => sessionRequest(request));
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
let tool = 'bond', selection = new Set(), gesture = null, preview = null, loading = false;
let view = {x: -25, y: -25, width: 645, height: 892};
let ui = null, bondStyle = 'single', arrowStyle = 'reaction', pointerPosition = null;
let previewInfo = null, previewSerial = 0, previewPending = false;
const supportedTools = new Set(['select', 'bond', 'benzene', 'delete', 'text', 'arrow']);

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

function sessionRequest(request) {
  return sessionDrawing(request, value => api('session', value),
    spec => labelCache.measure(spec, fontContext, measureLineHeight));
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
  document.querySelectorAll('[data-arrow]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.arrow === arrowStyle)));
  $('bond-length').value = state.settings.bond_length_px;
  $('drawing').innerHTML = sceneMarkup(previewInfo?.document ?? editor.document, {selection, preview: gesture?.kind === 'bond' && previewInfo ? null : preview, drawing: previewInfo?.drawing ?? editor.info.drawing});
  canvas.dataset.tool = tool;
  canvas.setAttribute('viewBox', `${view.x} ${view.y} ${view.width} ${view.height}`);
  for (const id of ['paper']) {
    $(id).setAttribute('x', -editor.info.sheet[0] / 2);
    $(id).setAttribute('y', -editor.info.sheet[1] / 2);
    $(id).setAttribute('width', editor.info.sheet[0]);
    $(id).setAttribute('height', editor.info.sheet[1]);
  }
  $('zoom-level').textContent = `${Math.round((canvas.getScreenCTM()?.a ?? 1) * 100)}%`;
  $('status').textContent = busy ? 'Applying edit…' : editor.readOnly ? 'Read-only · incomplete preview' : (ui?.hints[tool] ?? 'Eraser: click to erase');
}

function fitPage() {
  if (!editor.info) return;
  const [width, height] = editor.info.sheet;
  view = {x: -width / 2 - 25, y: -height / 2 - 25, width: width + 50, height: height + 50};
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

function hoverPoint() {
  const item = document.elementFromPoint(pointerPosition.clientX, pointerPosition.clientY)?.closest('[data-item]');
  const [kind, id] = (item && canvas.contains(item) ? item.dataset.item : '').split(':');
  return {...point(pointerPosition), atom_id: kind === 'atom' ? Number(id) : null};
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
    if (change.kind === 'atom_prompt') {
      if (!plan.needs_prompt) return;
      change = {...change, atom_id: plan.atom_id};
    }
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
  ]);
  render();
}

function setTool(next) { if (supportedTools.has(next)) { cancelGesture(); tool = next; render(); } }

canvas.addEventListener('pointerdown', event => {
  if (!editor.document || editor.busy || loading || gesture || event.button !== 0) return;
  canvas.focus();
  pointerPosition = {clientX: event.clientX, clientY: event.clientY};
  const p = point(event), item = event.target.closest('[data-item]')?.dataset.item ?? null;
  const [kind, rawId] = item?.split(':') ?? [];
  const id = Number(rawId);
  const hits = selectedItems(new Set(document.elementsFromPoint(event.clientX, event.clientY)
    .filter(element => canvas.contains(element))
    .map(element => element.closest('[data-item]')?.dataset.item)
    .filter(key => key && /^(atom|bond|arrow):/.test(key))));
  const scale = Math.min(canvas.clientWidth / view.width, canvas.clientHeight / view.height);
  if (tool === 'select') {
    gesture = {kind: 'pick', start: p, end: p, pointer: event.pointerId, shift: event.shiftKey, hits, scale,
      session: editor.info.session, revision: editor.info.revision, released: false};
    void resolveSelection(gesture);
  } else if (!editor.readOnly) {
    if (tool !== 'delete' && !pointInSheet(p, editor.info.sheet)) {
      notice(ui.off_sheet_guidance, true);
      return;
    }
    if (tool === 'delete') { selection.clear(); void edit({kind: 'erase', x: p.x, y: p.y, hits, scale}); }
    else if (tool === 'text') void atomInput({kind: 'atom', x: p.x, y: p.y, atom_id: kind === 'atom' ? id : null});
    else if (tool === 'benzene') void edit({kind: 'ring', x: p.x, y: p.y, atom_id: kind === 'atom' ? id : null});
    else {
      gesture = {kind: tool, start: p, pointer: event.pointerId, pressX: event.clientX, pressY: event.clientY, dragged: false, shift: event.shiftKey, style: arrowStyle, scale};
    }
  }
  if (gesture) canvas.setPointerCapture(event.pointerId);
  render();
});

async function resolveSelection(active) {
  try {
    const result = await api('session', {session: active.session, revision: active.revision,
      action: 'pick', x: active.start.x, y: active.start.y, hits: active.hits, scale: active.scale, preferred: !active.shift});
    if (gesture !== active) return;
    if (editor.info.session !== active.session || editor.info.revision !== active.revision || result.revision !== active.revision) {
      cancelGesture();
      return;
    }
    const item = result.target ? `${result.target.target}:${result.target.id}` : null;
    if (active.shift) {
      if (item) { if (selection.has(item)) selection.delete(item); else selection.add(item); }
    } else if (!item) selection.clear();
    else if (!selection.has(item)) selection = new Set([item]);
    if (!item || active.shift || editor.readOnly) { cancelGesture(); return; }
    active.kind = 'move'; active.selection = selectedItems();
    if (active.released) {
      cancelGesture();
      if (active.end.x !== active.start.x || active.end.y !== active.start.y) void edit(moveRequest(active, active.end));
    } else {
      if (active.end.x !== active.start.x || active.end.y !== active.start.y) {
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
});
canvas.addEventListener('pointermove', event => {
  pointerPosition = {clientX: event.clientX, clientY: event.clientY};
  if (!editor.document) return;
  const p = point(event);

  if (!gesture) return;
  if (gesture.kind === 'pick') {
    gesture.end = p;
    return;
  }
  if (gesture.kind === 'move') {
    preview = {kind: 'move', end: p};
    previewSerial++;
    void refreshGesturePreview();
  } else if (gesture.kind === 'bond' || gesture.kind === 'arrow') {
    if (!pointInSheet(p, editor.info.sheet)) {
      cancelGesture();
      notice(ui.off_sheet_guidance, true);
      return;
    }
    gesture.dragged ||= Math.abs(event.clientX - gesture.pressX) + Math.abs(event.clientY - gesture.pressY) >= ui.drag_distance;
    gesture.shift = event.shiftKey;
    preview = {kind: gesture.kind === 'arrow' ? 'arrow' : 'line', start: gesture.start, end: p};
    previewSerial++;
    void refreshGesturePreview();
  }
  render();
});

canvas.addEventListener('pointerup', event => {
  if (!gesture) return;
  const completed = gesture, p = point(event);
  if (completed.kind === 'pick') { completed.end = p; completed.released = true; return; }
  cancelGesture();
  if (completed.kind === 'arrow') {
    completed.dragged ||= Math.abs(event.clientX - completed.pressX) + Math.abs(event.clientY - completed.pressY) >= ui.drag_distance;
    completed.shift = event.shiftKey;
    void edit(arrowRequest(completed, p));
  } else if (completed.kind === 'bond') {
    void edit(bondRequest(completed, p));
  } else if (completed.kind === 'move' && (p.x !== completed.start.x || p.y !== completed.start.y)) {
    void edit(moveRequest(completed, p));
  }
});
canvas.addEventListener('pointerleave', () => { pointerPosition = null; });
canvas.addEventListener('pointercancel', cancelGesture);
canvas.addEventListener('lostpointercapture', () => { if (gesture && !(gesture.kind === 'pick' && gesture.released)) cancelGesture(); });
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  if (gesture || !ui || !editor.info) return;
  const rect = canvas.getBoundingClientRect();
  const deltaMode = event.deltaMode;
  view = wheelView(view, {width: canvas.clientWidth, height: canvas.clientHeight}, {
    deltaX: event.deltaX, deltaY: event.deltaY, deltaMode, ctrlKey: event.ctrlKey, metaKey: event.metaKey,
    position: {x: event.clientX - rect.left, y: event.clientY - rect.top},
  }, ui.navigation, measureLineHeight(getComputedStyle(canvas).font, 'M'));
  render();
}, {passive: false});
window.addEventListener('blur', cancelGesture);
document.addEventListener('pointerdown', event => {
  const control = event.target.closest('button, summary');
  if (event.button !== 0 || !control || control.closest('dialog')) return;
  // Match native pointer focus policies without changing keyboard activation.
  event.preventDefault();
  if (control.closest('.menus, footer')) canvas.focus();
});


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
$('delete').onclick = () => void deleteSelection();
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
  // Focused controls own activation, even while the pointer stays over the canvas.
  if (['Enter', ' '].includes(event.key) && event.target.closest('button, summary, a[href]')) return;
  if (event.key === 'Escape') { event.preventDefault(); setTool('select'); return; }
  if (editor.busy || loading) return;
  const key = event.key.toLowerCase(), command = event.ctrlKey || event.metaKey;
  if (command && key === 'a') { event.preventDefault(); selectAll(); }
  else if (command && key === 'n') { event.preventDefault(); $('new').click(); }
  else if (['F5', 'F6', 'F7', 'F8'].includes(event.key)) { event.preventDefault(); $({'F5': 'actual-size', 'F6': 'fit', 'F7': 'zoom-in', 'F8': 'zoom-out'}[event.key]).click(); }
  else if (command && key === 'z') { event.preventDefault(); $(event.shiftKey ? 'redo' : 'undo').click(); }
  else if (command && key === 's') { event.preventDefault(); $('save').click(); }
  else if (command && key === 'o') { event.preventDefault(); $('open').click(); }
  else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); if (!editor.readOnly) void deleteSelection(true); }
  else if (event.key === 'Enter' && !command && !event.altKey && !editor.readOnly && pointerPosition) {
    event.preventDefault(); cancelGesture();
    void atomInput({kind: 'atom_prompt', ...hoverPoint()});
  }
  else if (!command && !event.altKey) {
    const text = event.shiftKey ? event.key.toUpperCase() : key;
    if (pointerPosition && !editor.readOnly && ui.hover_shortcuts.includes(text)) {
      event.preventDefault();
      cancelGesture();
      void edit({kind: 'hover_shortcut', ...hoverPoint(), key: text}).then(ok => {
        if (ok && editor.info.shortcut_tool && !event.shiftKey) {
          if (editor.info.shortcut_tool === 'bond') bondStyle = ui.default_bond_style;
          setTool(editor.info.shortcut_tool);
        }
      });
      return;
    }
    const next = ui.tool_hotkeys[key];
    if (next && !event.shiftKey && (!editor.readOnly || next === 'select')) {
      event.preventDefault();
      if (next === 'bond') bondStyle = ui.default_bond_style;
      setTool(next);
    }
  }
});
new ResizeObserver(() => render()).observe(canvas);
try { ui = await api('ui'); buildControls(); await loadDocument(api('new'), 'Canvas 1.chemvas'); } catch (error) { notice(error.message, true); }


function actualSize() {
  if (!editor.info) return;
  view = {x: -canvas.clientWidth / 2, y: -canvas.clientHeight / 2, width: canvas.clientWidth, height: canvas.clientHeight};
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
  const arrows = document.createElement('div'); arrows.className = 'segments';
  const more = document.createElement('details'); more.id = 'arrow-more';
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
  for (const spec of ui.arrow_style_controls) { const element = button(spec); element.disabled = true; $('arrow-options').append(element); }
  const ring = button(ui.groups.flat().find(item => item.key === 'benzene'));
  ring.setAttribute('aria-pressed', 'true');
  $('ring-options').append(ring);
  document.querySelectorAll('.menus details, #arrow-more').forEach(menu => {
    menu.addEventListener('toggle', () => { if (menu.open) document.querySelectorAll('.menus details, #arrow-more').forEach(other => { if (other !== menu) other.open = false; }); });
    menu.querySelectorAll('button').forEach(item => item.addEventListener('click', () => { menu.open = false; }));
  });
  document.addEventListener('pointerdown', event => { if (!event.target.closest('.menus, #arrow-more')) document.querySelectorAll('.menus details, #arrow-more').forEach(menu => { menu.open = false; }); });
}

window.addEventListener('pagehide', () => { if (editor.info?.session) fetch('/api/session', {method: 'POST', headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'}, body: JSON.stringify({session: editor.info.session, action: 'close'}), keepalive: true}).catch(() => {}); });


function bondRequest(active, end) {
  return {kind: 'bond', start: [active.start.x, active.start.y], end: [end.x, end.y], style: bondStyle};
}

function arrowRequest(active, end) {
  return {kind: 'arrow', start: [active.start.x, active.start.y], end: [end.x, end.y], style: active.style, dragged: active.dragged, shift: active.shift, scale: active.scale};
}

async function refreshGesturePreview() {
  if (previewPending || !['bond', 'move', 'arrow'].includes(gesture?.kind) || !preview) return;
  const serial = previewSerial, projected = preview;
  const change = gesture.kind === 'move' ? moveRequest(gesture, projected.end) : gesture.kind === 'arrow' ? arrowRequest(gesture, projected.end) : bondRequest(gesture, projected.end);
  previewPending = true;
  try {
    const info = await sessionRequest({session: editor.info.session, revision: editor.info.revision, action: 'preview', edit: change});
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
