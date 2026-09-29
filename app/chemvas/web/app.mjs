import {SessionClient, sessionDrawing} from './transport.mjs';
import {sceneMarkup, AtomLabelCache, zoomView, wheelView, pointInSheet, marqueeSelection, measureDocumentLineHeight, selectionFrameMarkup, gridMarkup} from './scene.mjs';

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
let tool = 'bond', markKind = 'plus', selection = new Set(), gesture = null, preview = null, loading = false;
let view = {x: -25, y: -25, width: 645, height: 892};
let ui = null, bondStyle = 'single', arrowStyle = 'reaction', lineStyle = 'line', shapeStyle = 'circle', shapeStroke = 'solid', paintColor = null, ringFillColor = '#000000', contextPage = null, pointerPosition = null;
let grid = null;
const markHover = {request:null, result:null, pending:false};
let previewInfo = null, previewSerial = 0, previewPending = null, handleTarget = null;
let outlineRequest = null, outlinePending = false, outlineResult = {key:null,components:[],frame:null};
const supportedTools = new Set(['select', 'bond', 'benzene', 'delete', 'text', 'arrow', 'line', 'shape', 'color', 'ring_fill', 'mark']);

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
document.body.append(arrowProbe);
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
  return font;
}
function sessionRequest(request) {
  return sessionDrawing(request, value => api('session', value),
    measureLabels);
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
    if (item.dataset.tool === 'ring_fill') item.removeAttribute('aria-pressed');
    else item.setAttribute('aria-pressed', String(item.dataset.tool === tool));
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
  document.querySelectorAll('[data-context]').forEach(item => { item.hidden = item.dataset.context !== (contextPage ?? tool); });
  document.querySelectorAll('[data-bond]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.bond === bondStyle)));
  document.querySelectorAll('[data-arrow]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.arrow === arrowStyle)));
  document.querySelectorAll('[data-line]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.line === lineStyle)));
  document.querySelectorAll('[data-mark-kind]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.markKind === markKind)));
  document.querySelectorAll('[data-shape]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.shape === shapeStyle)));
  document.querySelectorAll('[data-color]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.color === paintColor)));
  document.querySelectorAll('[data-stroke]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.stroke === shapeStroke)));
  document.querySelectorAll('[data-setting]').forEach(item => { item.value = Math.round(state.settings[item.dataset.setting] * Number(item.dataset.factor)); });
  $('bond-length').value = state.settings.bond_length_px;
  const gridMode = grid.enabled ? grid.style : 'none';
  $('grid-mode').textContent = `Grid: ${gridMode[0].toUpperCase()+gridMode.slice(1)}`;
  $('grid-toggle').setAttribute('aria-pressed',String(grid.enabled));
  document.querySelectorAll('[data-grid]').forEach(item => item.setAttribute('aria-checked',String(item.dataset.grid === gridMode)));
  document.querySelectorAll('[data-grid-strength]').forEach(item => item.setAttribute('aria-checked',String(Number(item.dataset.gridStrength) === Math.round(grid.opacity*100))));
  $('grid').innerHTML = gridMarkup(editor.info.sheet,grid,ui.grid,state.settings.bond_length_px,Math.min(canvas.clientWidth/view.width,canvas.clientHeight/view.height));
  if (tool !== 'select' || !selection.has(handleTarget)) handleTarget = null;
  outlineRequest = selection.size && !previewInfo ? {session:editor.info.session, revision:editor.info.revision, action:'selection', selection:selectedItems()} : null;
  const outlineKey = JSON.stringify(outlineRequest);
  $('drawing').innerHTML = sceneMarkup(previewInfo?.document ?? editor.document, {selection, components: previewInfo?.selection_components ?? (outlineResult.key === outlineKey ? outlineResult.components : []), preview: gesture?.kind === 'bond' && previewInfo ? null : preview, drawing: previewInfo?.drawing ?? editor.info.drawing, handleTarget, handleStyle: ui.handles, showMarkOwners: tool === 'select', markPreview: tool === 'mark' && !busy && markHover.result?.revision === editor.info.revision ? markHover.result : null, markHoverStyle: ui.mark_hover, scale: Math.min(canvas.clientWidth / view.width, canvas.clientHeight / view.height)});
  for (const label of (previewInfo?.drawing ?? editor.info.drawing).arrow_labels ?? []) {
    const element = document.querySelector(`[data-arrow-label="${label.id}:${label.side}"]`);
    if (element) styleArrowLabel(element, label);
  }
  const frame = selectionFrameMarkup(previewInfo?.selection_frame ?? (outlineResult.key === outlineKey ? outlineResult.frame : null), previewInfo?.drawing ?? editor.info.drawing, ui.handles, Math.min(canvas.clientWidth/view.width, canvas.clientHeight/view.height));
  $('selection-frame').innerHTML = frame.outline;
  $('rotation-handle').innerHTML = editor.readOnly ? '' : frame.handle;
  canvas.dataset.tool = tool;
  canvas.setAttribute('viewBox', `${view.x} ${view.y} ${view.width} ${view.height}`);
  for (const id of ['paper']) {
    $(id).setAttribute('x', -editor.info.sheet[0] / 2);
    $(id).setAttribute('y', -editor.info.sheet[1] / 2);
    $(id).setAttribute('width', editor.info.sheet[0]);
    $(id).setAttribute('height', editor.info.sheet[1]);
  }
  $('zoom-level').textContent = `${Math.round((canvas.getScreenCTM()?.a ?? 1) * 100)}%`;
  $('status').textContent = busy ? 'Applying edit…' : editor.readOnly ? 'Read-only · incomplete preview' : (ui?.hints[tool] ?? `${ui?.groups.flat().find(item => item.key === tool)?.label ?? tool}: ready`);
  if (!busy) void refreshSelectionOutline();
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
  render(); void refreshMarkHover();
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
  if (gesture?.kind === 'marquee' && !gesture.accepted) selection = new Set(gesture.initialSelection);
  gesture = preview = previewInfo = null;
  markHover.request = markHover.result = null;
  previewSerial++;
  if (pointer !== undefined && canvas.hasPointerCapture(pointer)) canvas.releasePointerCapture(pointer);
  render();
}

async function edit(change) {
  if (loading || editor.busy || editor.readOnly) return;
  notice();
  const pending = editor.perform(change);
  render();
  try { await pending; if (editor.info.edit_notice) notice(editor.info.edit_notice); return true; }
  catch (error) { notice(error.message, true); return false; }
  finally { render(); void refreshMarkHover(); }
}

async function loadDocument(infoPromise, name) {
  loading = true;
  selection = new Set();
  cancelGesture();
  render();
  try {
    const info = await infoPromise;
    await editor.load(info, name);
    tool = 'bond'; paintColor = null; contextPage = null;
    grid = {enabled:false,style:ui.grid.style,opacity:ui.grid.opacity};
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
    ...editor.document.state.shapes.map((_, id) => `shape:${id}`),
    ...editor.document.state.ring_fills.map((_, id) => `ring:${id}`),
    ...editor.document.state.marks.map((_, id) => `mark:${id}`),
  ]);
  render();
}

function setTool(next) { if (supportedTools.has(next)) { handleTarget = null; cancelGesture(); contextPage = next === 'ring_fill' ? next : null; tool = next === 'ring_fill' ? 'select' : next; render(); void refreshMarkHover(); } }

canvas.addEventListener('pointerdown', event => {
  if (!editor.document || editor.busy || loading || gesture || event.button !== 0
      || (ui.navigation.zoom_modifier === 'meta' && event.ctrlKey)) return;
  canvas.focus();
  pointerPosition = {clientX: event.clientX, clientY: event.clientY};
  const p = point(event), item = event.target.closest('[data-item]')?.dataset.item ?? null;
  const [kind, rawId] = item?.split(':') ?? [];
  const id = Number(rawId);
  const hits = selectedItems(new Set(document.elementsFromPoint(event.clientX, event.clientY)
    .filter(element => canvas.contains(element))
    .map(element => element.closest('[data-item]')?.dataset.item)
    .filter(key => key && /^(atom|bond|arrow|shape|ring|mark):/.test(key))));
  const scale = Math.min(canvas.clientWidth / view.width, canvas.clientHeight / view.height);
  const handle = event.target.closest('[data-handle]');
  if (tool === 'select' && handle?.dataset.handle === ui.handles.rotation_type && !editor.readOnly) {
    gesture = {kind:'rotate', start:p, end:p, shift:event.shiftKey, selection:selectedItems(), pointer:event.pointerId,
      session:editor.info.session, revision:editor.info.revision};
  } else if (tool === 'select' && handle && !editor.readOnly) {
    gesture = {kind: 'handle', target: handle.dataset.shapeId === undefined ? 'arrow' : 'shape', id: Number(handle.dataset.shapeId ?? handle.dataset.arrowId), handle: handle.dataset.handle,
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
    else if (tool === 'benzene') void edit({kind: 'ring', x: p.x, y: p.y, atom_id: kind === 'atom' ? id : null});
    else if (tool === 'mark') void editWithMarkMeasurements({kind:'mark',x:p.x,y:p.y,mark_kind:markKind,hits,scale});
    else {
      gesture = {kind: tool, start: p, pointer: event.pointerId, pressX: event.clientX, pressY: event.clientY, dragged: false, shift: event.shiftKey, style: tool === 'shape' ? shapeStyle : tool === 'line' ? lineStyle : arrowStyle, stroke: shapeStroke, scale, hits};
    }
  }
  if (gesture) canvas.setPointerCapture(event.pointerId);
  render();
});

async function editWithMarkMeasurements(change) {
  if (loading || editor.busy || editor.readOnly) return;
  const spec = editor.info.drawing.label_measurements;
  const queries = [...new Map([...spec.queries, ...spec.mark_queries].map(query => [query.key,query])).values()];
  loading = true; render();
  try {
    await api('session',{session:editor.info.session,revision:editor.info.revision,action:'measure',font:measureLabels({...spec,queries})});
  } catch (error) { notice(error.message,true); return; }
  finally { loading = false; render(); }
  return await edit(change);
}

async function refreshMarkHover() {
  if (!pointerPosition || tool !== 'mark' || !editor.document || editor.readOnly || loading || editor.busy || gesture || !pointInSheet(point(pointerPosition),editor.info.sheet)) {
    const visible = Boolean(markHover.result);
    markHover.request = markHover.result = null; if (visible) render(); return;
  }
  const p = point(pointerPosition);
  const hits = selectedItems(new Set(document.elementsFromPoint(pointerPosition.clientX,pointerPosition.clientY)
    .filter(element=>canvas.contains(element)).map(element=>element.closest('[data-item]')?.dataset.item)
    .filter(key=>key && /^(atom|bond|arrow|shape|ring|mark):/.test(key))));
  const request = {session:editor.info.session,revision:editor.info.revision,action:'mark_preview',x:p.x,y:p.y,kind:markKind,hits,scale:Math.min(canvas.clientWidth/view.width,canvas.clientHeight/view.height)};
  markHover.request = request;
  if (markHover.pending) return;
  markHover.pending = true;
  try {
    while (markHover.request) {
      const current = markHover.request, spec = editor.info.drawing.label_measurements;
      const queries = [...new Map([...spec.queries,...spec.mark_queries].map(query=>[query.key,query])).values()];
      let result;
      try { result = await api('session',{...current,font:measureLabels({...spec,queries})}); }
      catch { if (markHover.request === current) { markHover.request = markHover.result = null; render(); break; } else continue; }
      if (markHover.request && current.session === editor.info.session && current.revision === editor.info.revision && current.kind === markKind && tool === 'mark' && !loading && !editor.busy) {
        markHover.result = result; render();
      }
      if (markHover.request === current) break;
    }
  } finally { markHover.pending = false; }
}

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
    active.toggleHandle = !active.shift && (item?.startsWith('shape:') || (item?.startsWith('arrow:') && selection.has(item))) ? item : null;
    if (active.toggleHandle === null) handleTarget = null;
    if (!item) {
      if (!active.additive) selection.clear();
    } else if (active.shift) {
      if (selection.has(item)) selection.delete(item); else selection.add(item);
    } else if (!selection.has(item)) selection = new Set([item]);
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
  void refreshMarkHover();
});
canvas.addEventListener('pointermove', event => {
  pointerPosition = {clientX: event.clientX, clientY: event.clientY};
  if (!editor.document) return;
  const p = point(event);

  if (!gesture) { void refreshMarkHover(); return; }
  if (gesture.kind === 'pick') {
    gesture.end = p;
    return;
  }
  if (gesture.kind === 'marquee') {
    updateMarquee(gesture, p);
  } else if (gesture.kind === 'rotate') {
    gesture.end = p; gesture.shift = event.shiftKey;
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
  } else if (['bond', 'arrow', 'line', 'shape'].includes(gesture.kind)) {
    if (!pointInSheet(p, editor.info.sheet)) {
      cancelGesture();
      notice(ui.off_sheet_guidance, true);
      return;
    }
    gesture.dragged ||= Math.abs(event.clientX - gesture.pressX) + Math.abs(event.clientY - gesture.pressY) >= ui.drag_distance;
    gesture.shift = event.shiftKey;
    preview = {kind: gesture.kind === 'bond' ? 'line' : gesture.kind === 'shape' ? 'shape' : 'arrow', start: gesture.start, end: p};
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
  if (event.detail !== 2 || event.button !== 0 || !['select', 'arrow', 'line'].includes(tool) || editor.readOnly || editor.busy || loading
      || (ui.navigation.zoom_modifier === 'meta' && event.ctrlKey)) return;
  cancelGesture();
  const p = point(event);
  const hits = selectedItems(new Set(document.elementsFromPoint(event.clientX, event.clientY)
    .filter(element => canvas.contains(element)).map(element => element.closest('[data-item]')?.dataset.item)
    .filter(key => key && /^(atom|bond|arrow|shape|ring|mark):/.test(key))));
  const session = editor.info.session, revision = editor.info.revision;
  loading = true; render();
  try {
    const result = await api('session', {session, revision, action: 'pick', ...p, hits,
      preferred: false, scale: Math.min(canvas.clientWidth / view.width, canvas.clientHeight / view.height)});
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
          styleArrowLabel(element, ui.arrow_labels.preview);
        }
      } catch (error) { if (serial === current) notice(error.message, true); }
    };
    for (const side of ['above', 'below']) $(`arrow-label-${side}`).oninput = update;
    $('arrow-label-hint').textContent = ui.arrow_labels.hint;
    dialog.returnValue = 'cancel';
    dialog.showModal();
    $('arrow-label-above').focus();
    void update();
    await new Promise(resolve => dialog.addEventListener('close', resolve, {once: true}));
    serial++;
    const labels = values();
    loading = false;
    if (dialog.returnValue === 'ok') await edit({kind: 'arrow_labels', id, labels});
  } catch (error) { notice(error.message, true); }
  finally { loading = false; render(); canvas.focus(); }
});
$('arrow-label-cancel').onclick = () => $('arrow-label-dialog').close('cancel');
canvas.addEventListener('contextmenu', event => {
  event.preventDefault();
  if (editor.readOnly || editor.busy || loading || gesture) return;
  const stack = document.elementsFromPoint(event.clientX,event.clientY)
    .filter(element => canvas.contains(element));
  if (stack.some(element => element.closest('[data-handle]'))) return;
  const mark = stack.map(element => element.closest('[data-item^="mark:"]')).find(Boolean);
  if (!mark) return;
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
      const scale = Math.min(canvas.clientWidth/view.width,canvas.clientHeight/view.height);
      const margin = 80/scale;
      if (x < view.x+margin) view.x = x-margin;
      else if (x+w > view.x+view.width-margin) view.x = x+w+margin-view.width;
      if (y < view.y+margin) view.y = y-margin;
      else if (y+h > view.y+view.height-margin) view.y = y+h+margin-view.height;
      canvas.setAttribute('viewBox', `${view.x} ${view.y} ${view.width} ${view.height}`);
      const ellipse = document.createElementNS('http://www.w3.org/2000/svg','ellipse');
      for (const [key,value] of Object.entries({cx:x+w/2,cy:y+h/2,rx:w/2+2,ry:h/2+2,fill:'none',stroke:'#a21caf','stroke-width':editor.info.drawing.selection_style.screen_width,'vector-effect':'non-scaling-stroke','pointer-events':'none'})) ellipse.setAttribute(key,String(value));
      $('mark-candidate').append(ellipse);
    };
    const dialog = $('mark-owner-dialog');
    loading = true;
    field.onchange = highlight;
    dialog.returnValue = 'cancel';
    dialog.showModal(); highlight(); field.focus();
    await new Promise(resolve => dialog.addEventListener('close',resolve,{once:true}));
    $('mark-candidate').replaceChildren();
    view = originalView; loading = false;
    if (dialog.returnValue === 'ok' && field.value !== '') await edit({kind:'mark_owner',id,atom_id:Number(field.value)});
    render(); canvas.focus();
  };
  $('reassign-mark').focus();
});
$('mark-owner-cancel').onclick = () => $('mark-owner-dialog').close('cancel');
document.addEventListener('pointerdown', event => { if (!$('mark-menu').contains(event.target)) $('mark-menu').hidden = true; });
document.addEventListener('keydown', event => { if (event.key === 'Escape') $('mark-menu').hidden = true; });

canvas.addEventListener('pointerleave', () => { pointerPosition = null; void refreshMarkHover(); });
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
  render(); void refreshMarkHover();
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
$('grid-mode').onclick = () => setGrid(ui.grid.modes[(ui.grid.modes.indexOf(grid.enabled ? grid.style : 'none')+1)%ui.grid.modes.length]);
$('grid-toggle').onclick = () => setGrid(grid.enabled ? 'none' : grid.style);

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
  const [width,height] = settings.sheet_custom_size_mm ?? ui.sheet_setup.dimensions.A4.slice().reverse();
  $('sheet-width').value = width.toFixed(ui.sheet_setup.decimals);
  $('sheet-height').value = height.toFixed(ui.sheet_setup.decimals);
  updateSheetFields(); dialog.returnValue = 'cancel'; dialog.showModal(); $('sheet-size').focus();
  await new Promise(resolve => dialog.addEventListener('close',resolve,{once:true}));
  loading = false;
  if (dialog.returnValue === 'ok') await edit({kind:'sheet_setup',size:$('sheet-size').value,orientation:$('sheet-orientation').value,custom_size_mm:$('sheet-size').value === ui.sheet_setup.custom ? ['width','height'].map(axis=>Number(Number($(`sheet-${axis}`).value).toFixed(ui.sheet_setup.decimals))) : null});
  render(); canvas.focus();
};
$('sheet-size').onchange = $('sheet-orientation').onchange = updateSheetFields;
$('sheet-cancel').onclick = () => $('sheet-dialog').close('cancel');

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
  try { await pending; selection = new Set(); } catch (error) { notice(error.message, true); } finally { render(); void refreshMarkHover(); }
};
$('delete').onclick = () => void deleteSelection();
$('select-all').onclick = selectAll;
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
$('bond-length').onchange = () => void edit({kind: 'bond_length', value: Number($('bond-length').value)});
$('atom-label-cancel').onclick = () => $('atom-dialog').close('cancel');
$('help').onclick = () => $('help-dialog').showModal();
$('close-help').onclick = () => $('help-dialog').close();
window.addEventListener('beforeunload', event => { if (editor.dirty || editor.busy) { event.preventDefault(); event.returnValue = ''; } });
document.addEventListener('keydown', event => {
  if (event.isComposing || document.querySelector('dialog[open]')) return;
  const popup = document.querySelector('.arrow-popup[open], #grid-options[open]');
  if (event.key === 'Escape' && popup) { event.preventDefault(); popup.open = false; canvas.focus(); return; }
  if (event.target.matches('input, textarea, select')) return;
  // Focused controls own activation, even while the pointer stays over the canvas.
  if (['Enter', ' '].includes(event.key) && event.target.closest('button, summary, a[href]')) return;
  if (event.key === 'Escape') { event.preventDefault(); setTool('select'); return; }
  if (editor.busy || loading) return;
  const key = event.key.toLowerCase(), command = event.ctrlKey || event.metaKey;
  if (command && key === 'a') { event.preventDefault(); selectAll(); }
  else if (command && event.shiftKey && !event.altKey && ['h','v'].includes(key)) { event.preventDefault(); if (!editor.readOnly) $(key === 'h' ? 'flip-horizontal' : 'flip-vertical').click(); }
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
      const apply = ['+','-'].includes(text) ? editWithMarkMeasurements : edit;
      void apply({kind: 'hover_shortcut', ...hoverPoint(), key: text}).then(ok => {
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
  for (const spec of ui.mark_options) {
    const element = button(spec); element.dataset.markKind = spec.key; element.dataset.editable = '';
    element.onclick = () => { markKind = spec.key; markHover.result = null; render(); void refreshMarkHover(); };
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
      slider.dataset.setting = spec.setting; slider.dataset.factor = spec.factor; slider.dataset.editable = ''; slider.setAttribute('aria-label', spec.label);
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
  const ring = button(ui.groups.flat().find(item => item.key === 'benzene'));
  ring.setAttribute('aria-pressed', 'true');
  $('ring-options').append(ring);
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

window.addEventListener('pagehide', () => { if (editor.info?.session) fetch('/api/session', {method: 'POST', headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'}, body: JSON.stringify({session: editor.info.session, action: 'close'}), keepalive: true}).catch(() => {}); });


function bondRequest(active, end) {
  return {kind: 'bond', start: [active.start.x, active.start.y], end: [end.x, end.y], style: bondStyle};
}

function arrowRequest(active, end) {
  return {kind: active.kind, grid: grid.enabled ? grid.style : 'none', start: [active.start.x, active.start.y], end: [end.x, end.y], style: active.style, dragged: active.dragged, shift: active.shift, scale: active.scale, ...(active.kind === 'line' ? {hits: active.hits} : {})};
}

function shapeRequest(active, end) {
  return {kind: 'shape', start: [active.start.x, active.start.y], end: [end.x, end.y], style: active.style, stroke: active.stroke};
}

async function refreshGesturePreview() {
  if (previewPending || !['bond', 'move', 'arrow', 'line', 'shape', 'handle', 'rotate'].includes(gesture?.kind) || gesture.released || !preview) return;
  const serial = previewSerial, projected = preview, active = gesture;
  const change = gesture.kind === 'rotate' ? rotationRequest(gesture,projected.end) : gesture.kind === 'handle' ? handleRequest(gesture, projected.end) : gesture.kind === 'move' ? moveRequest(gesture, projected.end) : ['arrow', 'line'].includes(gesture.kind) ? arrowRequest(gesture, projected.end) : gesture.kind === 'shape' ? shapeRequest(gesture, projected.end) : bondRequest(gesture, projected.end);
  try {
    previewPending = sessionRequest({session: editor.info.session, revision: editor.info.revision, action: 'preview', edit: change, selection: selectedItems()});
    const info = await previewPending;
    if (gesture === active && active.kind === 'handle' && active.target === 'arrow') {
      active.previous = info.drawing.arrows[active.id].handles.find(item => item.handle === active.handle).point;
    }
    if (serial === previewSerial && gesture) { previewInfo = info; render(); }
  } catch { /* A release reports errors through the committed edit path. */ }
  finally {
    previewPending = null;
    if (serial !== previewSerial && gesture) void refreshGesturePreview();
  }
}


function rotationRequest(active,end) {
  return {kind:'rotate', selection:active.selection, start:[active.start.x,active.start.y], end:[end.x,end.y], shift:active.shift};
}

function moveRequest(active, end) {
  return {kind: 'move', selection: active.selection, dx: end.x - active.start.x, dy: end.y - active.start.y};
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
  selection = selected;
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
  if (moved) void edit(moveRequest(active, end));
}

function handleRequest(active, end) {
  if (active.target === 'shape') return {kind: 'shape_handle', id: active.id, handle: active.handle, position: [end.x, end.y]};
  return {kind: 'arrow_handle', grid: grid.enabled ? grid.style : 'none', id: active.id, handle: active.handle,
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
      if (result.revision !== request.revision) throw new Error('The selection drawing has a stale revision.');
      outlineResult = {key, components:result.components, frame:result.frame};
      render();
    }
  } catch (error) {
    if (JSON.stringify(outlineRequest) === key) {
      outlineResult = {key, components:[], frame:null};
      if (!editor.busy && !loading) notice(error.message, true);
    }
  } finally {
    outlinePending = false;
    if (outlineRequest && JSON.stringify(outlineRequest) !== outlineResult.key && !editor.busy && !loading) void refreshSelectionOutline();
  }
}
