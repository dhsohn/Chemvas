import test from 'node:test';
import assert from 'node:assert/strict';
import {SessionClient} from '../app/chemvas/web/transport.mjs';
import {sceneMarkup} from '../app/chemvas/web/scene.mjs';

function info(count = 0) {
  const atoms = Object.fromEntries(Array.from({length: count}, (_, id) => [id, {element: id ? 'O' : 'C', x: 30 + 20 * id, y: 40, explicit_label: false, color: '#000000'}]));
  return {drawing: {atom_labels:Object.fromEntries(Object.entries(atoms).filter(([, a]) => a.element !== "C").map(([id, a]) => [id, a.element])), bonds:{}, line_width:1.5, font_size:12, atom_pick_radius:6.4}, unsupported: [], sheet: [595, 842], document: {type: 'chemvas', version: 9, state: {model: {atoms, bonds: [], next_atom_id: count}, arrows: [], notes: [], settings: {bond_length_px: 20, text_font_family: 'Arial', text_font_size: 12, text_color: '#222222'}}}};
}

test('transport sends revisions and only mirrors accepted server state', async () => {
  const calls = [];
  let response = {...info(), session: 'test', revision: 1, dirty: false, can_undo: false, can_redo: true};
  const editor = new SessionClient(async request => { calls.push(request); if (request.action === 'edit') throw new Error('Rejected'); return response; });
  await editor.load(info());
  const before = editor.document;
  await assert.rejects(editor.perform({kind: 'ring'}), /Rejected/);
  assert.equal(editor.document, before);
  assert.equal(editor.canRedo, true);
  assert.equal(editor.busy, false);
  assert.equal(calls[1].revision, 1);
  assert.equal(calls[1].session, 'test');
  response = {...info(6), session: 'test', revision: 2, can_undo: true, can_redo: false, dirty: true};
  await editor.redo();
  assert.equal(Object.keys(editor.document.state.model.atoms).length, 6);
  assert.equal(calls[2].action, 'redo');
});

test('pending request excludes concurrent replacement and edits', async () => {
  let resolve;
  const editor = new SessionClient(() => new Promise(done => { resolve = done; }));
  const pending = editor.load(info());
  assert.equal(editor.busy, true);
  await assert.rejects(editor.load(info(8)), /Wait/);
  await assert.rejects(editor.perform({}), /Wait/);
  resolve(info(1));
  await pending;
  assert.equal(editor.busy, false);
});

test('unsupported content cannot be edited', async () => {
  const source = info(1); source.unsupported = ['images'];
  const editor = new SessionClient(async () => source);
  await editor.load(source);
  await assert.rejects(editor.perform({}), /read-only/);
});

test('SVG display escapes untrusted labels', () => {
  const source = info(1);
  source.drawing.atom_labels[0] = '<script>alert(1)</script>';
  const svg = sceneMarkup(source.document, {drawing: source.drawing});
  assert.ok(svg.includes('&lt;script&gt;'));
  assert.ok(!svg.includes('<script>'));
});

test('drag preview never mutates the committed document', () => {
  const source = info(1), before = JSON.stringify(source);
  const markup = sceneMarkup(source.document, {drawing: source.drawing, preview: {kind: 'line', start: {x: 100, y: 120}, end: {x: 120, y: 120}}});
  assert.ok(markup.includes('x1="100.0000"'));
  assert.equal(JSON.stringify(source), before);
});


test('multiple selection highlights without modifying document geometry', () => {
  const source = info(2), before = JSON.stringify(source.document);
  const markup = sceneMarkup(source.document, {drawing: source.drawing, selection: new Set(['atom:0', 'atom:1'])});
  assert.equal((markup.match(/fill="#d6ece7"/g) ?? []).length, 2);
  assert.equal(JSON.stringify(source.document), before);
});


test('dotted bonds display native circles without inventing spacing', () => {
  const source = info(2);
  source.document.state.model.bonds = [{a:0, b:1, style:'dotted', color:'#123456'}];
  source.drawing.bonds[0] = [{dots:[[31,40],[34,40]], radius:0.87}];
  const before = JSON.stringify(source);
  const markup = sceneMarkup(source.document, {drawing:source.drawing});
  assert.ok(markup.includes('<circle cx="31.0000" cy="40.0000" r="0.8700" fill="#123456" stroke="none"/>'));
  assert.ok(markup.includes('<circle cx="34.0000" cy="40.0000" r="0.8700" fill="#123456" stroke="none"/>'));
  assert.equal(JSON.stringify(source), before);
});


test('atom hit circles use the native radius supplied with the scene', () => {
  const source = info(1);
  source.drawing.atom_pick_radius = 12.8;
  const markup = sceneMarkup(source.document, {drawing: source.drawing});
  assert.ok(markup.includes('r="12.8000" fill="transparent"'));
});
