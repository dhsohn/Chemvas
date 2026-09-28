import test from 'node:test';
import assert from 'node:assert/strict';
import {SessionClient} from '../app/chemvas/web/transport.mjs';
import {sceneMarkup, measureAtomLabels, AtomLabelCache, zoomView, wheelView, pointInSheet} from '../app/chemvas/web/scene.mjs';

function info(count = 0) {
  const atoms = Object.fromEntries(Array.from({length: count}, (_, id) => [id, {element: id ? 'O' : 'C', x: 30 + 20 * id, y: 40, explicit_label: false, color: '#000000'}]));
  return {drawing: {atom_labels:Object.fromEntries(Object.entries(atoms).filter(([, a]) => a.element !== "C").map(([id, a]) => [id, a.element])), atom_layouts: {}, label_measurements: {family: 'Arial', queries: []}, bonds:{}, line_width:1.5, font_size:12, atom_pick_radius:6.4}, unsupported: [], sheet: [595, 842], document: {type: 'chemvas', version: 9, state: {model: {atoms, bonds: [], next_atom_id: count}, arrows: [], notes: [], settings: {bond_length_px: 20, text_font_family: 'Arial', text_font_size: 12, text_color: '#222222'}}}};
}

test('transport sends revisions and only mirrors accepted server state', async () => {
  const calls = [];
  let response = {...info(), session: 'test', revision: 1, dirty: false, can_undo: false, can_redo: true};
  const editor = new SessionClient(async request => { calls.push(request); if (request.action === 'edit') throw Object.assign(new Error('Rejected'), {status: 400}); return response; });
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
  assert.equal(calls.length, 3);
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
  source.drawing.atom_layouts[0] = [{text: '<script>alert(1)</script>', size: 12, x: 30, y: 40}];
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


test('a lost edit response refreshes the committed state without repeating the edit', async () => {
  const calls = [];
  let server = {...info(), session: 'live', revision: 1, can_undo: false, name: 'Work.chemvas'};
  const editor = new SessionClient(async request => {
    calls.push(request);
    if (request.action === 'edit') {
      server = {...server, ...info(2), revision: 2, can_undo: true, dirty: true};
      throw new Error('Connection lost');
    }
    if (request.action === 'undo') server = {...server, ...info(), revision: 3, can_undo: false, dirty: false};
    return server;
  });
  await editor.load(info(), 'Work.chemvas');
  await assert.rejects(editor.perform({kind: 'bond'}), /refreshed/);
  assert.equal(editor.info.revision, 2);
  assert.equal(Object.keys(editor.document.state.model.atoms).length, 2);
  assert.equal(editor.canUndo, true);
  assert.equal(editor.dirty, true);
  assert.deepEqual(calls.map(call => call.action), ['load', 'edit', 'read']);
  await editor.undo();
  assert.equal(calls.at(-1).revision, 2);
  assert.equal(editor.dirty, false);
});

test('failed resynchronization makes the next action reconnect without mutating', async () => {
  let offline = false;
  const calls = [];
  const server = {...info(), session: 'live', revision: 1, name: 'Work.chemvas'};
  const editor = new SessionClient(async request => {
    calls.push(request);
    if (offline) throw new Error('Offline');
    return server;
  });
  await editor.load(info());
  offline = true;
  await assert.rejects(editor.perform({kind: 'ring'}), /could not be refreshed/);
  assert.equal(editor.busy, false);
  offline = false;
  await assert.rejects(editor.perform({kind: 'ring'}), /Connection restored/);
  assert.deepEqual(calls.map(call => call.action), ['load', 'edit', 'read', 'read']);
  await editor.perform({kind: 'ring'});
  assert.equal(calls.at(-1).action, 'edit');
  assert.equal(calls.at(-1).revision, 1);
});

test('a lost replacement response restores both the document and its name', async () => {
  let server = {...info(), session: 'live', revision: 1, name: 'Old.chemvas'};
  let replacing = false;
  const editor = new SessionClient(async request => {
    if (request.action === 'load' && replacing) {
      server = {...server, ...info(3), revision: 2, name: request.name};
      throw new Error('Response lost');
    }
    return server;
  });
  await editor.load(info(), 'Old.chemvas');
  replacing = true;
  await assert.rejects(editor.load(info(3), 'New.chemvas'), /refreshed/);
  assert.equal(editor.name, 'New.chemvas');
  assert.equal(Object.keys(editor.document.state.model.atoms).length, 3);
});


test('labels display positioned native runs without reparsing their text', () => {
  const source = info(1);
  source.drawing.atom_layouts[0] = [{text: 'NH', size: 12, pixels: 16, x: 100, y: 110}, {text: '2', size: 8.64, pixels: 12, x: 124, y: 113}];
  const markup = sceneMarkup(source.document, {drawing: source.drawing});
  assert.ok(markup.includes('x="124.0000" y="113.0000"'));
  assert.ok(markup.includes('font-size="12.0000"'));
  assert.ok(markup.includes('>NH</text>'));
  assert.ok(markup.includes('>2</text>'));
});

test('font measurement uses the native resolved pixel size', () => {
  const context = {font: '', measureText: text => ({width: text.length * 7, fontBoundingBoxAscent: 12, fontBoundingBoxDescent: 4, actualBoundingBoxAscent: 11})};
  const measured = measureAtomLabels({family: 'Arial', queries: [{key: '12:NH', text: 'NH', size: 12, pixels: 16}]}, context, () => 18);
  assert.equal(context.font, '16px "Arial"');
  assert.deepEqual(measured['12:NH'], {width: 14, ascent: 12, descent: 4, cap_height: 11, line_height: 18});
});


test('stale revisions and server failures resync while plain rejections do not', async () => {
  for (const status of [400, 409, 500]) {
    const calls = [];
    const state = {...info(), session: 'live', revision: 1};
    const editor = new SessionClient(async request => {
      calls.push(request.action);
      if (request.action === 'edit') throw Object.assign(new Error('Rejected'), {status});
      return state;
    });
    await editor.load(info());
    await assert.rejects(editor.perform({}), status === 400 ? /^Error: Rejected$/ : /refreshed/);
    assert.deepEqual(calls, status === 400 ? ['load', 'edit'] : ['load', 'edit', 'read']);
  }
});

const navigation = {min: .2, max: 5, step: 1.25, wheel_base: 1.0015, angle_per_pixel: 2};

test('plain wheel pans at the current scale and preserves fractional trackpad input', () => {
  const view = {x: 50, y: 30, width: 400, height: 300};
  const next = wheelView(view, {width: 800, height: 600}, {deltaX: 1.5, deltaY: -3.5, deltaMode: 0}, navigation, 18);
  assert.deepEqual(next, {x: 50.75, y: 28.25, width: 400, height: 300});
  assert.deepEqual(view, {x: 50, y: 30, width: 400, height: 300});
  assert.deepEqual(wheelView(view, {width: 800, height: 600}, {deltaX: 1, deltaY: -2, deltaMode: 1}, navigation, 18), {x: 59, y: 12, width: 400, height: 300});
  assert.deepEqual(wheelView(view, {width: 800, height: 600}, {deltaX: 1, deltaY: -1, deltaMode: 2}, navigation, 18), {x: 450, y: -270, width: 400, height: 300});
});

test('cursor zoom preserves its scene point, including SVG letterboxing', () => {
  const view = {x: 20, y: 40, width: 400, height: 400}, viewport = {width: 800, height: 400};
  const event = {deltaX: 0, deltaY: -60, deltaMode: 0, ctrlKey: true, position: {x: 100, y: 70}};
  const next = wheelView(view, viewport, event, navigation, 18);
  const scale = viewport.width / next.width;
  assert.ok(Math.abs(scale - 1.0015 ** 120) < 1e-12);
  assert.ok(Math.abs(next.x + 100 / scale - (-80)) < 1e-12);
  assert.ok(Math.abs(next.y + 70 / scale - 110) < 1e-12);
  const back = wheelView(next, viewport, {...event, deltaY: 60}, navigation, 18);
  assert.ok(Math.abs(back.x - (-180)) < 1e-12);
  assert.ok(Math.abs(back.width - 800) < 1e-12);
  assert.equal(wheelView(view, viewport, {...event, deltaY: 0}, navigation, 18), view);
});

test('zoom clamps to native magnification limits and buttons keep the center', () => {
  const view = {x: 0, y: 0, width: 800, height: 600}, viewport = {width: 800, height: 600};
  const enlarged = zoomView(view, viewport, 1 / navigation.step, navigation);
  assert.deepEqual(enlarged, {x: 80, y: 60, width: 640, height: 480});
  for (const [factor, expected] of [[1e-100, 5], [1e100, .2]]) {
    const next = zoomView(view, viewport, factor, navigation);
    assert.equal(800 / next.width, expected);
    assert.equal(next.x + next.width / 2, 400);
    assert.equal(next.y + next.height / 2, 300);
  }
});


test('label cache reuses metrics and native placements while translating moved atoms', async () => {
  const cache = new AtomLabelCache(), source = info(2), calls = [], measured = [];
  const spec = {family: 'Arial', size: 12, offset: 0, labels: {0: ['NH2', 'N', false, null], 1: ['NH2', 'N', false, null]}, queries: [{key: '12:NH', text: 'NH', size: 12, pixels: 16}]};
  const context = {font: '', measureText: text => { measured.push(text); return {width: 20, fontBoundingBoxAscent: 12, fontBoundingBoxDescent: 4, actualBoundingBoxAscent: 11}; }};
  let reject = false;
  const send = async payload => {
    calls.push(payload);
    if (reject) throw new Error('Connection lost');
    return payload.labels.map(() => [{text: 'NH', pixels: 16, size: 12, x: -5, y: 6}]);
  };
  const first = await cache.resolve(source.document, spec, context, () => 18, send);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].labels.length, 1);
  assert.equal(Object.hasOwn(calls[0], 'document'), false);
  assert.equal(first[0][0].x, 25);
  assert.equal(first[1][0].x, 45);
  source.document.state.model.atoms[0].x += 17;
  const moved = await cache.resolve(source.document, spec, context, () => 18, send);
  assert.equal(calls.length, 1);
  assert.equal(measured.length, 2); // Text and capital-height probe, once.
  assert.equal(moved[0][0].x, 42);
  spec.labels[0] = ['NH2', 'N', false, true];
  reject = true;
  await assert.rejects(cache.resolve(source.document, spec, context, () => 18, send), /Connection lost/);
  reject = false;
  await cache.resolve(source.document, spec, context, () => 18, send);
  assert.equal(calls.length, 3); // Failed placements are never cached.
  assert.equal(calls[2].labels.length, 1);
  assert.equal(measured.length, 2);
  await cache.resolve(source.document, {...spec, family: 'Helvetica'}, context, () => 18, send);
  assert.equal(calls.length, 4);
  assert.equal(measured.length, 4);
  await cache.resolve(source.document, {...spec, labels: {}, queries: []}, context, () => 18, send);
  await cache.resolve(source.document, spec, context, () => 18, send);
  assert.equal(calls.length, 5); // The discarded drawing does not retain old layouts.
});


test('macOS Command wheel zooms while other platforms retain Control and pinch', () => {
  const view = {x: 0, y: 0, width: 800, height: 600}, viewport = {width: 800, height: 600};
  const event = {deltaX: 0, deltaY: -60, deltaMode: 0, ctrlKey: false, metaKey: true, position: {x: 100, y: 100}};
  const mac = wheelView(view, viewport, event, {...navigation, zoom_modifier: 'meta'}, 18);
  assert.ok(mac.width < view.width);
  assert.deepEqual(wheelView(view, viewport, event, {...navigation, zoom_modifier: 'control'}, 18), {...view, y: -60});
  assert.deepEqual(wheelView(view, viewport, {...event, metaKey: false, ctrlKey: true}, {...navigation, zoom_modifier: 'meta'}, 18), mac);
});

test('sheet pointer bounds use the native centered coordinates and inclusive edges', () => {
  for (const [width, height] of [[842, 595], [595, 842], [850.3937007874, 510.2362204724]]) {
    for (const [x, y] of [[0, 0], [-100, -100], [-width / 2, -height / 2], [width / 2, height / 2]]) {
      assert.equal(pointInSheet({x, y}, [width, height]), true);
    }
    for (const [x, y] of [[-width / 2 - .001, 0], [width / 2 + .001, 0], [0, -height / 2 - .001], [0, height / 2 + .001]]) {
      assert.equal(pointInSheet({x, y}, [width, height]), false);
    }
  }
});
