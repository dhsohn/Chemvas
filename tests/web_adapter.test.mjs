import test from 'node:test';
import assert from 'node:assert/strict';
import {SessionClient, sessionDrawing} from '../app/chemvas/web/transport.mjs';
import {ChemistryClipboard, copySelection, isSelectionText, pasteText, writeSelection} from '../app/chemvas/web/clipboard.mjs';
import {sceneMarkup, measureAtomLabels, AtomLabelCache, clampView, zoomView, wheelView, pointInSheet, measureGlyphInk, marqueeSelection, measureDocumentLineHeight, selectionFrameMarkup, gridMarkup} from '../app/chemvas/web/scene.mjs';

test('document line height retains the font gap before the native ceiling', () => {
  // Recorded Chromium Arial normal-line measurements; Qt document heights are
  // 12, 14, 15, 17, 19, 23, 28 and 37 at these integer em sizes.
  const cases = [[10,11.5,12],[12,14,14],[13,15.5,15],[14,16,17],[16,18.5,19],[20,22.5,23],[24,27.5,28],[32,37,37]];
  for (const [pixels, smallBox, expected] of cases) {
    const style = {fontSize:'', set font(value) { this.fontSize = value.match(/(\d+)px/)[0]; }};
    const probe = {style, textContent:'', getBoundingClientRect() { return {height:style.fontSize === '2048px' ? 2355 : smallBox}; }};
    assert.equal(measureDocumentLineHeight(probe, `${pixels}px Arial`, 'NHBoc'), expected);
    assert.equal(probe.textContent, 'NHBoc');
  }
});

function info(count = 0) {
  const atoms = Object.fromEntries(Array.from({length: count}, (_, id) => [id, {element: id ? 'O' : 'C', x: 30 + 20 * id, y: 40, explicit_label: false, color: '#000000'}]));
  return {drawing: {selection_style:{screen_width:1.5,color:'#0d9488'},atom_labels:Object.fromEntries(Object.entries(atoms).filter(([, a]) => a.element !== "C").map(([id, a]) => [id, a.element])), atom_layouts: {}, label_measurements: {family: 'Arial', queries: [], offset: 0.25}, bonds:{}, line_width:1.5, font_size:12, atom_hit_radii:Object.fromEntries(Object.keys(atoms).map(id => [id,6.4]))}, unsupported: [], sheet: [595, 842], document: {type: 'chemvas', version: 9, state: {model: {atoms, bonds: [], next_atom_id: count}, arrows: [], notes: [], settings: {bond_length_px: 20, text_font_family: 'Arial', text_font_size: 12, text_color: '#222222'}}}};
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
  assert.ok(!svg.includes('paint-order') && !svg.includes('stroke="white"'));
});

test('drag preview never mutates the committed document', () => {
  const source = info(1), before = JSON.stringify(source);
  const markup = sceneMarkup(source.document, {drawing: source.drawing, preview: {kind: 'line', start: {x: 100, y: 120}, end: {x: 120, y: 120}}});
  assert.ok(markup.includes('x1="100.0000"'));
  assert.equal(JSON.stringify(source), before);
});


test('multiple selection highlights without modifying document geometry', () => {
  const source = info(2), before = JSON.stringify(source.document);
  const markup = sceneMarkup(source.document, {drawing: source.drawing, selection: new Set(['atom:0', 'atom:1']), components:[[{rect:[23.6,33.6,12.8,12.8]}],[{rect:[43.6,33.6,12.8,12.8]}]]});
  assert.equal((markup.match(/<filter /g) ?? []).length, 2);
  assert.ok(!markup.includes('#d6ece7'));
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
  source.drawing.atom_hit_radii[0] = 12.8;
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
  const context = {font: '', measureText: text => ({width: text.length * 7, fontBoundingBoxAscent: 12, fontBoundingBoxDescent: 4, actualBoundingBoxAscent: 11, actualBoundingBoxLeft: 1, actualBoundingBoxRight: 12})};
  const measured = measureAtomLabels({family: 'Arial', queries: [{key: '12:NH', text: 'NH', size: 12, pixels: 16}]}, context, () => 18);
  assert.equal(context.font, '16px "Arial"');
  assert.deepEqual(measured['12:NH'], {width: 14, bounding_width: 13, ascent: 12, descent: 4, cap_height: 11, line_height: 18});
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


function rasterContext() {
  return {
    canvas: {width: 0, height: 0}, font: '', paints: 0,
    measureText: () => ({width:4,fontBoundingBoxAscent:4,fontBoundingBoxDescent:1,actualBoundingBoxLeft: 1, actualBoundingBoxRight: 3, actualBoundingBoxAscent: 4, actualBoundingBoxDescent: 1}),
    setTransform(...values) { this.transform = values; },
    fillText() { this.paints++; this.painted = this.transform; },
    getImageData(x, y, width, height) {
      const data = new Uint8ClampedArray(width * height * 4);
      const [, , , , ox, oy] = this.painted;
      data[(Math.floor(oy) * width + Math.floor(ox)) * 4 + 3] = 255;
      return {data};
    },
  };
}

test('browser ink sampling returns baseline-relative pixel edges and bounds raster size', () => {
  const context = rasterContext();
  assert.deepEqual(measureGlyphInk(context, 'Arial', {text: 'O', pixels: 16}), [[0,0],[.125,0],[0,.125],[.125,.125]]);
  assert.deepEqual(context.transform, [1,0,0,1,0,0]);
  context.measureText = () => ({actualBoundingBoxLeft: 0, actualBoundingBoxRight: 1e7, actualBoundingBoxAscent: 1e6, actualBoundingBoxDescent: 0});
  measureGlyphInk(context, 'Arial', {text: 'large', pixels: 1e6});
  assert.ok(context.canvas.width <= 2048 && context.canvas.height <= 512);
});

test('glyph coverage excludes antialias fringes and retains half-covered thin strokes', () => {
  const context = rasterContext();
  context.getImageData = function(x, y, width, height) {
    const data = new Uint8ClampedArray(width * height * 4);
    const [, , , , ox, oy] = this.painted;
    for (const [dx, alpha] of [[-2, 1], [-1, 127], [0, 128], [1, 127], [2, 1]]) {
      data[((oy * width) + ox + dx) * 4 + 3] = alpha;
    }
    // A separate row with no half-covered pixels must not contribute any ink.
    data[((oy + 1) * width + ox) * 4 + 3] = 127;
    return {data};
  };
  assert.deepEqual(measureGlyphInk(context, 'Arial', {text: 'I', pixels: 16}), [[0,0],[.125,0],[0,.125],[.125,.125]]);
});

test('hinted raster edges stay within the font engine ink bounds, including negative bearings', () => {
  const context = rasterContext();
  context.measureText = () => ({actualBoundingBoxLeft: -.3, actualBoundingBoxRight: 3.7, actualBoundingBoxAscent: 4.1, actualBoundingBoxDescent: .9});
  context.getImageData = (x, y, width, height) => ({data: new Uint8ClampedArray(width * height * 4).fill(255)});
  const points = measureGlyphInk(context, 'Arial', {text: 'N', pixels: 16});
  assert.equal(Math.min(...points.map(p => p[0])), .3);
  assert.equal(Math.max(...points.map(p => p[0])), 3.7);
  assert.equal(Math.min(...points.map(p => p[1])), -4.1);
  assert.equal(Math.max(...points.map(p => p[1])), .9);
  context.getImageData = (x, y, width, height) => ({data: new Uint8ClampedArray(width * height * 4)});
  assert.deepEqual(measureGlyphInk(context, 'Arial', {text: ' ', pixels: 16}), []);
  assert.deepEqual(context.transform, [1,0,0,1,0,0]);
});

test('font cache reuses metrics and ink across layouts, bounds retention and invalidates fonts', () => {
  const cache = new AtomLabelCache(), context = rasterContext();
  const spec = {family:'Arial', queries:[{key:'12:O',text:'O',size:12,pixels:16}]};
  const first = cache.measure(spec, context, () => 18);
  assert.equal(context.paints, 1);
  assert.deepEqual(cache.measure(spec, context, () => 18), first);
  assert.equal(context.paints, 1);
  assert.equal(Object.hasOwn(first, 'document'), false);
  assert.deepEqual(Object.keys(first.ink), ['16:O']);
  cache.measure({...spec,family:'Helvetica'}, context, () => 18);
  assert.equal(context.paints, 2);
  assert.deepEqual(cache.measure({family:'Helvetica',queries:[]}, context, () => 18), {family:'Helvetica',metrics:{},ink:{}});
  cache.measure(spec, context, () => 18);
  assert.equal(context.paints, 3);
});

test('collapsed native bond lines do not become SVG round-cap dots', () => {
  const source = info(2);
  source.document.state.model.bonds = [{a:0,b:1,style:'single',color:'#123456'}];
  source.drawing.bonds[0] = [{line:[30,40,30,40]}];
  const markup = sceneMarkup(source.document, {drawing:source.drawing});
  assert.ok(!markup.includes('x1="30.0000" y1="40.0000" x2="30.0000" y2="40.0000"'));
});


test('label hit shape uses supplied ink bounds and the native offset anchor circle', () => {
  const source = info(1);
  source.drawing.atom_layouts[0] = [{text: 'Cl', pixels: 16, x: 30, y: 40}];
  source.drawing.atom_hit_rects = {0: [20, 32, 27, 18]};
  const markup = sceneMarkup(source.document, {drawing: source.drawing});
  assert.ok(markup.includes('<rect x="20.0000" y="32.0000" width="27.0000" height="18.0000" fill="transparent" pointer-events="all"/>'));
  assert.ok(markup.includes('<circle cx="30.2500" cy="39.7500" r="6.4000" fill="transparent"'));
  assert.ok(markup.includes('pointer-events="none">Cl</text>'));
});


for (const action of ['edit','load','undo','redo','read','preview']) {
  test(`${action}: only missing fonts require a measurement request, with no document upload or edit replay`, async () => {
    const calls = [], edit = {kind:'move',dx:20,dy:0,selection:[]};
    const spec = {family:'Arial',queries:[]};
    const complete = {...info(2),session:'one',revision:9};
    let missing = true;
    const send = async request => {
      calls.push(request);
      if (request.action === 'measure') { missing = false; return complete; }
      return {...complete, shortcut_tool:'bond', drawing:missing ? {needs_measurements:true,label_measurements:spec} : complete.drawing};
    };
    const request = {session:'one',revision:8,action,edit};
    const result = await sessionDrawing(request,send,value => { assert.equal(value,spec); return {metrics:{},ink:{}}; });
    assert.deepEqual(calls.map(c => c.action), [action,'measure']);
    assert.equal(calls[1].revision,9);
    assert.equal(Object.hasOwn(calls[1],'document'),false);
    assert.equal(Object.hasOwn(calls[1],'edit'),action === 'preview');
    assert.equal(result.shortcut_tool,'bond');
    await sessionDrawing(request,send,() => assert.fail('A known font must not be measured again'));
    assert.equal(calls.length,3);
  });
}

test('a failed first-load font completion retains its session for read-only recovery', async () => {
  const calls = [], complete = {...info(1),session:'new-window',revision:1};
  let offline = true;
  const send = async request => {
    calls.push(request);
    if (request.action === 'load') return {...complete,drawing:{needs_measurements:true,label_measurements:{}}};
    if (offline) throw new Error('Font request lost');
    return complete;
  };
  const client = new SessionClient(request => sessionDrawing(request,send,() => ({})));
  await assert.rejects(client.load(info(1)),/could not be refreshed/);
  assert.equal(client.document,null);
  offline = false;
  await assert.rejects(client.load(info()),/Connection restored/);
  assert.deepEqual(calls.map(c => c.action),['load','measure','read','read']);
  assert.equal(calls.at(-1).session,'new-window');
  assert.equal(client.document,complete.document);
});

test('malformed font completion is not retried in an unbounded request loop', async () => {
  const calls = [];
  await assert.rejects(sessionDrawing({action:'edit'},async request => {
    calls.push(request);
    return {session:'one',revision:2,drawing:{needs_measurements:true,label_measurements:{}}};
  },() => ({})),error => error.uncertain && error.session === 'one');
  assert.deepEqual(calls.map(c => c.action),['edit','measure']);
});


test('noncompact labels have an ink rectangle without an anchor circle', () => {
  const source = info(1);
  source.drawing.atom_layouts[0] = [{text:'CO2Me',pixels:16,x:30,y:40}];
  source.drawing.atom_hit_rects = {0:[20,32,27,18]};
  source.drawing.atom_hit_radii[0] = null;
  const markup = sceneMarkup(source.document,{drawing:source.drawing});
  assert.ok(markup.includes('<rect'));
  assert.ok(!markup.includes('<circle'));
  const selected = sceneMarkup(source.document,{drawing:source.drawing,selection:new Set(['atom:0'])});
  assert.ok(!selected.includes('<circle')); // Selection geometry comes from the native owner.
});


test('arrow SVG consumes native path commands, pens and curved hit geometry', () => {
  const source = info();
  source.document.state.arrows = [{kind:'curved_single',start:[0,0],end:[60,0]}];
  source.drawing.arrows = [{path:[['M',[0,0]],['Q',[30,-25,60,0]],['M',[55,-3]],['L',[60,0]],['L',[54,4]]],width:2.5,selection_width:6.1,dashed:true,cap:'round',join:'round',color:'#123456'}];
  const markup = sceneMarkup(source.document, {drawing:source.drawing,selection:new Set(['arrow:0'])});
  assert.ok(markup.includes('Q30.0000 -25.0000 60.0000 0.0000'));
  assert.ok(markup.includes('stroke="#123456" stroke-width="2.5000" stroke-linecap="round" stroke-linejoin="round"'));
  assert.ok(markup.includes('stroke-dasharray="10.0000 5.0000"'));
  assert.equal((markup.match(/Q30.0000 -25.0000 60.0000 0.0000/g) ?? []).length, 4);
  assert.ok(markup.includes('pointer-events="none"'));
  assert.ok(markup.includes('pointer-events="stroke"'));
  assert.ok(markup.includes('stroke="transparent" pointer-events="stroke"'));
  assert.ok(!markup.includes('stroke-width="8"'));
  assert.ok(!markup.includes('<line'));
  source.drawing.arrows[0] = {path:[],width:6.6,dashed:false,cap:'butt',join:'miter',color:'#222222'};
  const empty = sceneMarkup(source.document, {drawing:source.drawing});
  assert.ok(empty.includes('stroke-width="6.6000" stroke-linecap="butt" stroke-linejoin="miter"'));
  assert.ok(!empty.includes('stroke-dasharray'));
  assert.ok(empty.includes('d=""'));
});


test('bond graphics expose painted hits without an artificial eight-unit pick stroke', () => {
  const source = info(2);
  source.document.state.model.bonds = [{a:0,b:1,style:'single',color:'#000000'}];
  source.drawing.bonds = {0:[{line:[30,40,50,40]}]};
  const markup = sceneMarkup(source.document, {drawing:source.drawing,selection:new Set(['bond:0']),components:[[{line:[30,40,50,40],width:5}]]});
  assert.ok(!markup.includes('stroke-width="8"'));
  assert.ok(markup.includes('<g pointer-events="none"><filter'));
  assert.ok(!markup.includes('opacity="0.2"'));
});

test('arrow handles keep native screen size and snapped fill without changing records', () => {
  const source = info();
  source.document.state.arrows = [{kind:'arrow', start:[10,20], end:[100,50]}];
  source.drawing.arrows = [{path:[['M',[10,20]],['L',[100,50]]], width:1.5, color:'#123456', cap:'round', join:'round', handles:[
    {handle:'start', point:[10,20], snapped:false}, {handle:'end', point:[100,50], snapped:true},
  ]}];
  const before = JSON.stringify(source);
  for (const scale of [0.25,1,4]) {
    const svg = sceneMarkup(source.document, {drawing:source.drawing,handleTarget:'arrow:0',handleStyle:{size:8,color:'#0d9488'},scale});
    assert.equal((svg.match(/data-handle=/g) ?? []).length,2);
    assert.ok(svg.includes(`r="${(4/scale).toFixed(4)}" fill="#ffffff"`));
    assert.ok(svg.includes(`r="${(4/scale).toFixed(4)}" fill="#0d9488"`));
    assert.ok(svg.includes('vector-effect="non-scaling-stroke"'));
  }
  assert.ok(!sceneMarkup(source.document, {drawing:source.drawing}).includes('data-handle='));
  assert.equal(JSON.stringify(source),before);
});

test('drawing snap rings keep native screen size and take no pointer input', () => {
  const source = info(), before = JSON.stringify(source);
  const snapMarkStyle = {size:16, width:1.6, color:'#00a3ff'};
  const options = snapMarks => ({drawing:source.drawing, snapMarks, snapMarkStyle, scale:2});
  const svg = sceneMarkup(source.document, options([[100,100]]));
  const rings = [...svg.matchAll(/<circle\b[^>]*\bdata-snap-mark\b[^>]*>/g)].map(([tag]) =>
    Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(([, name, value]) => [name, value])));
  assert.equal(rings.length, 1);
  const [ring] = rings;
  assert.deepEqual([Number(ring.cx), Number(ring.cy), Number(ring.r)], [100, 100, 4]);
  assert.equal(Number(ring['stroke-width']), 0.8);
  assert.equal(ring.stroke, '#00a3ff');
  assert.equal(ring.fill, 'none');
  assert.equal(ring['pointer-events'], 'none');
  assert.ok(!('data-item' in ring) && !('data-handle' in ring));
  for (const snapMarks of [undefined, []]) assert.ok(!sceneMarkup(source.document, options(snapMarks)).includes('data-snap-mark'));
  assert.equal(JSON.stringify(source), before);
});

test('drawing snap rings keep screen size at every zoom and escape their colour', () => {
  const source = info(), before = JSON.stringify(source);
  const draw = (scale, color = '#00a3ff') => sceneMarkup(source.document, {drawing:source.drawing, snapMarks:[[10,20],[30,40]], snapMarkStyle:{size:16, width:1.6, color}, scale});
  for (const scale of [0.25, 1, 2]) {
    const svg = draw(scale);
    assert.equal((svg.match(/data-snap-mark/g) ?? []).length, 2);
    assert.ok(svg.includes(`cx="30.0000" cy="40.0000" r="${(8 / scale).toFixed(4)}" fill="none"`), String(scale));
    assert.ok(svg.includes(`stroke-width="${(1.6 / scale).toFixed(4)}"`), String(scale));
  }
  for (const scale of [0, -1, NaN, Infinity]) assert.ok(!draw(scale).includes('data-snap-mark'), String(scale));
  const escaped = draw(1, '"><script>');
  assert.ok(escaped.includes('stroke="&quot;&gt;&lt;script&gt;"') && !escaped.includes('<script>'));
  assert.equal(JSON.stringify(source), before);
});

test('arrow labels use measured native placements and remain arrow hit targets', () => {
  const source = info();
  source.document.state.arrows = [{kind:'arrow', start:[0,0], end:[100,0], labels:{above:'K_{2}CO_{3}'}}];
  source.drawing.arrows = [{path:[['M',[0,0]],['L',[100,0]]],color:'#222',width:1,cap:'round',join:'round'}];
  source.drawing.arrow_labels = [{id:0,side:'above',x:24,y:-32,width:52,height:27,html:'K<sub>2</sub>CO<sub>3</sub>'}];
  const before = structuredClone(source);
  const markup = sceneMarkup(source.document, {drawing:source.drawing});
  assert.match(markup, /<foreignObject data-item="arrow:0" x="24.0000" y="-32.0000" width="52.0000" height="27.0000">/);
  assert.match(markup, /data-arrow-label="0:above">K<sub>2<\/sub>CO<sub>3<\/sub>/);
  assert.doesNotMatch(markup, /text-anchor="middle"|K_\{2\}/);
  assert.deepEqual(source,before);
});

test('native shape primitives retain invisible interior hits and preview-only guide', () => {
  const source = info();
  source.drawing.shapes = [{kind:'rect',x:10,y:20,width:80,height:50,radius:14,stroke:'none',line_width:1.4,color:'#222',fill:null,alpha:null}];
  const before = structuredClone(source);
  const markup = sceneMarkup(source.document,{drawing:source.drawing});
  assert.match(markup, /data-item="shape:0" fill="transparent".*stroke="none"/);
  assert.match(markup, /pointer-events="all".*rx="14.0000"/);
  const preview = sceneMarkup(source.document,{drawing:source.drawing,preview:{kind:'shape'}});
  assert.match(preview,/stroke="#787878"/);
  assert.match(preview,/stroke-dasharray="5.6000 2.8000"/);
  assert.deepEqual(source,before);
});

test('shape handles preserve native corner and edge screen sizes at every zoom', () => {
  const source = info();
  source.drawing.shapes = [{kind:'rect',x:0,y:0,width:80,height:50,radius:0,stroke:'solid',line_width:1.4,color:'#000000',handles:[
    {handle:'shape_nw',point:[0,0]}, {handle:'shape_n',point:[40,0]},
    {handle:'shape_ne',point:[80,0]}, {handle:'shape_e',point:[80,25]},
    {handle:'shape_se',point:[80,50]}, {handle:'shape_s',point:[40,50]},
    {handle:'shape_sw',point:[0,50]}, {handle:'shape_w',point:[0,25]},
  ]}];
  const before = JSON.stringify(source);
  for (const scale of [0.25,1,4]) {
    const svg = sceneMarkup(source.document, {drawing:source.drawing,handleTarget:'shape:0',handleStyle:{size:8,edge_size:6,color:'#0d9488'},scale});
    assert.equal((svg.match(/data-shape-id="0"/g) ?? []).length,8);
    assert.equal((svg.match(new RegExp(`r="${(4/scale).toFixed(4)}"`, 'g')) ?? []).length,4);
    assert.equal((svg.match(new RegExp(`r="${(3/scale).toFixed(4)}"`, 'g')) ?? []).length,4);
  }
  assert.equal(JSON.stringify(source),before);
  assert.ok(!sceneMarkup(source.document,{drawing:source.drawing}).includes('data-handle='));
});

test('shape stacking follows native depths with stable ties and handles above content', () => {
  const source = info(2);
  source.document.state.model.bonds = [{a:0,b:1,color:'#000000'}];
  source.drawing.bonds = {0:[{line:[30,40,50,40]}]};
  source.document.state.arrows = [{kind:'arrow',start:[0,0],end:[80,0]}];
  source.drawing.arrows = [{path:[['M',[0,0]],['L',[80,0]]],width:1.5,color:'#000000',cap:'round',join:'round',handles:[]}];
  for (const z of [-12,-10,-0.01,0,2,3,4,10]) {
    const shape = {kind:'rect',x:0,y:0,width:80,height:50,radius:0,stroke:'solid',line_width:1.4,color:'#000000',z,handles:[{handle:'shape_n',point:[40,0]}]};
    source.drawing.shapes = [shape,{...shape}];
    const svg = sceneMarkup(source.document,{drawing:source.drawing,handleTarget:'shape:0',handleStyle:{size:8,edge_size:6,color:'#008080'}});
    const first = svg.indexOf('data-item="shape:0"'), second = svg.indexOf('data-item="shape:1"');
    assert.ok(first < second);
    assert.equal(first > svg.indexOf('data-item="arrow:0"'),z >= 0);
    assert.equal(first > svg.indexOf('data-item="bond:0"'),z >= 0);
    assert.equal(first > svg.indexOf('data-item="atom:0"'),z >= 3);
    assert.ok(svg.indexOf('data-handle="shape_n"') > second);
  }
});

test('font completion retains the native color notice without replaying the edit', async () => {
  const calls = [];
  const result = await sessionDrawing({action:'edit'},async request => {
    calls.push(request.action);
    return request.action === 'edit'
      ? {...info(),session:'color-test',revision:1,edit_notice:'Hidden carbon',drawing:{needs_measurements:true,label_measurements:{}}}
      : {...info(),session:'color-test',revision:1};
  }, () => ({}));
  assert.equal(result.edit_notice,'Hidden carbon');
  assert.deepEqual(calls,['edit','measure']);
});


test('transparent and filled ring interiors remain interactive below bonds', () => {
  for (const color of [null, '#f5d2ce']) {
    const source = info(2);
    source.document.state.ring_fills = [{atom_ids:[0,1], points:[[20,20],[60,20],[40,60]], color, alpha:color ? 1 : 0}];
    const markup = sceneMarkup(source.document, {drawing:source.drawing});
    assert.ok(markup.includes('data-item="ring:0"'));
    assert.ok(markup.includes('pointer-events="all"'));
    assert.ok(markup.includes(`fill="${color ?? 'transparent'}"`));
    assert.ok(markup.indexOf('data-item="ring:0"') < markup.indexOf('data-item="atom:0"'));
  }
});


test('marquee delegates geometry to SVG and preserves additive selection without mutating its base', () => {
  const calls = [], drawing = {}, base = ['atom:9'];
  const svg = {
    getCTM: () => ({a:2,b:0,c:0,d:2,e:10,f:20}),
    createSVGRect: () => ({}), querySelector: selector => { assert.equal(selector, '#drawing'); return drawing; },
    getIntersectionList: (rect, root) => {
      calls.push(rect); assert.equal(root, drawing);
      return ['bond:0', 'bond:0', 'ring:0', 'shape:1', 'arrow:2', 'mark:3', 'note:0', null].map(key => ({closest: () => key && ({dataset:{item:key}})}));
    },
  };
  const start = {x:40,y:30}, end = {x:10,y:5};
  assert.deepEqual([...marqueeSelection(svg,start,end,base,true)], ['atom:9','bond:0','ring:0','shape:1','arrow:2','mark:3','note:0']);
  assert.deepEqual([...marqueeSelection(svg,end,start,base)], ['bond:0','ring:0','shape:1','arrow:2','mark:3','note:0']);
  assert.deepEqual(calls, [{x:30,y:30,width:60,height:50},{x:30,y:30,width:60,height:50}]);
  assert.deepEqual(base, ['atom:9']);
  assert.deepEqual([...marqueeSelection(svg,start,start,base)], []);
  assert.equal(calls.length, 2);
});

test('marquee preview remains a noninteractive overlay and leaves document untouched', () => {
  const source = info(2), before = JSON.stringify(source);
  const markup = sceneMarkup(source.document, {drawing:source.drawing, preview:{kind:'marquee',start:{x:40,y:30},end:{x:10,y:5}}});
  assert.ok(markup.includes('x="10.0000" y="5.0000" width="30.0000" height="25.0000"'));
  assert.ok(markup.includes('fill="Highlight" fill-opacity="0.12"'));
  assert.ok(markup.includes('vector-effect="non-scaling-stroke" pointer-events="none"'));
  assert.equal(JSON.stringify(source), before);
});

test('unsupported marquee geometry is distinct from an empty selection and never calls SVG geometry', () => {
  const base = ['atom:9', 'bond:2'];
  for (const getIntersectionList of [undefined, null]) {
    const svg = {getIntersectionList, getCTM: () => { throw new Error('unsupported geometry was called'); }};
    for (const additive of [false, true]) {
      assert.equal(marqueeSelection(svg, {x:0,y:0}, {x:20,y:20}, base, additive), null);
    }
  }
  assert.deepEqual(base, ['atom:9', 'bond:2']);
});

test('arrow outlines retain native subpaths, round stroke boundaries and screen width at every zoom', () => {
  const source = info();
  source.document.state.arrows = [{kind:'arrow',start:[0,0],end:[60,0]}];
  source.drawing.arrows = [{path:[['M',[0,0]],['L',[60,0]],['M',[55,-3]],['L',[60,0]],['L',[54,4]]],width:1.4,selection_width:5,color:'#222',cap:'round',join:'round'}];
  const before = structuredClone(source);
  for (const scale of [0.1,0.25,1,5]) {
    const markup = sceneMarkup(source.document,{drawing:source.drawing,selection:new Set(['arrow:0']),scale});
    assert.equal((markup.match(/<mask /g) ?? []).length,2);
    assert.ok(markup.includes(`stroke="white" stroke-width="${(5+1.5/scale).toFixed(4)}"`));
    assert.equal(markup.includes('stroke="black"'),5 > 1.5/scale);
    if (5 > 1.5/scale) assert.ok(markup.includes(`stroke="black" stroke-width="${(5-1.5/scale).toFixed(4)}"`));
    assert.ok(markup.includes('maskUnits="userSpaceOnUse" maskContentUnits="userSpaceOnUse"'));
    assert.ok(markup.indexOf('<mask ') > markup.indexOf('data-item="arrow:0"'));
    assert.ok(!markup.includes('opacity="0.2"'));
    assert.ok(markup.includes('<g pointer-events="none"><mask'));
  }
  assert.deepEqual(source,before);
  source.drawing.arrows[0].path = [];
  assert.ok(!sceneMarkup(source.document,{drawing:source.drawing,selection:new Set(['arrow:0'])}).includes('<mask'));
});

test('molecule outlines consume native component parts and keep disconnected components separate', () => {
  const source = info(2);
  const components = [[{line:[-20,0,20,0],width:5},{shape:{polygon:[[20,0],[30,-3],[30,3]]}},{shape:{dots:[[31,0],[35,0]],radius:1}}],[{rect:[40,20,12.8,12.8]}]];
  const before = structuredClone(components);
  for (const scale of [0.2,1,5]) {
    const markup = sceneMarkup(source.document,{drawing:source.drawing,components,scale});
    assert.equal((markup.match(/<filter /g) ?? []).length,2);
    assert.equal((markup.match(/operator="dilate"/g) ?? []).length,2);
    assert.equal((markup.match(/operator="erode"/g) ?? []).length,2);
    assert.ok(markup.includes(`radius="${(0.75/scale).toFixed(4)}"`));
    assert.ok(markup.includes('rx="6.4000"'));
    assert.ok(markup.includes('<g pointer-events="none"><filter'));
    assert.ok(!markup.includes('NaN') && !markup.includes('Infinity'));
  }
  assert.deepEqual(components,before);
  assert.ok(!sceneMarkup(source.document,{drawing:source.drawing,components:[[{empty:true}]]}).includes('<filter'));
});

test('font completion keeps preview selection with its candidate instead of replaying a committed edit', async () => {
  const calls = [], selection = [{target:'atom',id:0}], edit = {kind:'move',dx:1,dy:2,selection};
  const result = await sessionDrawing({action:'preview',edit,selection},async request => {
    calls.push(request);
    return request.action === 'preview'
      ? {...info(),session:'selection-preview',revision:3,drawing:{needs_measurements:true,label_measurements:{}}}
      : {...info(),session:'selection-preview',revision:3,selection_components:[[{rect:[1,2,3,4]}]]};
  },()=>({}));
  assert.deepEqual(calls.map(request=>request.action),['preview','measure']);
  assert.deepEqual(calls[1].selection,selection);
  assert.deepEqual(calls[1].edit,edit);
  assert.deepEqual(result.selection_components,[[{rect:[1,2,3,4]}]]);
});

test('shape selection follows supplied geometry with independent outlines above stacked content', () => {
  const source = info();
  source.drawing.shapes = ['ellipse','rect'].map((kind,index) => ({kind,x:10+index*60,y:15,width:50,height:30,radius:index*8,stroke:'none',line_width:1.4,color:'#222',fill:null,alpha:0,z:12,selection:{outline:{kind,x:10+index*60,y:15,width:50,height:30,radius:index*8},width:4.8}}));
  const before = structuredClone(source);
  for (const scale of [0.1,1,5]) {
    const markup = sceneMarkup(source.document,{drawing:source.drawing,selection:new Set(['shape:0','shape:1']),components:[[{rect:[-20,-20,10,10]}]],scale});
    assert.ok(markup.includes('id="shape-selection-0"') && markup.includes('id="shape-selection-1"'));
    assert.ok(markup.includes('id="molecule-selection-0"'));
    assert.ok(markup.includes('stroke-width="4.8000" stroke-linecap="round" stroke-linejoin="round"'));
    assert.ok(markup.includes('rx="8.0000"'));
    assert.ok(markup.indexOf('id="shape-selection-0"') > markup.indexOf('data-item="shape:1"'));
    assert.ok(markup.includes(`radius="${(0.75/scale).toFixed(4)}"`));
    assert.ok(!markup.includes('NaN') && !markup.includes('Infinity'));
  }
  assert.deepEqual(source,before);
  assert.ok(!sceneMarkup(source.document,{drawing:source.drawing}).includes('shape-selection'));
  source.drawing.shapes[0].width=0;
  const markup=sceneMarkup(source.document,{drawing:source.drawing});
  assert.ok(markup.includes('d="M10.0000 15.0000 h0.0000 v30.0000 h0.0000 Z"'));
});


test('selection frames enclose supplied label bounds with screen-size rotation knobs', () => {
  const drawing = {selection_style:{color:'#0d9488',screen_width:1.5}};
  const frame = {rects:[[10,20,12,12],[5,18,40,24],[80,25,12,12]],padding:2.4};
  const original = JSON.stringify(frame);
  const handles = {rotation_stem:14,size:8,rotation_type:'selection_rotate',frame_radius:2,color:'#0d9488'};
  for (const scale of [.1,.5,1,3.05,5]) {
    const markup = selectionFrameMarkup(frame,drawing,handles,scale);
    assert.ok(markup.outline.includes('x="2.6000" y="15.6000" width="91.8000" height="28.8000"'));
    assert.ok(markup.outline.includes('pointer-events="none"'));
    assert.ok(markup.handle.includes(`cy="${(15.6-18/scale).toFixed(4)}" r="${(4/scale).toFixed(4)}"`));
    assert.ok(markup.handle.includes('data-handle="selection_rotate"') && markup.handle.includes('vector-effect="non-scaling-stroke"'));
  }
  assert.equal(JSON.stringify(frame),original);
  assert.deepEqual(selectionFrameMarkup(null,drawing,handles,1),{outline:'',handle:''});
});

test('selection frame is above outlines and rotation knob is above object handles', () => {
  const source=info(1);
  const svg=sceneMarkup(source.document,{drawing:source.drawing,components:[[{rect:[10,20,30,40]}]]});
  assert.ok(svg.indexOf('id="selection-frame"')>svg.indexOf('molecule-selection-0'));
  assert.ok(svg.indexOf('id="rotation-handle"')>svg.indexOf('id="selection-frame"'));
});


test('grid tiles keep the scene origin and cosmetic width as sheet and zoom change', () => {
  const spec = {step:0.5,minimum_spacing:6,color:'#8c8c87',tiles:{square:{size:[1,1],lines:[[0,0,0,1],[1,0,1,1],[0,0,1,0],[0,1,1,1]]}}};
  const grid = {enabled:true,style:'square',opacity:0.2};
  assert.equal(gridMarkup([842,595],{...grid,enabled:false},spec,20,1),'');
  assert.equal(gridMarkup([842,595],grid,spec,20,0.59),'');
  const atThreshold = gridMarkup([842,595],grid,spec,20,0.6);
  assert.match(atThreshold,/patternUnits="userSpaceOnUse" x="0" y="0" width="10" height="10"/);
  assert.match(atThreshold,/x="-421" y="-297.5" width="842" height="595"/);
  const zoomed = gridMarkup([100,200],grid,spec,40,2);
  assert.match(zoomed,/width="20" height="20"/);
  assert.match(zoomed,/stroke-width="0.5"/);
  assert.match(zoomed,/x="-50" y="-100" width="100" height="200"/);
});


test('imported marks expose native hit shapes and escape custom text', () => {
  const source = info();
  source.drawing.marks = [
    {id:0, hit_radius:6.4, kind:'radical', x:12, y:15, radius:1.2, color:'#123456'},
    {id:1, hit_radius:6.4, kind:'circled_plus', x:20, y:25, radius:4, stroke:0.975, extent:1.92, color:'#123456'},
    {id:2, hit_radius:6.4, kind:'circled_minus', x:30, y:35, radius:4, stroke:0.975, extent:1.92, color:'#123456'},
    {id:3, x:40, y:40, hit_radius:6.4, hit_rect:[32,35,16,10], kind:'plus', color:'#123456', runs:[{x:40, y:45, pixels:13, text:'<script>"&'}]},
    {id:4, x:50, y:40, hit_radius:6.4, kind:'minus', color:'#123456', runs:[]},
  ];
  const before = JSON.stringify(source);
  const markup = sceneMarkup(source.document, {drawing:source.drawing});
  assert.equal((markup.match(/data-mark=/g) ?? []).length, 5);
  assert.ok(markup.includes('<circle cx="12.0000" cy="15.0000" r="1.2000"/>'));
  assert.equal((markup.match(/<circle r="4.0000"/g) ?? []).length, 4);
  assert.equal((markup.match(/<line /g) ?? []).length, 6);
  assert.ok(markup.includes('stroke-width="0.9750"'));
  assert.ok(markup.includes('&lt;script&gt;&quot;&amp;'));
  assert.ok(!markup.includes('<script>') && !markup.includes('NaN'));
  assert.equal((markup.match(/data-item="mark:/g) ?? []).length, 5);
  assert.ok(markup.includes('stroke-width="4.8000" stroke-linecap="round" fill="none" pointer-events="stroke"'));
  assert.ok(markup.includes('r="6.4000" fill="transparent" pointer-events="all"'));
  assert.ok(markup.includes('x="32.0000" y="35.0000" width="16.0000" height="10.0000" fill="transparent"'));
  assert.equal(JSON.stringify(source), before);
});

// The page sources as the harnesses below slice them. A Windows checkout may
// carry CRLF line ends while the slices end at LF boundaries; JavaScript parses
// either terminator alike, so the executed production code is the same.
async function webSource(name) {
  const {readFile} = await import('node:fs/promises');
  return (await readFile(new URL(`../app/chemvas/web/${name}`, import.meta.url), 'utf8')).replaceAll('\r\n', '\n');
}

// Execute the production event bodies against a small DOM port so input ordering
// is exercised without creating a second browser implementation in the test.
async function markInputHandlers(overrides = {}) {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const handlers = {}, menu = {hidden:true,style:{},offsetWidth:100,offsetHeight:30};
  const action = {focus() {}}, mark = {dataset:{item:'mark:2'}};
  const context = {
    editor:{document:{},busy:false,readOnly:false,info:{session:'test',revision:1}},
    ui:{navigation:{zoom_modifier:'meta'}},loading:false,gesture:null,smilesInsert:null,tool:'select',
    canvas:{addEventListener:(kind, handler) => { handlers[kind] = handler; },contains:()=>true,
      focus:()=>{ throw new Error('context click reached canvas editing'); }},
    document:{elementsFromPoint:()=>[{closest:selector=>selector === '[data-handle]' ? null : mark}]},
    $:id=>id === 'mark-menu' ? menu : action,innerWidth:800,innerHeight:600,
    ...overrides,
  };
  for (const event of ['pointerdown','mousedown','contextmenu']) {
    const start = source.indexOf(`canvas.addEventListener('${event}', ${event === 'mousedown' ? 'async ' : ''}event => {`);
    assert.ok(start >= 0);
    const end = source.indexOf('\n});',start)+4;
    runInNewContext(source.slice(start,end),context);
  }
  return {handlers,menu,context,source,runInNewContext};
}

test('macOS Ctrl-left press opens only the mark context menu', async () => {
  const {handlers,menu,context} = await markInputHandlers();
  const event = {button:0,ctrlKey:true,clientX:120,clientY:90,preventDefault(){}};
  handlers.pointerdown(event);
  await handlers.mousedown({...event,detail:2});
  assert.equal(context.gesture,null);
  assert.equal(context.loading,false);
  assert.equal(menu.hidden,true);
  handlers.contextmenu(event);
  assert.equal(menu.hidden,false);
  assert.equal(menu.style.left,'120px');
  assert.equal(menu.style.top,'90px');
  for (const [platform,ctrlKey] of [['control',true],['meta',false]]) {
    const ordinary = await markInputHandlers({ui:{navigation:{zoom_modifier:platform}}});
    assert.throws(() => ordinary.handlers.pointerdown({...event,ctrlKey}), /context click reached canvas editing/);
  }
});

test('handles take priority over a mark in the same context-click stack', async () => {
  const {handlers,menu} = await markInputHandlers({document:{elementsFromPoint:()=>[
    {closest:selector=>selector === '[data-handle]' ? {} : null},
    {closest:selector=>selector === '[data-handle]' ? null : {dataset:{item:'mark:2'}}},
  ]}});
  handlers.contextmenu({clientX:120,clientY:90,preventDefault(){}});
  assert.equal(menu.hidden,true);
});

test('mark candidate preview scrolls only the missing margin', async () => {
  const {source,runInNewContext} = await markInputHandlers();
  const start = source.indexOf('    const highlight = () => {');
  const end = source.indexOf('\n    };',start)+7;
  assert.ok(start >= 0);
  for (const [rect,expected] of [
    [[85,85,10,10],[0,0]], [[75,85,10,10],[-5,0]],
    [[115,85,10,10],[5,0]], [[85,75,10,10],[0,-5]],
    [[85,115,10,10],[0,5]], [[75,115,10,10],[-5,5]],
  ]) {
    const view = {x:0,y:0,width:200,height:200};
    const context = {view,clampView,viewScale:()=>1,field:{value:'0'},render(){},
      $:()=>({replaceChildren(){},append(){}}),
      editor:{info:{drawing:{mark_owner_rects:{'0':rect},selection_style:{screen_width:1.5}}}},
      canvas:{clientWidth:200,clientHeight:200,setAttribute(){}},
      document:{createElementNS:()=>({setAttribute(){}})},
    };
    runInNewContext(source.slice(start,end)+'\nhighlight();',context);
    assert.deepEqual([view.x,view.y],expected);
  }
});

test('mark measurement excludes repeated presses until the request completes', async () => {
  const {source,runInNewContext} = await markInputHandlers();
  const start = source.indexOf('async function editWithMarkMeasurements(change) {');
  const end = source.indexOf('\n}',start)+2;
  let complete, requests = 0;
  const edits = [];
  const context = {loading:false, editor:{busy:false,readOnly:false,info:{session:'test',revision:1,drawing:{label_measurements:{queries:[],mark_queries:[]}}}},
    render(){},markFont:()=>({}),notice:()=>{},
    api:()=>{requests++; return new Promise(resolve=>{complete=resolve;});},
    edit:async change=>{edits.push(change);},
  };
  runInNewContext(source.slice(start,end),context);
  const first = context.editWithMarkMeasurements({key:'+'});
  const second = context.editWithMarkMeasurements({key:'-'});
  assert.equal(requests,1);
  await second;
  assert.equal(context.loading,true);
  complete(); await first;
  assert.deepEqual(edits,[{key:'+'}]);
  assert.equal(context.loading,false);
  for (const state of ['busy','readOnly']) {
    context.editor[state] = true;
    await context.editWithMarkMeasurements({key:'-'});
    context.editor[state] = false;
  }
  assert.equal(requests,1);
});

test('selected marks show native owner guides without changing document content', () => {
  const source = info(1), before = JSON.stringify(source.document);
  source.drawing.mark_owners = {
    0:{rect:[20,30,20,20],line:[30,40,100,100],color:'#b45309',text:'Owner: C #0 — far from owner'},
    1:{text:'Free mark (no chemical owner)'},
  };
  const options = {drawing:source.drawing,selection:new Set(['mark:0','mark:1'])};
  const svg = sceneMarkup(source.document,options);
  assert.ok(svg.includes('data-mark-owner="0"'));
  assert.ok(svg.includes('stroke="#b45309"'));
  assert.ok(svg.includes('stroke-dasharray="6.0000 3.0000"'));
  assert.ok(svg.includes('cx="30.0000" cy="40.0000" rx="10.0000" ry="10.0000"'));
  assert.ok(!svg.includes('data-mark-owner="1"'));
  assert.ok(!sceneMarkup(source.document,{...options,showMarkOwners:false}).includes('data-mark-owner='));
  assert.ok(!sceneMarkup(source.document,{drawing:source.drawing}).includes('data-mark-owner='));
  assert.equal(JSON.stringify(source.document),before);
});

test('mark hover reuses glyph drawing without interactive or document marks', () => {
  const source = info(1), before = JSON.stringify(source.document);
  const markPreview = {mark:{kind:'radical',x:50,y:25,radius:2,color:'#000000'},atom:[30,40,5],owner:0};
  const markHoverStyle = {color:[120,120,120,140],opacity:.55,z:4.5,atom_z:5,pen:[13,148,136,150],brush:[13,148,136,30]};
  const svg = sceneMarkup(source.document,{drawing:source.drawing,markPreview,markHoverStyle});
  assert.ok(svg.includes('data-mark-preview="true"'));
  assert.ok(svg.includes('opacity="0.5500" pointer-events="none"'));
  assert.ok(svg.includes('cx="50.0000" cy="25.0000" r="2.0000"'));
  assert.ok(svg.includes('data-mark-hover-owner="0"'));
  assert.ok(svg.includes('fill="rgba(120,120,120,0.5490196078431373)"'));
  assert.ok(!svg.includes('data-mark="'));
  assert.ok(!svg.includes('data-item="mark:'));
  assert.equal(JSON.stringify(source.document),before);
});

test('mark hover coalesces motion and cannot return after pointer leave or an edit', async () => {
  const {source,runInNewContext} = await markInputHandlers();
  const start = source.indexOf('async function refreshMarkHover() {');
  const end = source.indexOf('\n}',start)+2;
  const calls = [], releases = [];
  const context = {pointerPosition:{clientX:10,clientY:20},tool:'mark',markKind:'plus',gesture:null,loading:false,
    editor:{document:{},readOnly:false,busy:false,info:{session:'s',revision:1,sheet:[800,600],drawing:{label_measurements:{queries:[],mark_queries:[]}}}},
    point:p=>({x:p.clientX,y:p.clientY}),pointInSheet:()=>true,
    hitsAt:()=>[],viewScale:()=>1,markFont:()=>({}),render(){},
    markHover:{request:null,result:null,pending:false},
    api:async (_,request)=>{calls.push(request);return await new Promise(resolve=>releases.push(resolve));},
  };
  runInNewContext(source.slice(start,end),context);
  const pending = context.refreshMarkHover();
  context.pointerPosition = {clientX:30,clientY:40};
  await context.refreshMarkHover();
  assert.equal(calls.length,1);
  releases[0]({mark:{x:10},revision:1});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(calls.length,2);
  assert.equal(calls[1].x,30);
  releases[1]({mark:{x:30},revision:1});
  await pending;
  assert.equal(context.markHover.result.mark.x,30);
  for (const change of ['leave','revision','kind']) {
    const next = context.refreshMarkHover(), index = releases.length-1;
    if (change === 'leave') { context.pointerPosition = null; await context.refreshMarkHover(); }
    else if (change === 'revision') { context.editor.info.revision++; context.markHover.result=null; }
    else { context.markKind='minus'; context.markHover.result=null; }
    releases[index]({mark:{x:999},revision:1});
    await next;
    assert.equal(context.markHover.result,null);
    context.pointerPosition = {clientX:30,clientY:40};
  }
});

test('charge keypresses retain order and revisions through the existing edit path', async () => {
  const {source,runInNewContext} = await markInputHandlers();
  const start = source.indexOf('function queueChargeEdit(change) {');
  const end = source.indexOf('\n}',start)+2;
  const applied = [], releases = [];
  const context = {chargeEdits:null,loading:false,editor:{readOnly:false,busy:false,info:{session:'s',revision:1}},notice(){},
    editWithMarkMeasurements:async change=>{
      assert.equal(context.editor.busy,false);
      context.editor.busy=true;
      applied.push({key:change.key,atom:change.atom_id,revision:context.editor.info.revision});
      const ok = await new Promise(resolve=>releases.push(resolve));
      if (ok) context.editor.info.revision++;
      context.editor.busy=false;
      return ok;
    },
  };
  runInNewContext(source.slice(start,end),context);
  const keys = '++++++++++++---';
  const pending = [...keys].map(key=>context.queueChargeEdit({key,atom_id:0}));
  for (let index=0;index<keys.length;index++) {
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(applied.length,index+1);
    assert.deepEqual(applied[index],{key:keys[index],atom:0,revision:index+1});
    releases[index](true);
  }
  assert.deepEqual(await Promise.all(pending),Array(keys.length).fill(true));
  assert.equal(context.chargeEdits,null);
  for (const failure of ['rejected','session']) {
    const count = applied.length;
    const first = context.queueChargeEdit({key:'+',atom_id:0});
    const second = context.queueChargeEdit({key:'-',atom_id:1});
    await new Promise(resolve=>setImmediate(resolve));
    if (failure === 'session') context.editor.info.session += 'new';
    releases[count](failure === 'session');
    await first;
    assert.equal(await second,false);
    assert.equal(applied.length,count+1);
  }
  context.editor.busy=true;
  assert.equal(await context.queueChargeEdit({key:'+'}),false);
  context.editor.busy=false; context.editor.readOnly=true;
  assert.equal(await context.queueChargeEdit({key:'+'}),false);
});

test('keyboard busy guard admits only charge keys belonging to the active queue', async () => {
  const {source,runInNewContext} = await markInputHandlers();
  const start = source.indexOf("document.addEventListener('keydown', event => {\n");
  const end = source.indexOf('\n});',start)+4;
  for (const [busy,loading,queue,key,expected] of [
    [true,false,{},'+',1], [false,true,{},'-',1],
    [true,false,null,'+',0], [true,false,{},'n',0],
  ]) {
    let handler;
    const keys = [];
    const context = {chargeEdits:queue,loading,pointerPosition:{},editor:{busy,readOnly:false,info:{}},
      document:{querySelector:()=>null,addEventListener:(_,fn)=>{handler=fn;}},
      ui:{hover_shortcuts:['+','-','n'],navigation:{zoom_keys:{},function_keys:{},zoom_modifier:'control'}},cancelGesture(){},hoverPoint:()=>({x:10,y:20,atom_id:0}),
      noteEditorElement:{contains:()=>false},
      queueChargeEdit:async change=>{keys.push(change.key);return true;},
      edit:()=>{throw new Error('busy non-charge input was accepted');},
    };
    runInNewContext(source.slice(start,end),context);
    handler({key,shiftKey:key==='+',target:{matches:()=>false,closest:()=>null},preventDefault(){}});
    await Promise.resolve();
    assert.equal(keys.length,expected);
  }
});

test('scene limits clamp scrolling and center an axis smaller than the viewport', () => {
  const viewport={width:200,height:100};
  const scene=[-10,-20,100,80];
  for (const [x,y,expected] of [[-100,-100,[-10,-20]],[100,100,[40,35]],[0,0,[0,0]]]) {
    const result=clampView({x,y,width:50,height:25},viewport,scene);
    assert.deepEqual([result.x,result.y],expected);
  }
  assert.deepEqual(clampView({x:1000,y:1000,width:200,height:100},viewport,scene),
    {x:-60,y:-30,width:200,height:100});
  const letterboxed=clampView({x:0,y:0,width:100,height:100},viewport,[-1000,-1000,2000,2000]);
  assert.deepEqual(letterboxed,{x:-50,y:0,width:200,height:100});
});

test('orbital SVG retains native ellipse geometry, phase and center transforms', () => {
  const source = info();
  const orbital = {kind:'mo_antibonding',center:[37,-21],scale:0.5,rotation:45,
    ellipses:[[23,-25.9,14,9.8,true],[37,-25.9,14,9.8,false]],
    node:[37,-26.6,37,-15.4],hit_rect:[22.5,-27.1,29,12.2],width:1,color:'#000000',
    positive:'#2f6ed3',negative:'#d84a3a',alpha:0.25,phase:true,handles:[{handle:'scale',point:[53,-21]},{handle:'rotate',point:[37,-37]}]};
  source.drawing.orbitals = [orbital];
  let svg = sceneMarkup(source.document, {drawing:source.drawing});
  assert.ok(svg.includes('data-item="orbital:0"'));
  assert.ok(svg.includes('translate(37.0000 -21.0000) rotate(45.0000) scale(0.5000) translate(-37.0000 21.0000)'));
  assert.ok(svg.includes('cx="30.0000" cy="-21.0000" rx="7.0000" ry="4.9000" fill="#2f6ed3" fill-opacity="0.2500"'));
  assert.ok(svg.includes('cx="44.0000" cy="-21.0000" rx="7.0000" ry="4.9000" fill="#d84a3a" fill-opacity="0.2500"'));
  assert.ok(svg.includes('x1="37.0000" y1="-26.6000" x2="37.0000" y2="-15.4000"'));
  assert.ok(svg.includes('width="29.0000" height="12.2000" fill="transparent" stroke="none" pointer-events="all"'));
  const handles = sceneMarkup(source.document,{drawing:source.drawing,handleTarget:'orbital:0',handleStyle:{size:8,color:'#0d9488'},scale:2});
  assert.ok(handles.includes('data-handle="scale" data-orbital-id="0" cx="53.0000" cy="-21.0000" r="2.0000"'));
  assert.ok(handles.includes('data-handle="rotate" data-orbital-id="0" cx="37.0000" cy="-37.0000" r="2.0000"'));
  orbital.phase = false;
  orbital.node = null;
  orbital.kind = '<script>';
  svg = sceneMarkup(source.document, {drawing:source.drawing});
  assert.ok(svg.includes('fill="none" fill-opacity="0.2500"'));
  assert.ok(!svg.includes('fill="#2f6ed3"') && !svg.includes('fill="#d84a3a"'));
  assert.ok(!svg.includes('y1="-26.6000"'));
  assert.ok(svg.includes('Orbital &lt;script&gt;') && !svg.includes('<script>'));
});

test('orbital handles send the existing revisioned handle edit payload', async () => {
  const {source,runInNewContext} = await markInputHandlers();
  const start=source.indexOf('function handleRequest('), end=source.indexOf('\nasync function finishHandle(', start);
  const context={};
  runInNewContext(source.slice(start,end),context);
  for (const handle of ['scale','rotate']) {
    const payload=context.handleRequest({target:'orbital',id:3,handle},{x:12,y:-7});
    assert.deepEqual(JSON.parse(JSON.stringify(payload)),{kind:'orbital_handle',id:3,handle,position:[12,-7]});
  }
});

test('bracket SVG materializes native commands and glyph placement', () => {
  const source = info();
  source.drawing.brackets = [
    {kind:'parenthesis_left',path:[['M',[43.48,-21]],['C',[37,-10.44,37,-7.56,37,3]]],width:0.87,color:'#000000',symbol:null},
    {kind:'dagger',path:[],width:0.87,color:'#000000',bounds:[46,-6,8,21],symbol:{text:'†',pixels:27,x:49.6,y:12.72,family:'Arial'}},
  ];
  const svg = sceneMarkup(source.document,{drawing:source.drawing});
  assert.ok(svg.includes('data-item="ts_bracket:0"'));
  assert.ok(svg.includes('d="M43.4800 -21.0000 C37.0000 -10.4400 37.0000 -7.5600 37.0000 3.0000"'));
  assert.ok(svg.includes('stroke-width="0.8700" stroke-linecap="butt" stroke-linejoin="miter"'));
  // The glyph paints; its measured ink box is the hit target.
  assert.ok(svg.includes('x="49.6000" y="12.7200" font-family="Arial" font-size="27.0000" fill="#000000" pointer-events="none">†</text>'));
  assert.ok(svg.includes('<rect x="46.0000" y="-6.0000" width="8.0000" height="21.0000" fill="transparent" pointer-events="all"/>'));
  const dragged = sceneMarkup(source.document,{drawing:source.drawing,preview:{kind:'ts_bracket'}});
  assert.ok(dragged.includes('fill="rgba(120,120,120,0.549)" pointer-events="none">†</text>'));
  assert.ok(dragged.includes('stroke="#000000" stroke-width="0.8700"'));
  source.drawing.brackets[1].symbol.text = '<script>';
  const escaped = sceneMarkup(source.document,{drawing:source.drawing});
  assert.ok(escaped.includes('&lt;script&gt;') && !escaped.includes('<script>'));
});

test('mark ownership guidance appears only with the drawn owner guide', () => {
  const source = info();
  source.drawing.marks = [{id:0,kind:'radical',x:10,y:10,radius:1.2,hit_radius:4,color:'#000000'}];
  source.drawing.mark_owners = {'0':{text:'Owner: N #0',tooltip:'Owner: N #0. Amber means far from owner.',rect:[0,0,8,8],line:[4,4,10,10],color:'#0d9488'}};
  const title = options => sceneMarkup(source.document,{drawing:source.drawing,...options}).match(/<g data-mark="0"[^>]*><title>([^<]*)<\/title>/)[1];
  assert.equal(title({}), 'Owner: N #0');
  assert.equal(title({selection:new Set(['mark:0']),showMarkOwners:false}), 'Owner: N #0');
  assert.equal(title({selection:new Set(['mark:0'])}), 'Owner: N #0. Amber means far from owner.');
});

// A minimal DOM for scene.mjs's real note readers: parsed markup gets no CSSOM,
// as under the page's CSP, so a format reaches noteBlocks only once
// styleNoteText applies its data-style, data-pt or data-script.
const miniStyle = () => ({setProperty(name, value) {
  this[name.replace(/-(\w)/g, (_, letter) => letter.toUpperCase())] = value;
  if (name === 'text-decoration') this.textDecorationLine = value;
}});
class MiniText {
  constructor(data) { Object.assign(this, {nodeType: 3, nodeName: '#text', data, parentNode: null}); }
  get parentElement() { return this.parentNode; }
  get textContent() { return this.data; }
}
class MiniElement {
  constructor(name, attributes = {}) {
    Object.assign(this, {nodeType: 1, nodeName: name.toUpperCase(), attributes, childNodes: [], parentNode: null, style: miniStyle(), handlers: {}, writes: []});
  }
  get parentElement() { return this.parentNode; }
  get children() { return this.childNodes.filter(node => node.nodeType === 1); }
  get textContent() { return this.childNodes.map(node => node.textContent).join(''); }
  get classList() { return {contains: name => (this.attributes.class ?? '').split(' ').includes(name)}; }
  get dataset() {
    return Object.fromEntries(Object.entries(this.attributes).filter(([name]) => name.startsWith('data-'))
      .map(([name, value]) => [name.slice(5).replace(/-(\w)/g, (_, letter) => letter.toUpperCase()), value]));
  }
  set innerHTML(html) {
    this.writes.push(html);
    this.childNodes = [];
    const decode = text => text.replace(/&(lt|gt|quot|amp);/g, (_, name) => ({lt: '<', gt: '>', quot: '"', amp: '&'})[name]);
    let parent = this;
    for (const [, close, tag, attributes, text] of html.matchAll(/<(\/?)(\w+)([^>]*)>|([^<]+)/g)) {
      if (text !== undefined) parent.append(new MiniText(decode(text)));
      else if (close) parent = parent.parentNode;
      else {
        const child = new MiniElement(tag, Object.fromEntries([...attributes.matchAll(/([\w-]+)(?:="([^"]*)")?/g)].map(([, name, value = '']) => [name, decode(value)])));
        parent.append(child);
        if (child.nodeName !== 'BR') parent = child;
      }
    }
  }
  append(...nodes) { for (const node of nodes) { node.parentNode = this; this.childNodes.push(node); } }
  replaceChildren(...nodes) { this.childNodes = []; this.append(...nodes); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; if (name === 'style') this.style = miniStyle(); }
  contains(node) { for (; node; node = node.parentNode) if (node === this) return true; return false; }
  querySelectorAll(selector) {
    const name = /^\[([\w-]+)\]$/.exec(selector)[1], found = [];
    const walk = node => node.children.forEach(child => { if (name in child.attributes) found.push(child); walk(child); });
    walk(this);
    return found;
  }
  addEventListener(kind, handler) { this.handlers[kind] = handler; }
  focus() {}
}

// The note editor's own handlers over that DOM with scene.mjs's real noteBlocks,
// serializeNoteEditor and styleNoteText. Offsets stand in for DOM positions;
// note_markup replies wait until a test releases them with the adapter's markup.
async function noteEditorHarness() {
  const {runInNewContext} = await import('node:vm');
  const {noteBlocks, noteBlocksHtml, serializeNoteEditor, styleNoteText, formatNoteBlocks, noteFormatState} = await import('../app/chemvas/web/scene.mjs');
  const source = await webSource('app.mjs');
  const style = {family: 'Arial', pixels: 16, point_size: 12, weight: 400, italic: false, line_spacing: 1};
  const paragraph = 'margin-top:0px; margin-bottom:0px; white-space:pre-wrap';
  // The browser globals scene.mjs reads; computed style inherits from ancestors.
  globalThis.Node ??= {TEXT_NODE: 3, ELEMENT_NODE: 1};
  globalThis.getComputedStyle ??= target => {
    const inherited = key => { for (let node = target; node; node = node.parentElement) if (node.style[key]) return node.style[key]; };
    return {fontStyle: inherited('fontStyle') ?? 'normal', fontWeight: inherited('fontWeight') ?? '400', fontSize: inherited('fontSize') ?? '16px', fontFamily: inherited('fontFamily') ?? 'Arial'};
  };
  const replies = [], edits = [], documentHandlers = {}, element = new MiniElement('div'), writes = element.writes;
  const selection = {rangeCount: 1, anchorNode: element, focusNode: element, anchorOffset: 0, focusOffset: 0, changed: false,
    removeAllRanges() {}, addRange(range) { this.setBaseAndExtent(element, range.start, element, range.end); },
    setBaseAndExtent(anchorNode, anchorOffset, focusNode, focusOffset) { Object.assign(this, {anchorNode, anchorOffset, focusNode, focusOffset, changed: true}); }};
  const length = () => noteBlocks(element, style).reduce((total, block, index) => total + (index ? 1 : 0) + block.runs.reduce((n, run) => n + (run.br ? 1 : run.text.length), 0), 0);
  const buttons = ['bold', 'italic', 'superscript', 'subscript', 'left', 'center', 'right'].map(key =>
    ({dataset: {textFormat: key}, pressed: null, setAttribute(_name, value) { this.pressed = value; }}));
  const context = {
    editor: {readOnly: false, busy: false, document: {state: {settings: {text_color: '#222222', text_alignment: 'left'}}},
      info: {session: 's', revision: 3, drawing: {note_style: style, notes: [{id: 7, x: 0, y: 0, html: `<p data-style="${paragraph}">AB</p>`}]}}},
    loading: false, tool: 'note', ui: {text_format: {size_range: [6, 96]}}, noteEditor: null, noteCommit: Promise.resolve(), selection: new Set(),
    noteEditorElement: element, getSelection: () => selection,
    document: {addEventListener: (kind, handler) => { documentHandlers[kind] = handler; }, querySelectorAll: () => buttons, execCommand() {},
      createRange: () => ({selectNodeContents() { Object.assign(this, {start: 0, end: length()}); },
        setStart(_node, start) { this.start = start; }, setEnd(_node, end) { this.end = end; }})},
    noteBlocks, noteBlocksHtml, serializeNoteEditor, styleNoteText, formatNoteBlocks, noteFormatState,
    noteFont: () => ({ascent: 9, descent: 3, leading: 0}),
    noteTextOffset: (_root, _spec, _node, offset) => offset, noteTextPosition: (root, offset) => [root, offset],
    render() {}, notice() {}, api: (_path, body) => new Promise(resolve => replies.push({body, resolve})),
    edit: async request => { edits.push(request); return true; },
  };
  const start = source.indexOf('function textFormatButton(spec, action, checkable = false) {');
  const end = source.indexOf('// Mark placement also needs the H metrics', start);
  assert.ok(start >= 0 && end > start);
  runInNewContext(source.slice(start, end), context);
  const settle = async () => {
    await new Promise(resolve => setImmediate(resolve));
    if (selection.changed) { selection.changed = false; documentHandlers.selectionchange(); }
  };
  // The browser edits the text node at the caret, where noteTextPosition puts
  // it; a line without text gets a text node in place of its placeholder.
  const textAt = offset => {
    let remaining = offset;
    for (const [index, block] of element.children.entries()) {
      if (index) remaining -= 1;
      const leaves = [], walk = node => node.childNodes.forEach(child => child.nodeType === 3 || child.nodeName === 'BR' ? leaves.push(child) : walk(child));
      walk(block);
      const size = leaves.reduce((total, leaf) => total + (leaf.nodeType === 3 ? leaf.data.length : 1), 0);
      if (remaining > size) { remaining -= size; continue; }
      for (const leaf of leaves) {
        if (leaf.nodeType === 3 && remaining <= leaf.data.length) return [leaf, remaining];
        remaining -= leaf.nodeType === 3 ? leaf.data.length : 1;
      }
      return [block, 0];
    }
  };
  const splice = (remove, text) => {
    const at = Math.min(selection.anchorOffset, selection.focusOffset), [node, offset] = textAt(at);
    if (node.nodeType === 3) node.data = node.data.slice(0, offset - remove) + text + node.data.slice(offset);
    else node.replaceChildren(new MiniText(text));
    selection.setBaseAndExtent(element, at - remove + text.length, element, at - remove + text.length);
  };
  const input = (inputType, data, remove = 0) => {
    element.handlers.beforeinput({inputType, data, isComposing: false});
    splice(remove, data);
    element.handlers.input({inputType, data, isComposing: false});
  };
  return {context, element, replies, edits, writes, paragraph, settle, input,
    markup: body => `<p data-style="${paragraph}">${body}</p>`,
    key: (key, isComposing = false) => element.handlers.keydown({key, isComposing}),
    // A shortcut keypress, and the history input a browser menu sends; each
    // reports whether the editor took it from the browser.
    shortcut: (key, modifiers = {}) => {
      const event = {key, isComposing: false, ...modifiers, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }};
      element.handlers.keydown(event);
      return event.defaultPrevented;
    },
    history: inputType => {
      const event = {inputType, isComposing: false, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }};
      element.handlers.beforeinput(event);
      return event.defaultPrevented;
    },
    // A browser replacement of [from, to) that need not start at the caret,
    // such as a spelling correction, with or without its text as data.
    replace: (from, to, text, data = null) => {
      element.handlers.beforeinput({inputType: 'insertReplacementText', data, isComposing: false});
      selection.setBaseAndExtent(element, to, element, to);
      splice(to - from, text);
      element.handlers.input({inputType: 'insertReplacementText', data, isComposing: false});
    },
    // An input that arrives without a beforeinput of its own.
    bare: (inputType, data) => {
      splice(0, data);
      element.handlers.input({inputType, data, isComposing: false});
    },
    move: offset => selection.setBaseAndExtent(element, offset, element, offset),
    leave: () => Object.assign(selection, {anchorNode: {}, focusNode: {}, changed: true}),
    compose: (remove, text) => {
      element.handlers.beforeinput({inputType: 'insertCompositionText', data: text, isComposing: true});
      splice(remove, text);
      element.handlers.input({inputType: 'insertCompositionText', data: text, isComposing: true});
    },
    enter: async () => {
      element.handlers.beforeinput({inputType: 'insertParagraph', isComposing: false});
      const at = selection.anchorOffset, line = new MiniElement('p', {...element.children.at(-1).attributes});
      // The model starts a paragraph only at the note's end, as the tests use it.
      assert.equal(at, length());
      line.append(new MiniElement('br'));
      element.append(line);
      selection.setBaseAndExtent(element, at + 1, element, at + 1);
      element.handlers.input({inputType: 'insertParagraph', isComposing: false});
      await settle();
    },
    open: async (...args) => { context.beginNoteEdit(...args); await settle(); },
    caret: async (anchor, focus = anchor) => { selection.setBaseAndExtent(element, anchor, element, focus); await settle(); },
    press: async action => { await context.applyTextFormat(action); await settle(); },
    type: async text => { for (const c of text) { input('insertText', c); await settle(); } },
    reply: async (index, html) => { replies[index].resolve({html}); await settle(); await settle(); },
    finish: async () => { element.handlers.focusout({relatedTarget: null}); await settle(); },
    selection: () => [selection.anchorOffset, selection.focusOffset],
    pressed: () => Object.fromEntries(buttons.map(button => [button.dataset.textFormat, button.pressed === 'true'])),
    chars: () => noteBlocks(element, style).flatMap((block, index) => [...(index ? ['¶'] : []), ...block.runs.filter(run => !run.br).flatMap(({text, format}) =>
      text.split('').map(c => c + (format.bold ? 'b' : '') + (format.italic ? 'i' : '') + (format.script ? `:${format.script}` : '') + (format.pt !== 12 ? `@${format.pt}` : '')))]),
  };
}

test('caret formats accumulate and toggle off for the text typed next, like QTextCursor', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1);
  await h.press({key: 'bold'}); await h.press({key: 'italic'});
  assert.deepEqual([h.pressed().bold, h.pressed().italic, h.replies.length], [true, true, 0]);
  await h.type('X');
  assert.deepEqual(h.chars(), ['A', 'Xbi', 'B']);
  await h.caret(3); await h.press({key: 'bold'}); await h.press({key: 'bold'});
  assert.equal(h.pressed().bold, false);
  await h.type('Y');
  await h.reply(0, h.markup('A<span data-style="font-weight:700; font-style:italic">X</span>B'));
  await h.reply(1, h.markup('A<span data-style="font-weight:700; font-style:italic">X</span>BY'));
  assert.deepEqual(h.chars(), ['A', 'Xbi', 'B', 'Y']);
  await h.finish();
  assert.deepEqual(h.edits.map(edit => edit.html), [`<p style="${h.paragraph}">A<span style="font-weight:700; font-style:italic">X</span>BY</p>`]);
});

test('moving the caret forgets a pending format, even when it moves back', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  assert.equal(h.pressed().bold, true);
  await h.caret(2);
  assert.equal(h.pressed().bold, false);
  await h.caret(1);
  assert.equal(h.pressed().bold, false);
  await h.type('Y');
  assert.deepEqual([h.chars(), h.replies.length], [['A', 'Y', 'B'], 0]);
});

test('caret scripts exclude each other and size steps clamp to the native range', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1);
  await h.press({key: 'superscript'}); await h.press({key: 'subscript'});
  assert.deepEqual([h.pressed().superscript, h.pressed().subscript], [false, true]);
  await h.type('S'); await h.caret(3);
  for (let step = 0; step < 100; step++) await h.press({delta: 1});
  await h.type('U');
  for (let step = 0; step < 100; step++) await h.press({delta: -1});
  await h.type('D'); await h.caret(2); await h.press({delta: 1}); await h.press({delta: 1});
  await h.type('P');
  assert.deepEqual(h.chars(), ['A', 'S:sub', 'P:sub@14', 'B', 'U@96', 'D@6']);
});

test('a caret at a paragraph start takes the next character format and a new note types with its own', async () => {
  const h = await noteEditorHarness();
  h.context.editor.info.drawing.notes[0].html = `<p data-style="${h.paragraph}"><span data-style="font-weight:700">A</span>B</p>`;
  await h.open(7); await h.caret(0);
  assert.equal(h.pressed().bold, true);
  await h.press({key: 'italic'}); await h.type('Z');
  assert.deepEqual(h.chars(), ['Zbi', 'Ab', 'B']);
  await h.finish(); await h.open(null, 5, 6);
  assert.deepEqual(Object.values(h.pressed()).slice(0, 4), [false, false, false, false]);
  await h.press({key: 'bold'});
  assert.equal(h.pressed().bold, true);
  await h.type('RS');
  assert.deepEqual(h.chars(), ['Rb', 'Sb']);
  await h.finish();
  assert.deepEqual({...h.edits.at(-1)}, {kind: 'note_text', id: null, x: 5, y: 6, html: `<p style="${h.paragraph}"><span style="font-weight:700">RS</span></p>`});
});

test('a new paragraph keeps the pending caret format like the desktop', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(2); await h.press({key: 'bold'});
  await h.enter();
  assert.equal(h.pressed().bold, true);
  await h.type('E');
  assert.deepEqual(h.chars(), ['A', 'B', '¶', 'Eb']);
});

test('formatting only a caret changes neither the document nor history', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1);
  for (const action of [{key: 'bold'}, {key: 'italic'}, {key: 'superscript'}, {delta: 1}]) await h.press(action);
  await h.finish();
  await h.open(null, 5, 6); await h.press({key: 'bold'}); await h.finish();
  assert.deepEqual([h.edits.length, h.replies.length], [0, 0]);
});

test('a late note_markup reply cannot replace faster typing or a newer caret format', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(0); await h.press({key: 'bold'});
  h.input('insertText', 'R'); h.input('insertText', 'S'); await h.settle();
  assert.deepEqual([h.chars(), h.replies.length], [['Rb', 'Sb', 'A', 'B'], 1]);
  await h.press({key: 'italic'});
  const stale = h.markup('<span data-style="font-weight:700">R</span>AB'), current = h.markup('<span data-style="font-weight:700">RS</span>AB');
  const writesBeforeReply = h.writes.length;
  await h.reply(0, stale);
  assert.deepEqual([h.writes.length, h.replies.length], [writesBeforeReply, 2]);
  assert.ok(h.replies[1].body.html.includes('<span style="font-weight:700">RS</span>AB'));
  await h.reply(1, current);
  assert.deepEqual([h.writes.at(-1), h.chars(), h.selection(), h.pressed().bold, h.pressed().italic], [current, ['Rb', 'Sb', 'A', 'B'], [2, 2], true, true]);
  await h.type('T'); await h.finish();
  assert.equal(h.edits[0].html, `<p style="${h.paragraph}"><span style="font-weight:700">RS</span><span style="font-weight:700; font-style:italic">T</span>AB</p>`);
});

test('selected formatting shows at once and survives stale replies and typing', async () => {
  const h = await noteEditorHarness();
  await h.open(7);
  await h.caret(0, 1); await h.press({key: 'bold'});
  await h.caret(1, 2); await h.press({key: 'italic'});
  assert.deepEqual([h.chars(), h.replies.length, h.selection()], [['Ab', 'Bi'], 1, [1, 2]]);
  await h.caret(2); await h.type('C'); await h.reply(0, h.markup('<span data-style="font-weight:700">A</span>B'));
  assert.equal(h.replies.length, 2);
  const current = h.markup('<span data-style="font-weight:700">A</span><span data-style="font-style:italic">BC</span>');
  await h.reply(1, current);
  assert.deepEqual([h.chars(), h.writes.at(-1)], [['Ab', 'Bi', 'Ci'], current]);
});

test('finishing while note_markup is pending saves the typed format and ignores the reply', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'}); await h.type('X');
  await h.finish();
  assert.equal(h.edits[0].html, `<p style="${h.paragraph}">A<span style="font-weight:700">X</span>B</p>`);
  await h.open(7);
  const written = h.writes.length;
  await h.reply(0, h.markup('A<span data-style="font-weight:700">X</span>B'));
  assert.deepEqual([h.writes.length, h.replies.length, h.chars(), h.edits.length], [written, 1, ['A', 'B'], 1]);
});

test('IME text takes the caret format once committed and is never rewritten while composing', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  const written = h.writes.length;
  h.element.handlers.compositionstart({});
  h.compose(0, 'ㅎ'); await h.settle();
  h.compose(1, '한'); await h.settle();
  assert.deepEqual([h.writes.length, h.replies.length, h.chars()], [written, 0, ['A', '한', 'B']]);
  h.element.handlers.compositionend({}); await h.settle();
  assert.deepEqual([h.chars(), h.replies.length], [['A', '한b', 'B'], 1]);
  h.element.handlers.compositionstart({});
  h.compose(0, 'ㄱ'); await h.settle();
  const composing = h.writes.length;
  await h.reply(0, h.markup('A<span data-style="font-weight:700">한</span>B'));
  assert.deepEqual([h.writes.length, h.replies.length], [composing, 1]);
  h.element.handlers.compositionend({}); await h.settle();
  assert.equal(h.replies.length, 2);
  await h.reply(1, h.markup('A<span data-style="font-weight:700">한ㄱ</span>B'));
  assert.deepEqual(h.chars(), ['A', '한b', 'ㄱb', 'B']);
});

test('navigation keys and pointer presses forget a pending format, even at the same offset', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  h.key('ArrowRight'); h.move(2); h.key('ArrowLeft'); h.move(1); await h.settle();
  assert.equal(h.pressed().bold, false);
  await h.type('Y'); await h.press({key: 'italic'});
  h.element.handlers.pointerdown({}); await h.settle();
  assert.equal(h.pressed().italic, false);
  await h.type('Z');
  assert.deepEqual([h.chars(), h.replies.length], [['A', 'Y', 'Z', 'B'], 0]);
});

test('caret scripts and sizes show in the adapter markup before its reply, and a script ends where it is turned off', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1);
  await h.press({key: 'subscript'}); await h.type('2');
  await h.caret(3);
  for (let step = 0; step < 8; step++) await h.press({delta: 1});
  await h.press({key: 'superscript'}); await h.type('2');
  // The adapter's markup for these runs, as test_browser_note_html_follows_the_native_restore records it.
  assert.equal(h.writes.at(-1), h.markup('A<span data-style="font-size:11px" data-script="sub" data-base-pixels="16">2</span>B'
    + '<span data-style="font-size:17px" data-script="super" data-base-pixels="27" data-pt="20">2</span>'));
  const [sub, sup] = h.element.querySelectorAll('[data-script]');
  assert.deepEqual([sub.style.fontSize, sub.style.top, sup.style.fontSize, sup.style.top], ['11px', '2px', '17px', '-6px']);
  await h.caret(2); await h.press({key: 'subscript'}); await h.type('T');
  assert.deepEqual(h.chars(), ['A', '2:sub', 'T', 'B', '2:super@20']);
  await h.finish();
  assert.equal(h.edits[0].html, `<p style="${h.paragraph}">A<span style="vertical-align:sub">2</span>TB<span style="font-size:20pt; vertical-align:super">2</span></p>`);
});

test('paste and deletion keep the browser content, end a pending format and survive a late reply', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'}); await h.type('X');
  await h.press({key: 'italic'});
  h.input('insertFromPaste', 'PQ'); await h.settle();
  assert.deepEqual([h.chars(), h.pressed().bold, h.pressed().italic], [['A', 'Xb', 'Pb', 'Qb', 'B'], true, false]);
  await h.press({key: 'italic'});
  h.input('deleteContentBackward', '', 1); await h.settle();
  assert.deepEqual([h.chars(), h.pressed().italic], [['A', 'Xb', 'Pb', 'B'], false]);
  await h.reply(0, h.markup('A<span data-style="font-weight:700">X</span>B'));
  assert.deepEqual([h.chars(), h.replies.length], [['A', 'Xb', 'Pb', 'B'], 2]);
  await h.finish();
  assert.equal(h.edits[0].html, `<p style="${h.paragraph}">A<span style="font-weight:700">XP</span>B</p>`);
});

test('finishing mid-composition saves the composed text with its pending format without rewriting the editor', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  h.element.handlers.compositionstart({}); h.compose(0, '한'); await h.settle();
  h.key('ArrowLeft', true); h.leave(); await h.settle();
  const written = h.writes.length;
  await h.finish();
  assert.deepEqual([h.writes.length, h.replies.length, h.edits[0].html], [written, 0, `<p style="${h.paragraph}">A<span style="font-weight:700">한</span>B</p>`]);
});

test('a beforeinput without its input formats nothing and adds no history', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  h.element.handlers.beforeinput({inputType: 'insertText', data: 'X', isComposing: false});
  h.move(2); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'B']);
  await h.finish();
  assert.deepEqual([h.edits.length, h.replies.length], [0, 0]);
});

test('plain typing after a beforeinput without its input leaves every character plain', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  h.element.handlers.beforeinput({inputType: 'insertText', data: 'X', isComposing: false});
  h.move(2); await h.settle();
  await h.type('Z');
  assert.deepEqual(h.chars(), ['A', 'B', 'Z']);
  await h.finish();
  assert.equal(h.edits[0].html, `<p style="${h.paragraph}">ABZ</p>`);
});

test('a committed composition formats only its own text, wherever the caret moves meanwhile', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  h.element.handlers.compositionstart({data: ''}); h.compose(0, '한');
  h.move(3); await h.settle();
  h.element.handlers.compositionend({data: '한'}); await h.settle();
  assert.deepEqual([h.chars(), h.selection()], [['A', '한b', 'B'], [3, 3]]);
});

test('a cancelled composition formats nothing and adds no history', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  const written = h.writes.length;
  h.element.handlers.compositionstart({data: ''}); h.compose(0, 'ㅎ'); h.compose(1, '');
  h.element.handlers.compositionend({data: ''}); await h.settle();
  assert.deepEqual([h.chars(), h.writes.length, h.replies.length], [['A', 'B'], written, 0]);
  await h.finish();
  assert.equal(h.edits.length, 0);
});

test('Undo and Redo keys take the session steps for formatted and plain typing', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  await h.type('XY'); await h.caret(4); await h.type('Z');
  assert.deepEqual(h.chars(), ['A', 'Xb', 'Yb', 'B', 'Z']);
  assert.equal(h.shortcut('z', {ctrlKey: true}), true); await h.settle();
  assert.deepEqual([h.chars(), h.selection()], [['A', 'Xb', 'Yb', 'B'], [4, 4]]);
  assert.equal(h.shortcut('z', {metaKey: true}), true); await h.settle();
  assert.deepEqual([h.chars(), h.selection()], [['A', 'B'], [1, 1]]);
  assert.equal(h.shortcut('Z', {ctrlKey: true, shiftKey: true}), true); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'Xb', 'Yb', 'B']);
  assert.equal(h.shortcut('y', {ctrlKey: true}), true); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'Xb', 'Yb', 'B', 'Z']);
  await h.finish();
  assert.deepEqual(h.edits.map(edit => edit.html), [`<p style="${h.paragraph}">A<span style="font-weight:700">XY</span>BZ</p>`]);
});

test('browser history input takes the session steps, and contiguous deletion is one step', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(2); await h.type('CD');
  h.input('deleteContentBackward', '', 1); h.input('deleteContentBackward', '', 1); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'B']);
  assert.equal(h.history('historyUndo'), true); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'B', 'C', 'D']);
  assert.equal(h.history('historyUndo'), true); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'B']);
  assert.equal(h.history('historyRedo'), true); await h.settle();
  assert.deepEqual([h.chars(), h.replies.length], [['A', 'B', 'C', 'D'], 0]);
});

test('a committed composition is one step, a cancelled one none, and the IME keeps Undo while composing', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  h.element.handlers.compositionstart({data: ''}); h.compose(0, 'ㅎ'); h.compose(1, '한');
  assert.equal(h.shortcut('z', {ctrlKey: true, isComposing: true}), false);
  h.element.handlers.compositionend({data: '한'}); await h.settle();
  h.element.handlers.compositionstart({data: ''}); h.compose(0, 'ㄱ'); h.compose(1, '');
  h.element.handlers.compositionend({data: ''}); await h.settle();
  assert.deepEqual(h.chars(), ['A', '한b', 'B']);
  assert.equal(h.shortcut('z', {ctrlKey: true}), true); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'B']);
  assert.equal(h.shortcut('z', {ctrlKey: true}), true); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'B']);
  await h.finish();
  assert.equal(h.edits.length, 0);
});

test('selected formatting is one step, and a late note_markup reply neither records one nor replaces a restored state', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(0, 2); await h.press({key: 'italic'});
  assert.deepEqual([h.chars(), h.replies.length], [['Ai', 'Bi'], 1]);
  h.shortcut('z', {ctrlKey: true}); await h.settle();
  assert.deepEqual([h.chars(), h.selection()], [['A', 'B'], [0, 2]]);
  const written = h.writes.length;
  await h.reply(0, h.markup('<span data-style="font-style:italic">AB</span>'));
  assert.deepEqual([h.chars(), h.writes.length, h.replies.length], [['A', 'B'], written, 1]);
  h.shortcut('y', {ctrlKey: true}); await h.settle();
  assert.deepEqual(h.chars(), ['Ai', 'Bi']);
  h.shortcut('z', {ctrlKey: true}); await h.finish();
  assert.equal(h.edits.length, 0);
});

test('format-only caret changes record no step, and Undo with no step keeps the pending format', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'}); await h.press({key: 'italic'});
  const written = h.writes.length;
  assert.equal(h.shortcut('z', {ctrlKey: true}), true); await h.settle();
  assert.deepEqual([h.chars(), h.writes.length, h.pressed().bold, h.pressed().italic], [['A', 'B'], written, true, true]);
  await h.type('X');
  assert.deepEqual(h.chars(), ['A', 'Xbi', 'B']);
});

test('an Undo ends an unmatched beforeinput, so an input without its own neither resurrects undone text nor records a step', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(2); await h.type('C');
  h.element.handlers.beforeinput({inputType: 'insertText', data: 'Q', isComposing: false});
  assert.equal(h.shortcut('z', {ctrlKey: true}), true); await h.settle();
  assert.deepEqual([h.chars(), h.selection()], [['A', 'B'], [2, 2]]);
  h.bare('insertText', 'X'); await h.settle();
  h.shortcut('z', {ctrlKey: true}); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'B', 'X']);
  h.shortcut('y', {ctrlKey: true}); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'B', 'X']);
});

test('a composition owns its step, so an input after it without its own beforeinput adds no stale one', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  h.element.handlers.beforeinput({inputType: 'insertText', data: 'X', isComposing: false});
  h.element.handlers.compositionstart({data: ''}); h.compose(0, '한');
  h.element.handlers.compositionend({data: '한'}); await h.settle();
  h.element.handlers.input({inputType: 'insertCompositionText', data: '한', isComposing: false}); await h.settle();
  assert.deepEqual(h.chars(), ['A', '한b', 'B']);
  h.shortcut('z', {ctrlKey: true}); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'B']);
  h.shortcut('z', {ctrlKey: true}); h.shortcut('y', {ctrlKey: true}); await h.settle();
  assert.deepEqual(h.chars(), ['A', '한b', 'B']);
});

test('a replacement keeps the browser formatting, ends the pending format and is one step, with or without data', async () => {
  for (const data of [null, 'AXB']) {
    const h = await noteEditorHarness();
    await h.open(7); await h.caret(1); await h.press({key: 'bold'});
    h.replace(0, 2, 'AXB', data); await h.settle();
    assert.deepEqual([h.chars(), h.pressed().bold, h.replies.length], [['A', 'X', 'B'], false, 0]);
    assert.equal(h.shortcut('z', {ctrlKey: true}), true); await h.settle();
    assert.deepEqual(h.chars(), ['A', 'B']);
  }
});

test('a new paragraph is its own undo step between typing runs', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(2); await h.type('C');
  await h.enter(); await h.type('D');
  assert.deepEqual(h.chars(), ['A', 'B', 'C', '¶', 'D']);
  for (const expected of [['A', 'B', 'C', '¶'], ['A', 'B', 'C'], ['A', 'B']]) {
    assert.equal(h.shortcut('z', {ctrlKey: true}), true); await h.settle();
    assert.deepEqual(h.chars(), expected);
  }
  await h.finish();
  assert.equal(h.edits.length, 0);
});

test('Ctrl+Alt (AltGr) Z and Y stay with the keyboard', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(2); await h.type('C');
  assert.deepEqual([h.shortcut('z', {ctrlKey: true, altKey: true}), h.shortcut('y', {ctrlKey: true, altKey: true}), h.chars()], [false, false, ['A', 'B', 'C']]);
});

test('a rich note with sizes, script, colour, a line break, two paragraphs and alignment undoes to its original and saves nothing', async () => {
  const h = await noteEditorHarness();
  h.context.editor.info.drawing.notes[0].html = `<p data-style="${h.paragraph}" align="center">x <span data-style="font-size:27px" data-pt="20">B</span>`
    + '<span data-style="font-size:17px" data-script="super" data-base-pixels="27" data-pt="20">2</span><br>y</p>'
    + `<p data-style="${h.paragraph}"><span data-style="color:#c00000">R</span></p>`;
  await h.open(7);
  const original = h.chars();
  await h.caret(1); await h.press({key: 'italic'}); await h.type('Z');
  await h.caret(8); await h.type('W');
  assert.deepEqual(h.chars(), ['x', 'Zi', ' ', 'B@20', '2:super@20', 'y', '¶', 'W', 'R']);
  for (let step = 0; step < 2; step++) { assert.equal(h.shortcut('z', {ctrlKey: true}), true); await h.settle(); }
  assert.deepEqual(h.chars(), original);
  await h.finish();
  assert.equal(h.edits.length, 0);
});

test('browser Undo with nothing to undo still ends an unmatched beforeinput and its pending range', async () => {
  const h = await noteEditorHarness();
  await h.open(7); await h.caret(1); await h.press({key: 'bold'});
  h.element.handlers.beforeinput({inputType: 'insertText', data: 'Q', isComposing: false});
  assert.equal(h.history('historyUndo'), true); await h.settle();
  h.bare('insertText', 'X'); await h.settle();
  assert.deepEqual([h.chars(), h.pressed().bold, h.replies.length], [['A', 'X', 'B'], false, 0]);
});

// File > Export Figure's own menu item and click handler, as the page declares
// them, over an immediate session reply. The page's download helper is
// replaced, so nothing reaches the file system.
test('File > Export Figure downloads the accepted whole-canvas SVG without changing the document', async () => {
  const {runInNewContext} = await import('node:vm');
  const page = await webSource('index.html');
  const source = await webSource('app.mjs');
  const item = /<button\b([^>]*)>Export Figure…<\/button>/.exec(page);
  assert.ok(item && /\bid="export-figure"/.test(item[1]) && !/\bdisabled\b/.test(item[1]), 'File > Export Figure is not an enabled menu item with id export-figure');
  const at = source.indexOf("$('export-figure').onclick");
  assert.ok(at >= 0, 'File > Export Figure has no click handler');
  // Comments and one-export guards declared just before the handler belong to it.
  let start = at;
  for (let end = at - 1; end > 0;) {
    const begin = source.lastIndexOf('\n', end - 1) + 1;
    if (!/^(let |\/\/)/.test(source.slice(begin, end))) break;
    start = begin; end = begin - 1;
  }
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10.5833mm" height="11.9944mm" viewBox="0 0 30 34"/>';
  const elements = {'export-figure': {}}, requests = [], downloads = [], notices = [];
  const context = {
    $: id => elements[id], loading: false,
    editor: {document: {}, busy: false, readOnly: false, info: {session: 's', revision: 4}, name: 'Work.chemvas', canUndo: true, canRedo: false},
    selectedItems: () => [{target: 'bond', id: 0}],
    finishNoteEdit: async () => true,
    api: async (path, body) => { requests.push(JSON.parse(JSON.stringify([path, body]))); return {svg, revision: 4}; },
    download: (...args) => downloads.push(args), noticeSerial: 0,
    notice: (...args) => { notices.push(args); context.noticeSerial++; },
    edit: () => { throw new Error('Export Figure must not edit the document'); },
  };
  const editor = JSON.stringify(context.editor);
  runInNewContext(source.slice(start, source.indexOf('\n};', at) + 3), context);
  await elements['export-figure'].onclick();
  await new Promise(resolve => setImmediate(resolve));
  // The whole canvas as the session's native SVG, named like the desktop's default.
  assert.deepEqual(requests, [['session', {session: 's', revision: 4, action: 'export_figure', format: 'svg', scope: 'sheet'}]]);
  assert.deepEqual(downloads, [[svg, 'Work.svg', 'image/svg+xml']]);
  assert.equal(JSON.stringify(context.editor), editor);
  assert.deepEqual(notices.filter(([, error]) => error), []);
});

// File > Export MOL's own handler over a held note commit and session reply.
async function exportMolHandler() {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const start = source.indexOf('let exportingMol = false');
  const end = source.indexOf('\n};', source.indexOf("$('export-mol').onclick", start)) + 3;
  assert.ok(start >= 0 && end > start);
  const elements = {'export-mol': {}}, requests = [], downloads = [], notices = [], replies = [], commits = [];
  const context = {
    $: id => elements[id], loading: false,
    editor: {document: {}, busy: false, info: {session: 's', revision: 4}, name: 'Work.chemvas'},
    selectedItems: () => [{target: 'bond', id: 0}],
    finishNoteEdit: () => new Promise(resolve => commits.push(resolve)),
    api: (path, body) => new Promise((resolve, reject) => { requests.push(JSON.parse(JSON.stringify([path, body]))); replies.push({resolve, reject}); }),
    download: (...args) => downloads.push(args), noticeSerial: 0,
    notice: (...args) => { notices.push(args); context.noticeSerial++; },
  };
  runInNewContext(source.slice(start, end), context);
  return {context, requests, downloads, notices, replies, commits,
    flush: () => new Promise(resolve => setImmediate(resolve)),
    click: () => elements['export-mol'].onclick()};
}

test('Export MOL commits an open note first, then downloads the selected structure', async () => {
  const h = await exportMolHandler();
  const pending = h.click(); await h.flush();
  assert.deepEqual([h.commits.length, h.requests], [1, []]);
  h.context.editor.info = {session: 's', revision: 5}; h.commits[0](); await h.flush();
  assert.deepEqual(h.requests, [['session', {session: 's', revision: 5, action: 'export_mol', selection: [{target: 'bond', id: 0}]}]]);
  h.replies[0].resolve({molfile: 'MOL\n', revision: 5}); await pending;
  assert.deepEqual([h.downloads, h.notices], [[['MOL\n', 'Work.mol', 'chemical/x-mdl-molfile']], []]);
});

test('Export MOL runs one export at a time and not while busy or loading', async () => {
  const h = await exportMolHandler();
  const pending = h.click(); await h.click(); h.commits[0](); await h.flush(); await h.click();
  assert.deepEqual([h.commits.length, h.requests.length], [1, 1]);
  h.replies[0].resolve({molfile: 'MOL\n', revision: 4}); await pending;
  h.context.editor.busy = true; await h.click();
  h.context.editor.busy = false; h.context.loading = true; await h.click();
  assert.deepEqual([h.commits.length, h.requests.length, h.downloads.length], [1, 1, 1]);
  h.context.loading = false;
  const again = h.click(); h.context.editor.busy = true; h.commits[1](); await again;
  assert.deepEqual([h.commits.length, h.requests.length, h.downloads.length], [2, 1, 1]);
});

test('Export MOL shows a refusal for the current document and downloads nothing', async () => {
  const h = await exportMolHandler();
  const pending = h.click(); h.commits[0](); await h.flush();
  h.replies[0].reject(new Error('Select a molecular structure on the canvas first.')); await pending;
  assert.deepEqual([h.downloads, h.notices], [[], [['Select a molecular structure on the canvas first.', true]]]);
});

test('Export MOL drops a late reply or error once the document changes or turns busy', async () => {
  const changes = [
    context => { context.editor.info = {session: 't', revision: 0}; },
    context => { context.editor.name = 'Other.chemvas'; },
    context => { context.editor.info = {session: 's', revision: 5}; },
    context => { context.editor.busy = true; },
    context => { context.loading = true; },
  ];
  for (const change of changes) {
    for (const settle of ['resolve', 'reject']) {
      const h = await exportMolHandler();
      const pending = h.click(); h.commits[0](); await h.flush();
      change(h.context);
      if (settle === 'resolve') h.replies[0].resolve({molfile: 'MOL\n', revision: 4});
      else h.replies[0].reject(new Error('The drawing changed.'));
      await pending;
      assert.deepEqual([h.requests.length, h.downloads, h.notices], [1, [], []]);
    }
  }
});

test('Export MOL clears an earlier refusal once a current download succeeds', async () => {
  const h = await exportMolHandler();
  const refused = h.click(); h.commits[0](); await h.flush();
  h.replies[0].reject(new Error('Select a molecular structure on the canvas first.')); await refused;
  const exported = h.click(); h.commits[1](); await h.flush();
  h.replies[1].resolve({molfile: 'MOL\n', revision: 4}); await exported;
  assert.deepEqual([h.downloads.length, h.notices], [1, [['Select a molecular structure on the canvas first.', true], []]]);
});

// Export MOL's own handler over a held note commit, refused or answered.
async function refuseMol(h) {
  const pending = h.click(); h.commits.at(-1)(); await h.flush();
  h.replies.at(-1).reject(new Error('Select a molecular structure on the canvas first.')); await pending;
}
async function exportMolOnce(h) {
  const pending = h.click(); h.commits.at(-1)(); await h.flush();
  h.replies.at(-1).resolve({molfile: 'MOL\n', revision: 4}); await pending;
}

test('a successful Export MOL clears only its own refusal while it is still the notice shown', async () => {
  const rows = [
    ['another notice', [h => h.context.notice('Incomplete, read-only preview: images.')], false],
    ['the same text from another action', [refuseMol, h => h.context.notice('Select a molecular structure on the canvas first.', true)], false],
    ['a notice cleared by another action', [refuseMol, h => h.context.notice()], false],
    ['its own refusal', [refuseMol], true],
    ['its second refusal', [refuseMol, refuseMol], true],
  ];
  for (const [label, steps, cleared] of rows) {
    const h = await exportMolHandler();
    for (const step of steps) await step(h);
    const shown = h.notices.length;
    await exportMolOnce(h);
    assert.deepEqual([label, h.downloads.length, h.notices.slice(shown)], [label, 1, cleared ? [[]] : []]);
  }
});

// The real note editor and Export MOL's handler in one context, each note save
// answered by the test and each export answered at once.
async function noteExportHarness(save) {
  const h = await noteEditorHarness();
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const start = source.indexOf('let exportingMol = false');
  const end = source.indexOf('\n};', source.indexOf("$('export-mol').onclick", start)) + 3;
  const elements = {'export-mol': {}}, notices = [], exports = [];
  Object.assign(h.context, {
    $: id => elements[id], noticeSerial: 0, selectedItems: () => [], download() {},
    notice: (...args) => { notices.push(args); h.context.noticeSerial++; },
    edit: async request => { h.edits.push(request); return save(h, request); },
    api: (path, body) => body.action === 'export_mol' ? (exports.push(body.revision), Promise.resolve({molfile: 'MOL\n'})) : new Promise((resolve, reject) => h.replies.push({body, resolve, reject})),
  });
  h.context.editor.name = 'Work.chemvas';
  runInNewContext(source.slice(start, end), h.context);
  return Object.assign(h, {notices, exports, exportMol: async () => { await elements['export-mol'].onclick(); await h.settle(); }});
}

test('a failed note save keeps its text and stops Export MOL without blocking a later export', async () => {
  // label, save answer, change before finishing, reopened, [saves, exports] after the first and second Export
  const rows = [
    ['rejected', () => false, null, true, [1, []], [2, []]],
    ['busy', () => undefined, null, true, [1, []], [2, []]],
    ['applied but its reply lost', h => { h.context.editor.info.revision += 1; return false; }, null, false, [1, []], [1, [4]]],
    ['drawing changed while open', () => true, h => { h.context.editor.info.revision += 1; }, false, [0, []], [0, [4]]],
    ['saved', h => { h.context.editor.info.revision += 1; return true; }, null, false, [1, [4]], [1, [4, 4]]],
  ];
  for (const [label, save, before, reopened, first, second] of rows) {
    const h = await noteExportHarness(save);
    await h.open(7); await h.caret(2); await h.type('X');
    before?.(h);
    h.element.handlers.focusout({relatedTarget: null}); h.element.handlers.focusout({relatedTarget: null});
    await h.exportMol();
    assert.deepEqual([label, h.edits.length, h.exports, Boolean(h.context.noteEditor)], [label, ...first, reopened]);
    if (reopened) assert.deepEqual(h.chars(), ['A', 'B', 'X']);
    await h.exportMol();
    assert.deepEqual([label, h.edits.length, h.exports], [label, ...second]);
  }
});

test('a late note save failure reopens nothing over a newer note or a document load', async () => {
  const rows = [
    ['a newer note', h => h.context.beginNoteEdit(7), true, ['A', 'B']],
    ['a document load', h => { h.context.loading = true; }, false, []],
    ['another session', h => { h.context.editor.info.session = 't'; }, false, []],
  ];
  for (const [label, takeOver, open, chars] of rows) {
    let fail;
    const h = await noteExportHarness(() => new Promise(resolve => { fail = resolve; }));
    await h.open(7); await h.caret(2); await h.type('X');
    h.element.handlers.focusout({relatedTarget: null});
    const exporting = h.exportMol();
    takeOver(h); fail(false); await exporting;
    assert.deepEqual([label, h.edits.length, Boolean(h.context.noteEditor), h.chars(), h.exports], [label, 1, open, chars, []]);
  }
});

test('a reopened note keeps its own Undo, and undoing to its original exports without saving', async () => {
  let answer = false;
  const h = await noteExportHarness(() => answer);
  await h.open(7); await h.caret(2); await h.type('X');
  h.element.handlers.focusout({relatedTarget: null});
  await h.exportMol();
  assert.deepEqual([h.edits.length, h.chars(), h.exports], [1, ['A', 'B', 'X'], []]);
  answer = true;
  assert.equal(h.shortcut('z', {ctrlKey: true}), true); await h.settle();
  assert.deepEqual(h.chars(), ['A', 'B']);
  await h.exportMol();
  assert.deepEqual([h.edits.length, h.exports, h.context.noteEditor], [1, [3], null]);
});

test('a restored note ignores its old normalization and keeps its formats, Undo and Redo', async () => {
  const settle = [
    ['a late reply', h => h.reply(0, h.markup('A<span data-style="font-weight:700">X</span>B'))],
    ['a late error', async h => { h.replies[0].reject(new Error('Markup failed.')); await h.settle(); }],
  ];
  for (const [label, release] of settle) {
    const h = await noteExportHarness(h => { h.context.notice('Note save failed.', true); return false; });
    await h.open(7); await h.caret(1); await h.press({key: 'bold'}); await h.type('X');
    h.element.handlers.focusout({relatedTarget: null}); await h.settle();
    assert.deepEqual([label, Boolean(h.context.noteEditor), h.chars(), h.selection()], [label, true, ['A', 'Xb', 'B'], [2, 2]]);
    const written = h.writes.length;
    await release(h);
    assert.deepEqual([label, h.writes.length, h.replies.length, h.notices], [label, written, 1, [['Note save failed.', true]]]);
    h.shortcut('z', {ctrlKey: true}); await h.settle();
    assert.deepEqual([label, h.chars()], [label, ['A', 'B']]);
    h.shortcut('y', {ctrlKey: true}); await h.settle();
    assert.deepEqual([label, h.chars()], [label, ['A', 'Xb', 'B']]);
    await h.caret(3); await h.press({key: 'italic'}); await h.type('Y');
    assert.deepEqual([label, h.replies.length, h.chars()], [label, 2, ['A', 'Xb', 'B', 'Yi']]);
  }
});

test('a restored rich note keeps its formats and saves the identical text again', async () => {
  let answer = false;
  const h = await noteExportHarness(() => answer);
  h.context.editor.info.drawing.notes[0].html = `<p data-style="${h.paragraph}" align="center">x <span data-style="font-size:27px" data-pt="20">B</span>`
    + '<span data-style="font-size:17px" data-script="super" data-base-pixels="27" data-pt="20">2</span><br><span data-style="font-style:italic">y</span></p>';
  await h.open(7); await h.caret(1); await h.type('Z');
  const typed = h.chars();
  assert.deepEqual(typed, ['x', 'Z', ' ', 'B@20', '2:super@20', 'yi']);
  h.element.handlers.focusout({relatedTarget: null}); await h.settle();
  assert.deepEqual([Boolean(h.context.noteEditor), h.chars()], [true, typed]);
  answer = true; await h.finish();
  assert.deepEqual([h.edits.length, h.edits[1].html, h.context.noteEditor], [2, h.edits[0].html, null]);
});

test('a note whose save fails after a tool switch reopens under the Text tool', async () => {
  let fail;
  const h = await noteExportHarness(() => new Promise(resolve => { fail = resolve; }));
  await h.open(7); await h.caret(2); await h.type('X');
  h.element.handlers.focusout({relatedTarget: null});
  h.context.tool = 'bond'; fail(false); await h.settle();
  assert.deepEqual([h.context.tool, Boolean(h.context.noteEditor), h.chars()], ['note', true, ['A', 'B', 'X']]);
});

test('a new note whose save fails reopens at its place once, and one applied with its reply lost is never sent again', async () => {
  const rows = [
    ['rejected', () => false, true, [2, []]],
    ['applied but its reply lost', h => { h.context.editor.info.revision += 1; return false; }, false, [1, [4]]],
  ];
  for (const [label, save, reopened, second] of rows) {
    const h = await noteExportHarness(save);
    await h.open(null, 5, 6); await h.type('N');
    h.element.handlers.focusout({relatedTarget: null});
    await h.exportMol();
    const restored = h.context.noteEditor;
    assert.deepEqual([label, h.edits.length, h.exports, Boolean(restored)], [label, 1, [], reopened]);
    if (reopened) assert.deepEqual([label, restored.id, restored.x, restored.y, [...h.context.selection], h.chars()], [label, null, 5, 6, [], ['N']]);
    await h.exportMol();
    assert.deepEqual([label, h.edits.length, h.exports], [label, ...second]);
    assert.ok(h.edits.every(edit => edit.kind === 'note_text' && edit.id === null && edit.x === 5 && edit.y === 6), label);
  }
});

test('a failed note save stops a Text-tool press and keeps the reopened text and its notice', async () => {
  const h = await noteExportHarness(h => { h.context.notice('Note save failed.', true); return false; });
  Object.assign(h.context, {point: event => ({x: event.clientX, y: event.clientY}), hitsAt: () => [], viewScale: () => 1});
  await h.open(7); await h.caret(2); await h.type('X');
  h.element.handlers.focusout({relatedTarget: null});
  void h.context.noteToolPress({clientX: 12, clientY: 34}); await h.settle();
  assert.deepEqual([h.replies.map(reply => reply.body.action), Boolean(h.context.noteEditor), h.chars(), h.notices],
    [[], true, ['A', 'B', 'X'], [['Note save failed.', true]]]);
});

test('an Export MOL stopped by a failed note save keeps that failure notice', async () => {
  const rows = [
    ['rejected', h => { h.context.notice('Note save failed.', true); return false; }, null, ['Note save failed.', true]],
    ['drawing changed while open', () => true, h => { h.context.editor.info.revision += 1; },
      ['The drawing changed while the note was open; its text was not saved.', true]],
  ];
  for (const [label, save, before, shown] of rows) {
    const h = await noteExportHarness(save);
    await h.open(7); await h.caret(2); await h.type('X');
    before?.(h);
    h.element.handlers.focusout({relatedTarget: null});
    await h.exportMol();
    assert.deepEqual([label, h.exports, h.notices], [label, [], [shown]]);
  }
});

test('valence feedback sits on the desktop item rect: a label selection rect or a hidden carbon dot', async () => {
  const {valenceWarningMarkup, valenceWarningBounds} = await import('../app/chemvas/web/scene.mjs');
  const source = info(2), style = {color: '#b91c1c'}, view = [0, 0, 400, 300];
  const drawing = {...source.drawing, atom_hit_radii: {0: 6.5, 1: null}, atom_selection_rects: {1: [44, 32, 12, 16]}};
  assert.deepEqual([0, 1].map(id => valenceWarningBounds(source.document, drawing, id)), [[23.5, 33.5, 13, 13], [44, 32, 12, 16]]);
  const markup = valenceWarningMarkup(source.document, [0, 1], drawing, style, 2, view);
  const path = id => markup.match(new RegExp(`<path data-valence-warning="${id}" d="([^"]+)"([^>]*)/>`));
  assert.ok(path(0)[1].startsWith('M22.0000 48.0000 L23.0000 49.0000 L24.0000 48.0000') && path(0)[1].endsWith('L38.0000 48.0000'));
  assert.equal(path(0)[1].split(' L').length, 17);
  assert.ok(path(1)[1].startsWith('M42.5000 49.5000 L43.5000 50.5000') && path(1)[1].endsWith('L57.5000 50.5000'));
  for (const id of [0, 1]) assert.match(path(id)[2], /fill="none" stroke="#b91c1c" stroke-width="1" stroke-linecap="square" stroke-linejoin="bevel" vector-effect="non-scaling-stroke"/);
  const unmeasured = valenceWarningMarkup(source.document, [0, 1], {...drawing, atom_selection_rects: {}}, style, 2, view);
  assert.deepEqual([...unmeasured.matchAll(/data-valence-warning="(\d+)"/g)].map(match => match[1]), ['0']);
  assert.equal(valenceWarningMarkup(source.document, [0, 1], {...drawing, needs_measurements: true}, style, 2, view), '');
  assert.equal(valenceWarningMarkup(source.document, [0, 1], drawing, null, 2, view), '');
});

// View > Valence Checking's own render helper and menu handler over a held editor.
async function valenceFeedbackHandler() {
  const {runInNewContext} = await import('node:vm');
  const {valenceWarningMarkup} = await import('../app/chemvas/web/scene.mjs');
  const source = await webSource('app.mjs');
  const start = source.indexOf('function valenceFeedback()');
  const end = source.indexOf('\n', source.indexOf("$('valence-toggle').onclick", start));
  assert.ok(start >= 0 && end > start);
  const accepted = info(2), elements = {'valence-toggle': {}}, calls = [];
  Object.assign(accepted.drawing, {valence_warnings: [0], atom_selection_rects: {1: [44, 32, 12, 16]}});
  const context = {
    $: id => elements[id], valenceChecking: true, previewInfo: null, ui: {valence_warning: {color: '#b91c1c'}}, viewScale: () => 1, visibleSceneRect: () => [0, 0, 400, 300],
    editor: {document: accepted.document, info: {drawing: accepted.drawing, revision: 3}, dirty: false, canUndo: false},
    valenceWarningMarkup, render: () => calls.push('render'), api: () => calls.push('api'),
  };
  runInNewContext(source.slice(start, end), context);
  return {context, elements, calls, accepted, source};
}

test('valence feedback takes ids from the accepted drawing, at the positions the canvas shows', async () => {
  const {context, accepted} = await valenceFeedbackHandler();
  const starts = () => [...context.valenceFeedback().matchAll(/data-valence-warning="(\d+)" d="M([\d.]+) /g)].map(match => [match[1], match[2]]);
  assert.deepEqual(starts(), [['0', '20.6000']]);
  // A move preview carries the accepted warning to where the atom is shown.
  const moved = structuredClone(accepted.document);
  moved.state.model.atoms[0].x = 50;
  context.previewInfo = {document: moved, drawing: accepted.drawing};
  assert.deepEqual(starts(), [['0', '40.6000']]);
  // A drawing preview's own warnings wait until the edit is accepted.
  context.previewInfo = {document: accepted.document, drawing: {...accepted.drawing, valence_warnings: [0, 1]}};
  context.editor.info.drawing = {...accepted.drawing, valence_warnings: []};
  assert.deepEqual(starts(), []);
  context.previewInfo = null;
  context.editor.info.drawing = {...accepted.drawing, valence_warnings: [0, 1]};
  assert.deepEqual(starts().map(([id]) => id), ['0', '1']);
});

test('View > Valence Checking toggles only the view: no request, history, dirty state or title change', async () => {
  const {context, elements, calls, source} = await valenceFeedbackHandler();
  const editor = JSON.stringify(context.editor);
  elements['valence-toggle'].onclick();
  assert.deepEqual([context.valenceChecking, context.valenceFeedback(), calls], [false, '', ['render']]);
  elements['valence-toggle'].onclick();
  assert.deepEqual([context.valenceChecking, calls], [true, ['render', 'render']]);
  assert.equal(JSON.stringify(context.editor), editor);
  // New Canvas and Open both load a drawing, which starts with it on, as a fresh desktop canvas does.
  assert.match(source, /grid = \{enabled:false[^\n]*\n\s*valenceChecking = true;/);
});

test('valence feedback draws nothing for unusable numbers and only the visible steps of each warning', async () => {
  const {valenceWarningMarkup} = await import('../app/chemvas/web/scene.mjs');
  const source = info(2), style = {color: '#b91c1c'}, view = [0, 0, 400, 300];
  const drawing = {...source.drawing, atom_hit_radii: {0: 6.5, 1: null}, atom_selection_rects: {1: [44, 32, 12, 16]}};
  const draw = (rect, scale = 2, viewport = view) => valenceWarningMarkup(source.document, [0, 1], {...drawing, atom_selection_rects: {1: rect}}, style, scale, viewport);
  const warned = markup => [...markup.matchAll(/data-valence-warning="(\d+)"/g)].map(match => match[1]);
  const points = markup => markup.match(/data-valence-warning="1" d="([^"]+)"/)[1].split(/ ?[ML]/).slice(1).map(point => point.split(' ').map(Number));
  for (const scale of [0, -1, NaN, Infinity, -Infinity, undefined, 1e-320]) assert.equal(valenceWarningMarkup(source.document, [0, 1], drawing, style, scale, view), '', String(scale));
  // A view that is not finite, is empty, or whose far edge overflows draws nothing.
  for (const viewport of [undefined, [0, 0, 400], [NaN, 0, 400, 300], [0, 0, Infinity, 300], [0, 0, 0, 300], [0, 0, 400, 0], [0, 0, -1, 300], [1e308, 0, 1e308, 300], [0, 1e308, 400, 1e308]]) {
    assert.equal(valenceWarningMarkup(source.document, [0, 1], drawing, style, 2, viewport), '', String(viewport));
  }
  // Unusable rects, items off each side of the view, and steps too far from the
  // item's edge to count exactly draw nothing for that atom alone.
  for (const rect of [[NaN, 32, 12, 16], [44, Infinity, 12, 16], [44, 32, -1, 16], [44, 32, 12, -Infinity], [-12, 100, 12, 16], [400, 100, 12, 16], [100, -16, 12, 16], [100, 300, 12, 16], [-1e300, 10, 2e300, 10], [-1e308, 10, 1.7e308, 10]]) {
    const markup = draw(rect);
    assert.deepEqual(warned(markup), ['0'], String(rect));
    assert.ok(!/NaN|Infinity/.test(markup), String(rect));
  }
  assert.equal(valenceWarningMarkup(source.document, [1], {...drawing, atom_selection_rects: {1: [1.6e308, 0, 1, 1]}}, style, 1e-307, [1.5e308, -1, 2e307, 10]), '');
  // Items just inside an edge keep the steps of their whole zigzag that the view shows.
  const whole = [-100, -100, 600, 500];
  assert.deepEqual(points(draw([399, 299, 12, 16])), points(draw([399, 299, 12, 16], 2, whole)).slice(0, 5));
  assert.deepEqual(points(draw([-11, -15, 12, 16])), points(draw([-11, -15, 12, 16], 2, whole)).slice(-5));
  assert.equal(points(draw([44, 32, 1e300, 16])).length, 360);
  // Panning by 1, 2 or 3 px leaves every step where it was.
  const wide = [-1e6, 10, 2e6, 10], still = points(draw(wide, 1, [0, 0, 800, 600]));
  assert.deepEqual(still.slice(0, 2), [[-3, 23], [-1, 25]]);
  for (const pan of [0, 1, 2, 3]) {
    const moved = points(draw(wide, 1, [pan, 0, 800, 600])), shared = moved.filter(([x]) => x <= still.at(-1)[0]);
    assert.ok(moved.length <= 800 / 2 + 4 && moved[0][0] < pan && moved.at(-1)[0] > pan + 800, String(pan));
    assert.deepEqual(shared, still.slice(still.findIndex(([x]) => x === shared[0][0])), String(pan));
  }
  // Beyond the 5x zoom limit, as a resized window gives, the native zigzag still
  // draws, and a narrow view keeps its part of it.
  const close = points(draw([5, 5, 4, 2], 40, [0, 0, 20, 15]));
  assert.deepEqual([close.length, close[0], close[1]], [84, [4.925, 7.075], [4.975, 7.125]]);
  assert.deepEqual(points(draw([5, 5, 4, 2], 40, [6, 0, 1, 15])), close.slice(20, 44));
});

test('valence feedback draws at most 50,000 points a view, leaving later warnings out', async () => {
  const {valenceWarningMarkup} = await import('../app/chemvas/web/scene.mjs');
  const many = info(2000), ids = Object.keys(many.document.state.model.atoms).map(Number), wide = [-1e9, 10, 2e9, 10];
  const markup = valenceWarningMarkup(many.document, ids, {...many.drawing, atom_selection_rects: Object.fromEntries(ids.map(id => [id, wide]))}, {color: '#b91c1c'}, 2, [0, 0, 400, 300]);
  const paths = [...markup.matchAll(/data-valence-warning="(\d+)" d="([^"]+)"/g)];
  // Each warning in view keeps 404 points, so the first 123 fit and the rest wait.
  assert.deepEqual(paths.map(([, id]) => Number(id)), ids.slice(0, 123));
  for (const [, , d] of paths) {
    assert.equal(d.split(' L').length, 404);
    assert.ok(d.startsWith('M-1.5000 21.5000 L-0.5000 22.5000 L0.5000 21.5000') && d.endsWith('L401.5000 22.5000'));
  }
});

// Gesture previews' real request loop, release and cancel over held replies.
async function gesturePreviewHarness(sessionRequest) {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const code = ['async function refreshGesturePreview() {', 'async function finishHandle(active) {', 'function cancelGesture() {', 'function handleRequest(active, end) {'].map(marker => {
    const start = source.indexOf(marker), end = source.indexOf('\n}\n', start) + 2;
    assert.ok(start >= 0 && end > start, marker);
    return source.slice(start, end);
  }).join('\n');
  const requests = [], replies = [], renders = [], edits = [];
  const request = name => (active, end) => ({request: name, kind: active.kind, end: [end.x, end.y]});
  const send = body => { requests.push(JSON.parse(JSON.stringify(body))); return new Promise(resolve => replies.push(resolve)); };
  const context = {
    gesture: null, preview: null, previewSerial: 0, previewPending: null, previewInfo: null, markHover: {}, selection: new Set(),
    editor: {info: {session: 's', revision: 3}}, selectedItems: () => [{target: 'atom', id: 0}], gridMode: () => 'off',
    sessionRequest: sessionRequest ? body => sessionRequest(body, send) : send,
    render: () => renders.push(context.previewInfo), edit: change => edits.push(JSON.parse(JSON.stringify(change))),
    canvas: {hasPointerCapture: () => false},
    rotationRequest: request('rotation'), moveRequest: request('move'), arrowRequest: request('arrow'),
    shapeRequest: request('shape'), bracketRequest: request('bracket'), bondRequest: request('bond'),
  };
  runInNewContext(code, context);
  const reply = async (index, value) => { replies[index](value); await new Promise(resolve => setImmediate(resolve)); };
  const start = (kind, end, owner = context.editor.info) => {
    context.gesture = {kind, target: 'arrow', id: 0, handle: 'end', previous: null, moved: true, released: false, scale: 1, end, session: owner.session, revision: owner.revision};
    context.preview = {kind, end};
    return context.gesture;
  };
  const move = end => { context.previewSerial++; context.preview = {kind: context.gesture.kind, end}; context.gesture.end = end; };
  return {context, requests, renders, edits, reply, start, move};
}
const arrowHandleDrawing = point => ({arrows: [{handles: [{handle: 'end', point}]}]});

test('a gesture preview reply counts only for its own gesture, session and revision', async () => {
  const rows = [
    ['the current gesture', () => {}, {session: 's', revision: 3}, true, 1],
    ['another session', c => { c.editor.info = {session: 't', revision: 1}; }, {session: 's', revision: 3}, false, 1],
    ['a newer revision', c => { c.editor.info = {session: 's', revision: 4}; }, {session: 's', revision: 3}, false, 1],
    ['a replaced gesture', c => { c.gesture = {...c.gesture, previous: null}; }, {session: 's', revision: 3}, false, 2],
    ['a reply from another session', () => {}, {session: 't', revision: 3}, false, 1],
    ['a reply at another revision', () => {}, {session: 's', revision: 2}, false, 1],
  ];
  for (const [label, change, owner, used, sent] of rows) {
    const h = await gesturePreviewHarness();
    const active = h.start('handle', {x: 1, y: 2}), pending = h.context.refreshGesturePreview();
    assert.deepEqual(h.requests, [{session: 's', revision: 3, action: 'preview', edit: {kind: 'arrow_handle', grid: 'off', id: 0, handle: 'end', position: [1, 2], previous: null, scale: 1}, selection: [{target: 'atom', id: 0}]}], label);
    change(h.context);
    await h.reply(0, {...owner, drawing: arrowHandleDrawing([5, 6])}); await pending;
    // Only the owner's reply is shown or carried; a replaced gesture asks once for itself.
    assert.deepEqual([label, h.context.previewInfo?.revision ?? null, h.renders.length, active.previous, h.requests.length], [label, used ? 3 : null, used ? 1 : 0, used ? [5, 6] : null, sent]);
  }
});

test('a new gesture while an old preview is pending gets exactly one request of its own', async () => {
  const h = await gesturePreviewHarness();
  h.start('arrow', {x: 1, y: 2});
  const old = h.context.refreshGesturePreview();
  h.context.cancelGesture();
  h.context.editor.info = {session: 's', revision: 4};
  h.start('line', {x: 9, y: 8});
  await h.context.refreshGesturePreview();
  assert.equal(h.requests.length, 1);
  await h.reply(0, {session: 's', revision: 3, drawing: {}}); await old;
  assert.deepEqual(h.requests, [
    {session: 's', revision: 3, action: 'preview', edit: {request: 'arrow', kind: 'arrow', end: [1, 2]}, selection: [{target: 'atom', id: 0}]},
    {session: 's', revision: 4, action: 'preview', edit: {request: 'arrow', kind: 'line', end: [9, 8]}, selection: [{target: 'atom', id: 0}]},
  ]);
  assert.deepEqual([h.context.previewInfo, h.renders], [null, [null]]);
  const fresh = {session: 's', revision: 4, drawing: {}};
  await h.reply(1, fresh);
  assert.deepEqual([h.context.previewInfo === fresh, h.renders.length, h.requests.length], [true, 2, 2]);
});

test('a delayed preview never asks again for its gesture against a newer document', async () => {
  for (const current of [{session: 's', revision: 4}, {session: 't', revision: 1}]) {
    const h = await gesturePreviewHarness();
    h.start('move', {x: 1, y: 2});
    const pending = h.context.refreshGesturePreview();
    h.move({x: 3, y: 4}); h.context.editor.info = current;
    await h.reply(0, {session: 's', revision: 3, drawing: {}}); await pending;
    await h.context.refreshGesturePreview();
    assert.deepEqual([h.requests.length, h.context.previewInfo, h.renders.length], [1, null, 0]);
  }
});

test('handle moves coalesce behind one preview, and the release edit uses the point it carried', async () => {
  const h = await gesturePreviewHarness();
  const active = h.start('handle', {x: 1, y: 2});
  const first = h.context.refreshGesturePreview();
  h.move({x: 3, y: 4}); await h.context.refreshGesturePreview();
  h.move({x: 5, y: 6}); await h.context.refreshGesturePreview();
  assert.equal(h.requests.length, 1);
  await h.reply(0, {session: 's', revision: 3, drawing: arrowHandleDrawing([7, 8])}); await first;
  // Too old to show, the reply still carries its point, and the latest end is asked once.
  assert.deepEqual([active.previous, h.context.previewInfo, h.requests.length], [[7, 8], null, 2]);
  assert.deepEqual(h.requests[1].edit, {kind: 'arrow_handle', grid: 'off', id: 0, handle: 'end', position: [5, 6], previous: [7, 8], scale: 1});
  // The release waits for that preview, and its final edit keeps the point it carries.
  h.move({x: 5.1, y: 6});
  const released = h.context.finishHandle(active);
  await h.reply(1, {session: 's', revision: 3, drawing: arrowHandleDrawing([9, 10])}); await released;
  assert.deepEqual(h.edits, [{kind: 'arrow_handle', grid: 'off', id: 0, handle: 'end', position: [5.1, 6], previous: [9, 10], scale: 1}]);
  assert.deepEqual([h.context.gesture, h.context.previewInfo, h.requests.length], [null, null, 2]);
});

test('a preview completed by a font measurement counts only for the revision it was asked at', async () => {
  const rows = [['unchanged', false, 3, true], ['an edit accepted between the steps', true, 3, false], ['measured at a newer revision', false, 4, false]];
  for (const [label, changed, measuredAt, used] of rows) {
    const h = await gesturePreviewHarness((body, send) => sessionDrawing(body, send, () => ({metrics: {}, ink: {}})));
    h.start('move', {x: 1, y: 2});
    const pending = h.context.refreshGesturePreview();
    await h.reply(0, {session: 's', revision: 3, drawing: {needs_measurements: true, label_measurements: {}}});
    assert.deepEqual(h.requests.map(request => [request.action, request.revision]), [['preview', 3], ['measure', 3]], label);
    if (changed) h.context.editor.info = {session: 's', revision: 4};
    await h.reply(1, {session: 's', revision: measuredAt, drawing: {}}); await pending;
    assert.deepEqual([label, h.context.previewInfo?.revision ?? null, h.renders.length], [label, used ? 3 : null, used ? 1 : 0]);
  }
});

test('drawing snap rings: held Line and Arrow requests take the live view scale after a zoom', async () => {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const slice = (marker, close = '\n}\n') => {
    const start = source.indexOf(marker), end = source.indexOf(close, start) + close.length;
    assert.ok(start >= 0 && end > start, marker);
    return source.slice(start, end);
  };
  // The page's own view scale, keyboard zoom, request, preview loop and release.
  const code = [
    slice('const viewScale = ', '\n'), slice('function zoom(factor) {'), slice('function arrowRequest(active, end) {'),
    slice('async function refreshGesturePreview() {'), slice('function cancelGesture() {'),
    slice("canvas.addEventListener('pointerup', event => {", '\n});'), 'liveScale = viewScale;',
  ].join('\n');
  for (const kind of ['line', 'arrow']) {
    const requests = [], edits = [], handlers = {};
    const context = {
      gesture: null, preview: null, previewSerial: 0, previewPending: null, previewInfo: null, markHover: {}, selection: new Set(),
      view: {x: -400, y: -300, width: 800, height: 600}, ui: {navigation: {min: .2, max: 5, step: 1.25}, drag_distance: 10},
      canvas: {clientWidth: 800, clientHeight: 600, hasPointerCapture: () => false, addEventListener: (type, handler) => { handlers[type] = handler; }},
      editor: {info: {session: 's', revision: 3}}, zoomView, gridMode: () => 'none', selectedItems: () => [],
      point: event => event.scene, render() {}, refreshHover() {},
      sessionRequest: async body => { requests.push(JSON.parse(JSON.stringify(body))); return {session: 's', revision: 3, drawing: {}}; },
      edit: async change => { edits.push(JSON.parse(JSON.stringify(change))); return true; },
    };
    runInNewContext(code, context);
    const start = {x: 102, y: 98}, style = kind === 'line' ? 'line' : 'reaction';
    const active = context.gesture = {kind, start, pointer: 1, pressX: 0, pressY: 0, dragged: false, shift: false, style, stroke: null,
      scale: context.liveScale(), hits: [], session: 's', revision: 3};
    // Zoom by keyboard while the button is held; the next move asks for a preview.
    context.zoom(1 / context.ui.navigation.step);
    const previewed = context.liveScale();
    context.preview = {kind: 'arrow', start, end: {x: 163, y: 103}}; context.previewSerial++;
    await context.refreshGesturePreview();
    // Zoom again before the release commits.
    context.zoom(1 / context.ui.navigation.step);
    const released = context.liveScale();
    assert.equal(active.scale, 1, kind);
    assert.ok(Math.abs(previewed - 1.25) < 1e-12 && Math.abs(released - 1.5625) < 1e-12, kind);
    handlers.pointerup({scene: {x: 163, y: 103}, clientX: 61, clientY: 5, shiftKey: false});
    // The snap reach is on screen: each request takes the scale shown when it is made.
    assert.deepEqual([kind, requests.map(request => request.edit.scale), edits.map(change => change.scale)], [kind, [previewed], [released]]);
    assert.deepEqual([requests[0].edit.start, requests[0].edit.end, edits[0].start, edits[0].end, edits[0].style], [[102, 98], [163, 103], [102, 98], [163, 103], style]);
    assert.deepEqual([active.scale, active.start, active.style], [1, start, style]);
  }
});

// A held Line or Arrow preview, its reply delayed across each change in turn;
// the controls run before the keyboard zoom, so they report even if it fails.
async function heldPreviewAcrossViewChange(kind) {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const slice = (marker, close = '\n}\n') => {
    const start = source.indexOf(marker), end = source.indexOf(close, start) + close.length;
    assert.ok(start >= 0 && end > start, marker);
    return source.slice(start, end);
  };
  // The page's own view scale, keyboard zoom, request, preview loop and cancellation.
  const code = [
    slice('const viewScale = ', '\n'), slice('function zoom(factor) {'), slice('function arrowRequest(active, end) {'),
    slice('async function refreshGesturePreview() {'), slice('function cancelGesture() {'), 'liveScale = viewScale;',
  ].join('\n');
  // label, change while the reply is held, whether that reply may then be shown
  const rows = [
    ['no view change', () => {}, true],
    ['cancelled gesture', c => c.cancelGesture(), false],
    ['newer revision', c => { c.editor.info = {session: 's', revision: 4}; }, false],
    ['other session', c => { c.editor.info = {session: 't', revision: 3}; }, false],
    ['keyboard zoom', c => c.zoom(1 / c.ui.navigation.step), false],
  ];
  for (const [label, change, shown] of rows) {
    const requests = [], replies = [], row = `${kind}: ${label}`;
    const context = {
      gesture: null, preview: null, previewSerial: 0, previewPending: null, previewInfo: null, markHover: {}, selection: new Set(),
      view: {x: -400, y: -300, width: 800, height: 600}, ui: {navigation: {min: .2, max: 5, step: 1.25}, drag_distance: 10},
      canvas: {clientWidth: 800, clientHeight: 600, hasPointerCapture: () => false},
      editor: {info: {session: 's', revision: 3}}, zoomView, gridMode: () => 'none', selectedItems: () => [],
      render() {}, refreshHover() {},
      sessionRequest: body => { requests.push(JSON.parse(JSON.stringify(body))); return new Promise(resolve => replies.push(resolve)); },
    };
    runInNewContext(code, context);
    const start = {x: 102, y: 98};
    context.gesture = {kind, start, pointer: 1, pressX: 0, pressY: 0, dragged: true, shift: false, style: kind === 'line' ? 'line' : 'reaction',
      stroke: null, scale: context.liveScale(), hits: [], session: 's', revision: 3};
    context.preview = {kind: 'arrow', start, end: {x: 170, y: 106}}; context.previewSerial++;
    const pending = context.refreshGesturePreview();
    // The request in flight was asked at 100 %.
    assert.deepEqual([row, requests.length, requests[0].edit.scale], [row, 1, 1]);
    change(context);
    assert.ok(Math.abs(context.liveScale() - (label === 'keyboard zoom' ? 1.25 : 1)) < 1e-12, row);
    // 11.7 scene units from the arrow's end: inside the 12 px reach at 100 %, not
    // at 125 %. The reply carries the ring its own request's reach gave.
    const held = {session: 's', revision: 3, drawing: {}, snap_marks: [[160, 100]]};
    replies[0](held); await pending;
    // previewInfo is what render() gives sceneMarkup as the rings to draw.
    assert.equal(context.previewInfo === held, shown, row);
  }
}

test('drawing snap rings: a Line preview asked before a keyboard zoom is not shown after it', () => heldPreviewAcrossViewChange('line'));
test('drawing snap rings: an Arrow preview asked before a keyboard zoom is not shown after it', () => heldPreviewAcrossViewChange('arrow'));

// The real render over stubbed page elements, logging what each layer is given.
async function renderHarness() {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const start = source.indexOf('function render() {'), end = source.indexOf('\n}\n', start) + 2;
  assert.ok(start >= 0 && end > start);
  const accepted = info(1), log = [], elements = {};
  const outline = {key: JSON.stringify({session: 's', revision: 4, action: 'selection', selection: []}), components: [[{rect: [0, 0, 1, 1]}]], frame: 'accepted frame', groups: []};
  const context = {
    editor: {document: accepted.document, info: {session: 's', revision: 4, sheet: accepted.sheet, drawing: accepted.drawing}, name: 'Untitled', dirty: false},
    loading: false, tool: 'select', selection: new Set(['atom:0']), handleTarget: null, contextPage: null, paintColor: null,
    document: {title: '', querySelectorAll: () => [], querySelector: () => null}, $: id => elements[id] ??= {setAttribute() {}},
    view: {x: 0, y: 0, width: 10, height: 10}, clampView: () => ({x: 1, y: 2, width: 30, height: 20}), viewScale: () => 10,
    canvas: {clientWidth: 300, clientHeight: 200, dataset: {}, setAttribute: (name, value) => log.push([name, value]), getScreenCTM: () => null},
    ui: {title: {unsaved_marker: '*', suffix: 'Chemvas'}, tool_names: {}, context_pages: {}, hints: {}},
    grid: {enabled: false, opacity: 0.5}, gridMode: () => 'off', gridMarkup: () => '', valenceChecking: true,
    outlineRequest: null, outlineResult: outline, selectedItems: () => [], previewInfo: null,
    sceneMarkup: (document, options) => { log.push(['scene', document, options.drawing, options.components]); return ''; },
    valenceFeedback: () => { log.push(['valence', context.previewInfo]); return ''; },
    selectionFrameMarkup: (frame, drawing) => { log.push(['frame', frame, drawing]); return {outline: '', handle: ''}; },
    scenePreview: () => null, markHover: {result: null}, imageUrl: () => null, templateHover: {result: null}, bondHover: {result: null},
    positionNoteEditor() {}, refreshTextFormatState() {}, groupBoxesMarkup: () => '', refreshSelectionOutline() {},
  };
  runInNewContext(source.slice(start, end), context);
  return {context, log, outline};
}

test('render drops a published preview of an earlier session or revision before any layer reads it', async () => {
  for (const [label, owner, kept] of [['current', {session: 's', revision: 4}, true], ['older revision', {session: 's', revision: 3}, false], ['other session', {session: 't', revision: 4}, false]]) {
    const {context, log, outline} = await renderHarness();
    const preview = {...owner, document: structuredClone(context.editor.document), drawing: {...context.editor.info.drawing}, selection_components: [], selection_frame: 'preview frame', selection_groups: []};
    context.previewInfo = preview;
    context.render();
    const shown = kept ? preview : null, drawing = kept ? preview.drawing : context.editor.info.drawing;
    const [scene, valence, frame] = ['scene', 'valence', 'frame'].map(kind => log.find(entry => entry[0] === kind));
    assert.equal(context.previewInfo, shown, label);
    assert.deepEqual([scene[1] === (kept ? preview.document : context.editor.document), scene[2] === drawing, scene[3] === (kept ? preview.selection_components : outline.components)], [true, true, true], label);
    assert.equal(valence[1], shown, label);
    assert.deepEqual([frame[1], frame[2] === drawing], [kept ? 'preview frame' : outline.frame, true], label);
  }
});

test('render moves the view before the valence feedback reads the screen transform', async () => {
  const {context, log} = await renderHarness();
  context.render();
  assert.deepEqual(log.map(([kind, value]) => kind === 'viewBox' ? value : kind), ['1 2 30 20', 'scene', 'valence', 'frame']);
  assert.deepEqual({...context.view}, {x: 1, y: 2, width: 30, height: 20});
});

test('drawing snap rings use only the current gesture preview', async () => {
  const marks = [[100, 100]];
  const rows = [
    ['current preview', {session: 's', revision: 4}, true, false],
    ['no or cancelled preview', null, false, false],
    ['older revision', {session: 's', revision: 3}, false, false],
    ['other session', {session: 't', revision: 4}, false, false],
    ['Ring ghost', null, false, true],
  ];
  for (const [label, owner, shown, ghosts] of rows) {
    const {context} = await renderHarness();
    let options = null;
    context.sceneMarkup = (_document, given) => { options = given; return ''; };
    context.ui.snap_mark = {size: 16, width: 1.6, color: '#00a3ff'};
    // Accepted state and the other previews never bring rings to the scene.
    context.editor.info.snap_marks = [[1, 2]];
    if (owner) context.previewInfo = {...owner, document: context.editor.document, drawing: context.editor.info.drawing, snap_marks: marks};
    if (ghosts) context.templateHover = {result: {snap_marks: [[5, 6]]}};
    context.render();
    if (shown) assert.equal(options.snapMarks, marks, label);
    else assert.ok(!options.snapMarks?.length, label);
    assert.equal(options.snapMarkStyle, context.ui.snap_mark, label);
    assert.equal(options.scale, 10, label);
  }
});

test('Bond hover draws planner primitives faintly, rings its target and is never picked', async () => {
  const {bondHoverMarkup} = await import('../app/chemvas/web/scene.mjs');
  assert.equal(typeof bondHoverMarkup, 'function', 'scene.mjs draws no Bond hover preview');
  const preview = {
    primitives: [{line: [10, 20, 30, 20]}, {line: [5, 5, 5, 5]}, {polygon: [[0, 0], [4, 2], [4, -2]], outlined: true},
      {polygon: [[1, 1], [2, 2], [3, 1]], outlined: false}, {dots: [[7, 8]], radius: 0.8}],
    width: 1.6, color: [120, 120, 120, 140], opacity: 0.55, z: 4.5,
    target: {circle: [10, 20, 5], z: 5}, pen: [13, 148, 136, 150], brush: [13, 148, 136, 30],
  };
  const before = JSON.stringify(preview), grey = `rgba(120,120,120,${140 / 255})`;
  const svg = bondHoverMarkup(preview);
  // HoverController's grey at its 0.55 item opacity, over the planner's own primitives.
  assert.ok(svg.startsWith(`<g data-bond-hover="preview" opacity="0.5500" fill="none" stroke="${grey}" stroke-width="1.6000" stroke-linecap="round">`));
  assert.ok(svg.includes('<line x1="10.0000" y1="20.0000" x2="30.0000" y2="20.0000" />'));
  assert.ok(!svg.includes('x1="5.0000"'), 'a collapsed line is not painted');
  assert.ok(svg.includes(`<polygon points="0.0000,0.0000 4.0000,2.0000 4.0000,-2.0000" fill="${grey}" />`));
  assert.ok(svg.includes(`<polygon points="1.0000,1.0000 2.0000,2.0000 3.0000,1.0000" fill="${grey}" stroke="none"/>`));
  assert.ok(svg.includes(`<circle cx="7.0000" cy="8.0000" r="0.8000" fill="${grey}" stroke="none"/>`));
  // A hovered atom's ring lies over the faint bond and is not faded with it.
  assert.ok(svg.endsWith(`</g><circle data-bond-hover="target" cx="10.0000" cy="20.0000" r="5.0000" stroke="rgba(13,148,136,${150 / 255})" fill="rgba(13,148,136,${30 / 255})" stroke-width="1"/>`));
  // A hovered bond's ring lies under it; a free preview has none.
  assert.ok(bondHoverMarkup({...preview, target: {circle: [10, 20, 4.4], z: 4}}).startsWith('<circle data-bond-hover="target"'));
  assert.ok(!bondHoverMarkup({...preview, target: null}).includes('data-bond-hover="target"'));
  // Nothing in it can be hit, picked or selected.
  assert.ok(!svg.includes('data-item') && !svg.includes('pointer-events="all"'));
  assert.equal(JSON.stringify(preview), before);
});

// The page's own Bond hover: pointer handlers, tool and style controls, the
// hover loop and render, over deferred session replies.
async function bondHoverHarness() {
  const {runInNewContext} = await import('node:vm');
  const {bondHoverMarkup} = await import('../app/chemvas/web/scene.mjs');
  const source = await webSource('app.mjs');
  const slice = (marker, close = '\n}\n') => {
    const start = source.indexOf(marker), end = source.indexOf(close, start) + close.length;
    assert.ok(start >= 0 && end > start, marker);
    return source.slice(start, end);
  };
  const code = [
    slice('function render() {'), slice('function hoverPoint() {'), slice('function cancelGesture() {'),
    slice('function setTool(next) {', '\n'), slice('function refreshHover() {'), slice('async function refreshBondHover() {'),
    slice("canvas.addEventListener('pointerdown', event => {", '\n});'), slice("canvas.addEventListener('pointermove', event => {", '\n});'),
    slice("canvas.addEventListener('pointerleave'", '\n'),
  ].join('\n');
  // The Bond page's style button handler, as buildControls attaches it.
  const styleButton = slice('element.onclick = () => { bondStyle = spec.key;', '\n');
  const accepted = info(2), requests = [], replies = [], handlers = {}, elements = {};
  // Atom 1 (O at 50, 40) is under client point 450, 340.
  const atom = {dataset: {item: 'atom:1'}};
  const editor = {
    document: accepted.document, info: {session: 's', revision: 4, sheet: accepted.sheet, drawing: accepted.drawing},
    name: 'Work.chemvas', dirty: true, busy: false, readOnly: false, canUndo: true, canRedo: false,
    perform() { throw new Error('a hover must not edit the drawing'); },
  };
  const context = {
    editor, loading: false, tool: 'bond', bondStyle: 'single', gesture: null, preview: null, previewInfo: null, previewSerial: 0,
    pointerPosition: null, selection: new Set(), handleTarget: null, contextPage: null, paintColor: null,
    arrowStyle: 'reaction', shapeStroke: 'solid', lineStyle: 'line', shapeStyle: 'rect', bracketKind: 'ts', ringTemplate: {size: 6, style: 'benzene'},
    supportedTools: new Set(['select', 'bond']), markHover: {request: null, result: null}, templateHover: {result: null},
    bondHover: {request: null, result: null, pending: false},
    document: {title: '', querySelectorAll: () => [], querySelector: () => null,
      elementFromPoint: (x, y) => (x === 450 && y === 340 ? {closest: () => atom} : null)},
    $: id => elements[id] ??= {setAttribute() {}},
    view: {x: -400, y: -300, width: 800, height: 600}, clampView: view => view, viewScale: () => 1,
    canvas: {clientWidth: 800, clientHeight: 600, dataset: {}, setAttribute() {}, getScreenCTM: () => null, contains: () => true,
      focus() {}, setPointerCapture() {}, hasPointerCapture: () => false, addEventListener: (type, handler) => { handlers[type] = handler; }},
    ui: {title: {unsaved_marker: '*', suffix: 'Chemvas'}, tool_names: {}, context_pages: {}, hints: {}, templates: [{size: 6, style: 'benzene'}],
      navigation: {zoom_modifier: 'control'}, drag_distance: 10, off_sheet_guidance: 'outside'},
    grid: {enabled: false, opacity: 0.5}, gridMode: () => 'off', gridMarkup: () => '', valenceChecking: true,
    outlineRequest: null, outlineResult: {key: null, components: [], frame: null, groups: []}, selectedItems: () => [],
    sceneMarkup: () => '', valenceFeedback: () => '', selectionFrameMarkup: () => ({outline: '', handle: ''}), scenePreview: () => null,
    imageUrl: () => null, positionNoteEditor() {}, refreshTextFormatState() {}, groupBoxesMarkup: () => '', refreshSelectionOutline() {},
    currentSmilesInsert: () => true, refreshMarkHover() {}, refreshTemplateHover() {}, moveSmilesPreview() {}, refreshGesturePreview() {},
    finishNoteEdit() {}, notice() {}, pointInSheet, bondHoverMarkup, hitsAt: () => [],
    point: event => ({x: event.clientX - 400, y: event.clientY - 300}),
    api: (path, body) => { requests.push(JSON.parse(JSON.stringify([path, body]))); return new Promise(resolve => replies.push(resolve)); },
  };
  runInNewContext(code, context);
  const flush = () => new Promise(resolve => setImmediate(resolve));
  return {
    context, handlers, flush,
    requests: () => requests.map(([path, body]) => (assert.equal(path, 'session'), body)),
    overlay: () => elements['bond-hover']?.innerHTML ?? '',
    move: (clientX, clientY) => handlers.pointermove({clientX, clientY}),
    reply: async (index, preview) => { replies[index]({preview, revision: 4}); await flush(); },
    chooseStyle: key => { context.element = {}; context.spec = {key}; runInNewContext(styleButton, context); context.element.onclick(); },
  };
}
const faintBond = (x, target = null) => ({primitives: [{line: [x, 20, x + 20, 20]}], width: 1.5, color: [120, 120, 120, 140],
  opacity: 0.55, z: 4.5, target, pen: [13, 148, 136, 150], brush: [13, 148, 136, 30]});

test('Bond hover follows the pointer with one coalesced request and shows only the newest reply, changing nothing', async () => {
  const h = await bondHoverHarness();
  const accepted = JSON.stringify(h.context.editor);
  h.move(410, 320);
  assert.deepEqual(h.requests(), [{session: 's', revision: 4, action: 'bond_preview', x: 10, y: 20, atom_id: null, hits: [], scale: 1, style: 'single'}]);
  assert.equal(h.overlay(), '');
  h.move(420, 330); h.move(430, 340);
  assert.equal(h.requests().length, 1, 'moves wait behind the request in flight');
  // The older position's reply is not shown; only the newest position is asked again.
  await h.reply(0, faintBond(10));
  assert.equal(h.overlay(), '');
  assert.deepEqual(h.requests().map(request => [request.x, request.y]), [[10, 20], [30, 40]]);
  await h.reply(1, faintBond(30));
  assert.ok(h.overlay().startsWith('<g data-bond-hover="preview" opacity="0.5500"'), h.overlay());
  assert.ok(h.overlay().includes('<line x1="30.0000" y1="20.0000" x2="50.0000" y2="20.0000" />'));
  // A hover only asks: no edit, and the accepted drawing, revision and history are untouched.
  assert.ok(h.requests().every(request => request.action === 'bond_preview'));
  assert.equal(JSON.stringify(h.context.editor), accepted);
});

test('Bond hover asks for the hovered atom and follows the chosen Bond style at once', async () => {
  const h = await bondHoverHarness();
  h.move(450, 340);
  assert.deepEqual(h.requests()[0], {session: 's', revision: 4, action: 'bond_preview', x: 50, y: 40, atom_id: 1, hits: [], scale: 1, style: 'single'});
  await h.reply(0, faintBond(50, {circle: [50, 40, 5], z: 5}));
  assert.ok(h.overlay().includes('<circle data-bond-hover="target" cx="50.0000" cy="40.0000" r="5.0000"'));
  // Another style hides the old style's preview at once and asks for its own.
  h.chooseStyle('wedge');
  assert.equal(h.context.bondStyle, 'wedge');
  assert.equal(h.overlay(), '');
  assert.deepEqual(h.requests().map(request => [request.style, request.atom_id]), [['single', 1], ['wedge', 1]]);
  await h.reply(1, {...faintBond(50), primitives: [{polygon: [[50, 40], [70, 39], [70, 41]], outlined: true}]});
  assert.ok(h.overlay().includes('<polygon points="50.0000,40.0000 70.0000,39.0000 70.0000,41.0000"'));
});

test('Bond hover is withdrawn, and a late reply never returns, after leave, press, tool change, edits, busy, read-only or off-sheet', async () => {
  // label, change while a newer request is in flight, whether the change asks again
  const rows = [
    ['pointer leave', h => h.handlers.pointerleave({})],
    ['press', h => {
      h.handlers.pointerdown({button: 0, ctrlKey: false, shiftKey: false, clientX: 425, clientY: 320, pointerId: 1, target: {closest: () => null}});
      assert.equal(h.context.gesture?.kind, 'bond', 'the press still starts a bond');
    }],
    ['tool change', h => h.context.setTool('select')],
    ['accepted edit', h => { h.context.editor.info = {...h.context.editor.info, revision: 5}; h.context.render(); }],
    ['document replaced', h => { h.context.editor.info = {...h.context.editor.info, session: 't'}; h.context.render(); }],
    ['busy', h => { h.context.editor.busy = true; h.move(425, 320); }],
    ['read-only', h => { h.context.editor.readOnly = true; h.move(425, 320); }],
    ['outside the sheet', h => h.move(400 + 2000, 320)],
  ];
  for (const [label, change] of rows) {
    const h = await bondHoverHarness();
    h.move(410, 320); await h.reply(0, faintBond(10));
    assert.ok(h.overlay().includes('data-bond-hover="preview"'), label);
    h.move(420, 320);
    assert.equal(h.requests().length, 2, label);
    change(h);
    assert.equal(h.overlay(), '', label);
    await h.reply(1, faintBond(20));
    assert.equal(h.overlay(), '', `${label}: a late reply`);
    assert.equal(h.requests().length, 2, `${label}: nothing is asked for meanwhile`);
  }
});

// Save copy's own handler, with its one-save guard when that is declared just
// before it, over the real note editor in one context. The DOM is the mock one
// above, not a browser's, and edit is a stand-in that never marks the editor
// busy: real-DOM acceptance of Save copy is a separate check. A note save keeps
// its text as the session's and advances the revision unless a test answers it
// otherwise; an export answers at once with the session's note text, or is held
// until the test settles it.
const SAVE_COPY_NOTICE = 'Save copy requested. Check your downloads before closing; the original file has not changed.';
function acceptNoteSave(h, request) { h.stored = request.html; h.context.editor.info.revision += 1; return true; }
async function noteSaveCopyHarness({save = acceptNoteSave, hold = false} = {}) {
  const h = await noteEditorHarness();
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const at = source.indexOf("$('save').onclick"), guard = source.lastIndexOf('let savingCopy', at);
  const start = guard >= 0 && !source.slice(guard, at).includes('};') ? guard : at;
  const end = source.indexOf('\n};', at) + 3;
  assert.ok(at >= 0 && end > at);
  const elements = {save: {}}, notices = [], exports = [], downloads = [], pending = [];
  h.stored = h.context.editor.info.drawing.notes[0].html;
  Object.assign(h.context, {
    $: id => elements[id], download: (...args) => downloads.push(args),
    notice: (...args) => notices.push(args),
    edit: async request => { h.edits.push(request); return save(h, request); },
    api: (_path, body) => {
      if (body?.action !== 'export') return new Promise((resolve, reject) => h.replies.push({body, resolve, reject}));
      exports.push({...body});
      const reply = {document: {notes: [h.stored]}};
      return hold ? new Promise((resolve, reject) => pending.push({resolve: () => resolve(reply), reject})) : Promise.resolve(reply);
    },
  });
  h.context.editor.name = 'Work.chemvas';
  runInNewContext(source.slice(start, end), h.context);
  return Object.assign(h, {notices, exports, downloads, pending,
    click: () => elements.save.onclick(),
    saveCopy: async () => { await elements.save.onclick(); await h.settle(); },
    revisions: () => exports.map(body => body.revision),
    // Each downloaded copy's note text, without its markup.
    texts: () => downloads.map(([text]) => JSON.parse(text).notes[0].replace(/<[^>]*>/g, ''))});
}

test('Save copy commits an open note first and saves that draft at the committed revision', async () => {
  const h = await noteSaveCopyHarness();
  await h.open(7); await h.caret(2); await h.type('X');
  await h.saveCopy();
  assert.deepEqual(h.edits.map(({kind, id}) => [kind, id]), [['note_text', 7]]);
  assert.deepEqual(h.exports, [{session: 's', revision: 4, action: 'export'}]);
  assert.deepEqual([h.texts(), h.downloads.map(([, name, type]) => [name, type]), h.notices, h.context.noteEditor],
    [['ABX'], [['Work-web-copy.chemvas', 'application/json']], [[SAVE_COPY_NOTICE]], null]);
});

test('a note that was not saved stops Save copy, reopening where safe, without blocking a later copy', async () => {
  // label, save answer, change before saving, reopened, then [saves, export revisions, copies] after the first and second Save copy
  const rows = [
    ['rejected', () => false, null, true, [1, [], []], [2, [], []]],
    ['refused as busy', () => undefined, null, true, [1, [], []], [2, [], []]],
    ['applied but its reply lost', (h, request) => { acceptNoteSave(h, request); return false; }, null, false, [1, [], []], [1, [4], ['ABX']]],
    ['drawing changed while open', () => true, h => { h.context.editor.info.revision += 1; }, false, [0, [], []], [0, [4], ['AB']]],
  ];
  for (const [label, save, before, reopened, first, second] of rows) {
    const h = await noteSaveCopyHarness({save});
    await h.open(7); await h.caret(2); await h.type('X');
    before?.(h);
    await h.saveCopy();
    assert.deepEqual([label, h.edits.length, h.revisions(), h.texts(), Boolean(h.context.noteEditor)], [label, ...first, reopened]);
    if (reopened) assert.deepEqual(h.chars(), ['A', 'B', 'X']);
    assert.ok(!h.notices.some(([text]) => text === SAVE_COPY_NOTICE), label);
    await h.saveCopy();
    assert.deepEqual([label, h.edits.length, h.revisions(), h.texts()], [label, ...second]);
  }
});

test('Save copy shares a pending focusout commit and exports only once it lands', async () => {
  for (const saved of [true, false]) {
    let land;
    const h = await noteSaveCopyHarness({save: (harness, request) => new Promise(resolve => {
      land = () => { if (saved) acceptNoteSave(harness, request); resolve(saved); };
    })});
    await h.open(7); await h.caret(2); await h.type('X');
    h.element.handlers.focusout({relatedTarget: null});
    const saving = h.click(); await h.settle();
    const early = h.revisions();
    land(); await saving; await h.settle();
    assert.deepEqual([saved, early, h.edits.length, h.revisions(), h.texts(), Boolean(h.context.noteEditor)],
      [saved, [], 1, saved ? [4] : [], saved ? ['ABX'] : [], !saved]);
    if (!saved) assert.deepEqual(h.chars(), ['A', 'B', 'X']);
  }
});

test('Save copy does nothing while busy or loading, and stops when either starts during its note commit', async () => {
  const h = await noteSaveCopyHarness();
  await h.open(7); await h.caret(2); await h.type('X');
  h.context.editor.busy = true; await h.saveCopy();
  h.context.editor.busy = false; h.context.loading = true; await h.saveCopy();
  assert.deepEqual([h.edits.length, h.exports, h.downloads, h.chars()], [0, [], [], ['A', 'B', 'X']]);
  for (const key of ['busy', 'loading']) {
    let land;
    const g = await noteSaveCopyHarness({save: (harness, request) => new Promise(resolve => {
      land = () => { acceptNoteSave(harness, request); resolve(true); };
    })});
    const owner = key === 'busy' ? g.context.editor : g.context;
    await g.open(7); await g.caret(2); await g.type('X');
    const saving = g.click(); await g.settle();
    owner[key] = true; land?.(); await saving; await g.settle();
    assert.deepEqual([key, g.edits.length, g.exports, g.downloads], [key, 1, [], []]);
    owner[key] = false; await g.saveCopy();
    assert.deepEqual([key, g.revisions(), g.texts()], [key, [4], ['ABX']]);
  }
});

test('Save copy runs one save at a time', async () => {
  const h = await noteSaveCopyHarness({hold: true});
  const first = h.click(); await h.settle();
  const second = h.click(); await h.settle();
  const during = h.exports.length;
  h.pending.forEach(reply => reply.resolve()); await Promise.all([first, second]); await h.settle();
  const third = h.click(); await h.settle();
  h.pending.forEach(reply => reply.resolve()); await third;
  assert.deepEqual([during, h.revisions(), h.downloads.length], [1, [3, 3], 2]);
});

test('Save copy drops a late reply or refusal once the document changes, is renamed or turns busy', async () => {
  const changes = [
    ['nothing', () => {}],
    ['another session', c => { c.editor.info.session = 't'; }],
    ['a new revision', c => { c.editor.info.revision += 1; }],
    ['a rename', c => { c.editor.name = 'Other.chemvas'; }],
    ['a load', c => { c.loading = true; }],
    ['busy', c => { c.editor.busy = true; }],
  ];
  for (const [label, change] of changes) {
    for (const settle of ['resolve', 'reject']) {
      const h = await noteSaveCopyHarness({hold: true});
      const saving = h.click(); await h.settle();
      change(h.context);
      if (settle === 'resolve') h.pending.forEach(reply => reply.resolve());
      else h.pending.forEach(reply => reply.reject(new Error('The export failed.')));
      await saving;
      const current = label === 'nothing';
      assert.deepEqual([label, settle, h.exports.length, h.downloads.length, h.notices],
        [label, settle, 1, current && settle === 'resolve' ? 1 : 0,
          !current ? [] : settle === 'resolve' ? [[SAVE_COPY_NOTICE]] : [['The export failed.', true]]]);
    }
  }
});


// The statement that starts at `start`, ending where its brackets have closed.
function statementAt(source, start) {
  let depth = 0, opened = false;
  for (let i = start; i < source.length; i++) {
    const c = source[i];
    if (c === '/' && source[i + 1] === '/') { const next = source.indexOf('\n', i); if (next < 0) break; i = next - 1; }
    else if (c === "'" || c === '"' || c === '`') { for (i++; i < source.length && source[i] !== c; i++) if (source[i] === '\\') i++; }
    else if ('([{'.includes(c)) { depth++; opened = true; }
    else if (')]}'.includes(c)) depth--;
    else if (!depth && opened && (c === ';' || c === '\n')) return source.slice(start, i + 1);
  }
  return source.slice(start);
}

// The real New and Open handlers, mayReplace with the note check that is to
// precede it, and the page's own beforeunload callback, over the real note
// editor. The DOM is the mock one above, not a browser's: loadDocument is a spy
// that closes the editor as a load does, the file chooser a counter, and the
// beforeunload event an object recording preventDefault and returnValue. Every
// note save is refused, so an editor that loses focus reopens with its text.
async function noteReplaceHarness() {
  const h = await noteEditorHarness();
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const replace = source.indexOf('function mayReplace() {'), check = source.indexOf('function pendingNoteChanges(');
  const start = check >= 0 && check < replace ? check : replace, end = source.indexOf('\n}', replace) + 2;
  const buttons = source.indexOf('let canvasCount = 0;'), open = source.indexOf("$('open').onclick", buttons);
  const unloadAt = /^(?!\s*\/\/).*?(?:['"]beforeunload['"]|onbeforeunload\s*=)/m.exec(source)?.index ?? -1;
  assert.ok(replace >= 0 && end > replace && buttons >= 0 && open > buttons && unloadAt >= 0);
  const elements = {new: {}, open: {}, file: {click: () => { files += 1; }}}, confirms = [], requests = [], loads = [], listeners = {};
  let answer = false, files = 0;
  const listen = (kind, handler) => { listeners[kind] = handler; };
  Object.assign(h.context, {
    $: id => elements[id], window: {addEventListener: listen}, addEventListener: listen,
    confirm: message => { confirms.push(message); return answer; },
    loadDocument: (_info, name) => { loads.push(name); h.context.closeNoteEditor(); },
    edit: async request => { h.edits.push(request); return false; },
    api: (path, body) => {
      if (path !== 'new') return new Promise((resolve, reject) => h.replies.push({body, resolve, reject}));
      requests.push(path);
      return Promise.resolve({document: {state: {settings: {}}}});
    },
  });
  h.context.ui = {...h.context.ui, canvas_name: 'Canvas {}', new_canvas_settings: []};
  h.context.editor.dirty = false;
  runInNewContext(source.slice(start, end), h.context);
  runInNewContext(source.slice(buttons, source.indexOf('\n', open) + 1), h.context);
  runInNewContext(statementAt(source, unloadAt), h.context);
  const unload = listeners.beforeunload ?? h.context.window.onbeforeunload ?? h.context.onbeforeunload;
  assert.equal(typeof unload, 'function');
  return Object.assign(h, {confirms, requests, loads,
    files: () => files, answer: value => { answer = value; }, click: id => elements[id].onclick(),
    // Whether leaving would warn: a prevented default, a returnValue set, or a
    // legacy returned message.
    warns: () => {
      const event = {type: 'beforeunload', defaultPrevented: false, assigned: false, value: '',
        preventDefault() { this.defaultPrevented = true; },
        get returnValue() { return this.value; }, set returnValue(value) { this.assigned = true; this.value = value; }};
      const returned = unload(event);
      return event.defaultPrevented || event.assigned || typeof returned === 'string';
    }});
}

// A note whose save was refused, settled and reopened unfocused holding ABX,
// while the session itself stays clean.
async function recoverNoteText(h) {
  await h.open(7); await h.caret(2); await h.type('X');
  h.element.handlers.focusout({relatedTarget: null});
  await h.context.noteCommit; await h.settle();
  assert.deepEqual([Boolean(h.context.noteEditor), h.edits.length, h.context.editor.dirty, h.chars()], [true, 1, false, ['A', 'B', 'X']]);
}

// How the note editor is left, and whether committing it would save its text:
// a changed or emptied existing note would be saved or deleted; an untouched
// note, a new note without text, a caret format alone or an undone change not.
const noteLeftRows = [
  ['changed text', async h => { await h.open(7); await h.caret(2); await h.type('X'); }, true],
  ['text recovered from a refused save', recoverNoteText, true],
  ['an emptied existing note', async h => {
    await h.open(7); await h.caret(2);
    h.input('deleteContentBackward', '', 1); await h.settle();
    h.input('deleteContentBackward', '', 1); await h.settle();
    assert.deepEqual(h.chars(), []);
  }, true],
  ['text typed with a pending format', async h => { await h.open(7); await h.caret(2); await h.press({key: 'bold'}); await h.type('X'); }, true],
  ['a format applied to selected text', async h => { await h.open(7); await h.press({key: 'bold'}); }, true],
  ['an untouched existing note', async h => { await h.open(7); }, false],
  ['an empty new note', async h => { await h.open(null, 5, 5); }, false],
  ['a new note holding only whitespace', async h => { await h.open(null, 5, 5); await h.type('  '); }, false],
  ['a caret format on an existing note', async h => { await h.open(7); await h.caret(2); await h.press({key: 'bold'}); }, false],
  ['a caret format on an empty new note', async h => { await h.open(null, 5, 5); await h.press({key: 'bold'}); }, false],
  ['text changed then undone', async h => {
    await h.open(7); await h.caret(2); await h.type('X');
    h.history('historyUndo'); await h.settle();
    assert.deepEqual(h.chars(), ['A', 'B']);
  }, false],
];

test('leaving the page warns for note text a commit would save, as for a dirty or busy document', async () => {
  const rows = [...noteLeftRows,
    ['a dirty document', async h => { h.context.editor.dirty = true; }, true],
    ['a busy document', async h => { h.context.editor.busy = true; }, true],
    ['a busy document with an untouched note', async h => { await h.open(7); h.context.editor.busy = true; }, true],
    ['a clean document', async () => {}, false]];
  for (const [label, leave, warns] of rows) {
    const h = await noteReplaceHarness();
    await leave(h);
    const before = [Boolean(h.context.noteEditor), h.chars(), h.edits.length, h.replies.length];
    assert.deepEqual([label, h.warns()], [label, warns]);
    // The check neither commits, requests nor closes anything.
    assert.deepEqual([label, Boolean(h.context.noteEditor), h.chars(), h.edits.length, h.replies.length], [label, ...before]);
  }
});

test('New and Open ask once before discarding note text a commit would save, and are refused while busy or loading', async () => {
  // label, how it is left, whether replacing asks, whether replacing is allowed at all
  const rows = [
    ...noteLeftRows.map(([label, leave, unsaved]) => [label, leave, unsaved, true]),
    ['a dirty document', async h => { h.context.editor.dirty = true; }, true, true],
    ['a clean document', async () => {}, false, true],
    ['a busy document', async h => { h.context.editor.busy = true; }, false, false],
    ['a loading document', async h => { h.context.loading = true; }, false, false],
    ['a busy document holding recovered text', async h => { await recoverNoteText(h); h.context.editor.busy = true; }, false, false],
    ['a loading document holding changed text', async h => { await h.open(7); await h.caret(2); await h.type('X'); h.context.loading = true; }, false, false],
  ];
  for (const [label, leave, asks, allowed] of rows) {
    for (const button of ['new', 'open']) {
      for (const answer of [false, true]) {
        const h = await noteReplaceHarness();
        await leave(h);
        const open = Boolean(h.context.noteEditor), chars = h.chars(), edits = h.edits.length;
        h.answer(answer); h.click(button); await h.settle();
        const replaced = allowed && (!asks || answer), row = [label, button, answer];
        assert.deepEqual([...row, h.confirms.length, h.edits.length, h.requests, h.loads, h.files()],
          [...row, allowed && asks ? 1 : 0, edits, replaced && button === 'new' ? ['new'] : [], replaced && button === 'new' ? ['Canvas 1'] : [], replaced && button === 'open' ? 1 : 0]);
        if (!replaced) assert.deepEqual([...row, Boolean(h.context.noteEditor), h.chars()], [...row, open, chars]);
      }
    }
  }
});

// File > Export Figure's own handler, with the comments and one-export guard
// declared just before it, over a held note commit and session reply; with
// `mol`, Export MOL's own handler joins it in the same page. The download helper
// and edit are stand-ins, so nothing reaches the file system, and an export
// must never edit. The reply is shaped like the server's: the SVG text the
// desktop's figure export wrote, with the revision it was read at.
const FIGURE_SVG = [
  '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
  '<svg width="10.5833mm" height="11.9944mm"',
  ' viewBox="0 0 30 34"',
  ' xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"  version="1.2" baseProfile="tiny">',
  '<defs>',
  '</defs>',
  '<g fill="none" stroke="#000000" stroke-opacity="1" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" transform="matrix(1,0,0,1,0,0)"',
  'font-family="Sans Serif" font-size="9" font-weight="400" font-style="normal" >',
  '<polyline fill="none" vector-effect="none" points="5,29 25,5 " />',
  '</g>',
  '</svg>',
  ''].join('\n');
const figureRequest = revision => ['session', {session: 's', revision, action: 'export_figure', format: 'svg', scope: 'sheet'}];
async function exportFigureHandler({mol = false} = {}) {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const at = source.indexOf("$('export-figure').onclick");
  assert.ok(at >= 0, 'File > Export Figure has no click handler');
  let start = at;
  for (let end = at - 1; end > 0;) {
    const begin = source.lastIndexOf('\n', end - 1) + 1;
    if (!/^(let |\/\/)/.test(source.slice(begin, end))) break;
    start = begin; end = begin - 1;
  }
  const elements = {'export-figure': {}, 'export-mol': {}}, requests = [], downloads = [], notices = [], replies = [], commits = [], edits = [];
  const context = {
    $: id => elements[id], loading: false,
    editor: {document: {}, busy: false, info: {session: 's', revision: 4}, name: 'Work.chemvas'},
    selectedItems: () => [{target: 'bond', id: 0}],
    finishNoteEdit: () => new Promise(resolve => commits.push(resolve)),
    api: (path, body) => new Promise((resolve, reject) => { requests.push(JSON.parse(JSON.stringify([path, body]))); replies.push({resolve, reject}); }),
    download: (...args) => downloads.push(args), noticeSerial: 0,
    notice: (...args) => { notices.push(args); context.noticeSerial++; },
    edit: (...args) => { edits.push(args); return Promise.resolve(true); },
  };
  runInNewContext(source.slice(start, source.indexOf('\n};', at) + 3), context);
  if (mol) {
    const from = source.indexOf('let exportingMol = false');
    const to = source.indexOf('\n};', source.indexOf("$('export-mol').onclick", from)) + 3;
    assert.ok(from >= 0 && to > from);
    runInNewContext(source.slice(from, to), context);
  }
  return {context, requests, downloads, notices, replies, commits, edits,
    flush: () => new Promise(resolve => setImmediate(resolve)),
    click: () => elements['export-figure'].onclick(),
    clickMol: () => elements['export-mol'].onclick()};
}
// One Export Figure over a saved note, refused, answered, or refused only after
// its document was renamed.
async function refuseFigure(h, message = 'There is nothing to export.') {
  const pending = h.click(); h.commits.at(-1)(true); await h.flush();
  h.replies.at(-1).reject(new Error(message)); await pending;
}
async function exportFigureOnce(h) {
  const pending = h.click(); h.commits.at(-1)(true); await h.flush();
  h.replies.at(-1).resolve({svg: FIGURE_SVG, revision: h.context.editor.info.revision}); await pending;
}
async function dropFigureRefusal(h) {
  const pending = h.click(); h.commits.at(-1)(true); await h.flush();
  h.context.editor.name = 'Other.chemvas';
  h.replies.at(-1).reject(new Error('There is nothing to export.')); await pending;
}

test('Export Figure commits an open note first, then downloads the whole-canvas SVG at the committed revision', async () => {
  const h = await exportFigureHandler();
  const pending = h.click(); await h.flush();
  assert.deepEqual([h.commits.length, h.requests], [1, []]);
  h.context.editor.info = {session: 's', revision: 5}; h.commits[0](true); await h.flush();
  assert.deepEqual(h.requests, [figureRequest(5)]);
  h.replies[0].resolve({svg: FIGURE_SVG, revision: 5}); await pending;
  assert.deepEqual([h.downloads, h.notices, h.edits], [[[FIGURE_SVG, 'Work.svg', 'image/svg+xml']], [], []]);
  assert.deepEqual(h.context.editor, {document: {}, busy: false, info: {session: 's', revision: 5}, name: 'Work.chemvas'});
});

test('Export Figure names the download after the document', async () => {
  const rows = [['Work.chemvas', 'Work.svg'], ['Plate 2.CHEMVAS', 'Plate 2.svg'], ['Canvas 1', 'Canvas 1.svg'], ['a.chemvas.chemvas', 'a.chemvas.svg']];
  for (const [name, file] of rows) {
    const h = await exportFigureHandler();
    h.context.editor.name = name;
    await exportFigureOnce(h);
    assert.deepEqual([name, h.downloads], [name, [[FIGURE_SVG, file, 'image/svg+xml']]]);
  }
});

test('Export Figure asks nothing without a document, while busy or loading', async () => {
  const rows = [['no document', c => { c.editor.document = null; }], ['busy', c => { c.editor.busy = true; }], ['loading', c => { c.loading = true; }]];
  for (const [label, change] of rows) {
    const h = await exportFigureHandler();
    change(h.context);
    await h.click(); await h.flush();
    assert.deepEqual([label, h.commits.length, h.requests, h.downloads, h.notices, h.edits], [label, 0, [], [], [], []]);
  }
});

test('Export Figure runs one export at a time', async () => {
  const h = await exportFigureHandler();
  const first = h.click(); await h.flush();
  // A second press while the note commit is held, then while the reply is held.
  // Neither press is awaited before the counts are checked, so a second export
  // left waiting on its own note commit fails here instead of hanging.
  const whileCommitting = h.click(); await h.flush();
  assert.deepEqual([h.commits.length, h.requests], [1, []]);
  h.commits[0](true); await h.flush();
  const whileReplying = h.click(); await h.flush();
  assert.deepEqual([h.commits.length, h.requests], [1, [figureRequest(4)]]);
  await Promise.all([whileCommitting, whileReplying]);
  h.replies[0].resolve({svg: FIGURE_SVG, revision: 4}); await first;
  await exportFigureOnce(h);
  assert.deepEqual([h.commits.length, h.requests.length, h.downloads.length, h.notices], [2, 2, 2, []]);
});

test('Export Figure stops when its note is not saved or the document is replaced, busy or loading by then', async () => {
  const rows = [
    ['note not saved', () => false],
    ['document replaced', c => { c.editor.document = null; return true; }],
    ['busy', c => { c.editor.busy = true; return true; }],
    ['loading', c => { c.loading = true; return true; }],
  ];
  for (const [label, during] of rows) {
    const h = await exportFigureHandler();
    const pending = h.click(); await h.flush();
    // Checked before the press is awaited, so an export that goes on to ask the
    // server fails here instead of waiting on a reply that never comes.
    h.commits[0](during(h.context)); await h.flush();
    assert.deepEqual([label, h.requests, h.downloads, h.notices, h.edits], [label, [], [], [], []]);
    await pending;
    // The stopped export leaves the next one free to run.
    h.context.loading = false; Object.assign(h.context.editor, {document: {}, busy: false});
    await exportFigureOnce(h);
    assert.deepEqual([label, h.requests, h.downloads.length], [label, [figureRequest(4)], 1]);
  }
});

test('Export Figure drops a late reply or refusal once the document changes, is renamed or turns busy', async () => {
  const changes = [
    ['another session', c => { c.editor.info = {session: 't', revision: 0}; }],
    ['a new revision', c => { c.editor.info = {session: 's', revision: 5}; }],
    ['a rename', c => { c.editor.name = 'Other.chemvas'; }],
    ['busy', c => { c.editor.busy = true; }],
    ['loading', c => { c.loading = true; }],
  ];
  for (const [label, change] of changes) {
    for (const settle of ['resolve', 'reject']) {
      const h = await exportFigureHandler();
      const pending = h.click(); h.commits[0](true); await h.flush();
      change(h.context);
      if (settle === 'resolve') h.replies[0].resolve({svg: FIGURE_SVG, revision: 4});
      else h.replies[0].reject(new Error('There is nothing to export.'));
      await pending;
      assert.deepEqual([label, settle, h.requests.length, h.downloads, h.notices, h.edits], [label, settle, 1, [], [], []]);
    }
  }
});

test('Export Figure shows the server refusal for the current document and downloads nothing', async () => {
  const messages = [
    'There is nothing to export.',
    'The figure export took too long. No file was written.',
    'The figure could not be exported. No file was written.',
  ];
  for (const message of messages) {
    const h = await exportFigureHandler();
    await refuseFigure(h, message);
    assert.deepEqual([h.requests, h.downloads, h.notices, h.edits], [[figureRequest(4)], [], [[message, true]], []]);
  }
});

test('a successful Export Figure clears only its own refusal while it is still the notice shown', async () => {
  const shownElsewhere = h => h.context.notice('Incomplete, read-only preview: images.');
  const rows = [
    ['another notice', [shownElsewhere], false],
    ['the same text from another action', [refuseFigure, h => h.context.notice('There is nothing to export.', true)], false],
    ['a notice cleared by another action', [refuseFigure, h => h.context.notice()], false],
    ['another notice, then a refusal dropped as stale', [shownElsewhere, dropFigureRefusal], false],
    ['its own refusal', [refuseFigure], true],
    ['its second refusal', [refuseFigure, refuseFigure], true],
    ['its own timeout', [h => refuseFigure(h, 'The figure export took too long. No file was written.')], true],
  ];
  for (const [label, steps, cleared] of rows) {
    const h = await exportFigureHandler();
    for (const step of steps) await step(h);
    const shown = h.notices.length;
    await exportFigureOnce(h);
    assert.deepEqual([label, h.downloads.length, h.notices.slice(shown)], [label, 1, cleared ? [[]] : []]);
    // A later download finds no refusal of its own left to clear.
    await exportFigureOnce(h);
    assert.deepEqual([label, h.downloads.length, h.notices.slice(shown)], [label, 2, cleared ? [[]] : []]);
  }
});

test('Export Figure and Export MOL in one page each clear only their own refusal', async () => {
  const h = await exportFigureHandler({mol: true});
  const mol = async (settle, value) => {
    const pending = h.clickMol(); h.commits.at(-1)(true); await h.flush();
    h.replies.at(-1)[settle](value); await pending;
  };
  await mol('reject', new Error('Select a molecular structure on the canvas first.'));
  const molRefused = h.notices.length;
  await exportFigureOnce(h);
  assert.deepEqual([h.downloads.map(([, name, type]) => [name, type]), h.notices.slice(molRefused)], [[['Work.svg', 'image/svg+xml']], []]);
  await refuseFigure(h);
  const figureRefused = h.notices.length;
  await mol('resolve', {molfile: 'MOL\n', revision: 4});
  assert.deepEqual([h.downloads.map(([, name]) => name), h.notices.slice(figureRefused)], [['Work.svg', 'Work.mol'], []]);
  assert.deepEqual([h.requests.map(([, body]) => body.action), h.edits], [['export_mol', 'export_figure', 'export_figure', 'export_mol'], []]);
});

// The page's own held move: pointer move and release, Shift+Arrow nudge,
// keyboard zoom, preview loop and edit, over held preview replies and a session
// whose edits land only when the test lands them. Scene x/y follow the view as
// the canvas CTM does, so a zoom moves the pointer's scene position.
async function heldMoveHarness() {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const slice = (marker, close = '\n}\n', from = 0) => {
    const start = source.indexOf(marker, from), end = source.indexOf(close, start) + close.length;
    assert.ok(start >= 0 && end > start, marker);
    return source.slice(start, end);
  };
  // The canvas keydown handler, not the one-line menu Escape handler before it.
  const keys = source.lastIndexOf("document.addEventListener('keydown'", source.indexOf("if (event.isComposing || document.querySelector('dialog[open]')) return;"));
  const code = [
    slice('const viewScale = ', '\n'), slice('function zoom(factor) {'), slice('function cancelGesture() {'),
    slice('async function edit(change) {'), slice('async function refreshGesturePreview() {'),
    slice('function moveRequest(active, end) {'), slice('function selectionGestureMoved(active, end) {'),
    slice('function finishSelection(active, end) {'),
    slice("canvas.addEventListener('pointermove', event => {", '\n});'), slice("canvas.addEventListener('pointerup', event => {", '\n});'),
    slice("document.addEventListener('keydown', event => {", '\n});', keys), 'liveScale = viewScale;',
  ].join('\n');
  const requests = [], replies = [], performed = [], landings = [], handlers = {}, listeners = {};
  const editor = {
    info: {session: 's', revision: 3}, document: {}, busy: false, readOnly: false,
    perform(change) {
      performed.push(JSON.parse(JSON.stringify(change)));
      editor.busy = true;
      let landed = false;
      return new Promise(resolve => landings.push(() => {
        if (landed) return;
        landed = true;
        editor.busy = false;
        editor.info = {...editor.info, revision: editor.info.revision + 1};
        resolve();
      }));
    },
  };
  const context = {
    gesture: null, preview: null, previewSerial: 0, previewPending: null, previewInfo: null, pointerPosition: null,
    handleTarget: null, loading: false, markHover: {}, selection: new Set(['arrow:0']), chargeEdits: null,
    view: {x: -400, y: -300, width: 800, height: 600},
    ui: {drag_distance: 10, navigation: {min: .2, max: 5, step: 1.25, zoom_keys: {}, function_keys: {}, nudge_keys: {Right: [1, 0]}, rotate_keys: {}, zoom_modifier: 'control'}},
    canvas: {clientWidth: 800, clientHeight: 600, hasPointerCapture: () => false, addEventListener: (type, handler) => { handlers[type] = handler; }},
    document: {addEventListener: (type, handler) => { listeners[type] = handler; }, querySelector: () => null},
    noteEditorElement: {contains: () => false}, editor, zoomView, selectedItems: () => [{target: 'arrow', id: 0}],
    point: event => ({x: context.view.x + event.clientX * context.view.width / 800, y: context.view.y + event.clientY * context.view.height / 600}),
    render() {}, refreshHover() {}, notice() {},
    sessionRequest: body => { requests.push(JSON.parse(JSON.stringify(body))); return new Promise(resolve => replies.push(resolve)); },
  };
  runInNewContext(code, context);
  const flush = () => new Promise(resolve => setImmediate(resolve));
  return {
    context, requests, performed, flush,
    // A press on the selected arrow at the view's centre, already a move.
    start: () => {
      context.gesture = {kind: 'move', start: context.point({clientX: 400, clientY: 300}), pointer: 1, scale: 1, hasArrows: true, dragged: false,
        toggleHandle: null, released: false, selection: [{target: 'arrow', id: 0}], session: 's', revision: 3};
    },
    move: (clientX, clientY) => handlers.pointermove({clientX, clientY}),
    release: (clientX, clientY) => handlers.pointerup({clientX, clientY, shiftKey: false}),
    nudge: () => listeners.keydown({key: 'ArrowRight', shiftKey: true, altKey: false, ctrlKey: false, metaKey: false, isComposing: false,
      target: {matches: () => false, closest: () => null}, preventDefault() {}}),
    reply: async (index, value) => { replies[index](value); await flush(); },
    land: async index => { landings[index](); await flush(); },
  };
}

test('a held move preview follows a keyboard zoom: a reply asked before it is not shown, and the preview and release use the new scale', async () => {
  for (const delivered of [false, true]) {
    const label = delivered ? 'preview shown before the zoom' : 'preview in flight across the zoom';
    const h = await heldMoveHarness();
    h.start();
    h.move(500, 340); await h.flush();
    assert.deepEqual([label, h.requests.length, h.requests[0].edit.scale], [label, 1, 1]);
    const asked = {session: 's', revision: 3, drawing: {}};
    if (delivered) { await h.reply(0, asked); assert.equal(h.context.previewInfo, asked, label); }
    h.context.zoom(1 / h.context.ui.navigation.step);
    const scale = h.context.liveScale();
    assert.ok(Math.abs(scale - 1.25) < 1e-12, label);
    if (!delivered) await h.reply(0, asked);
    await h.flush();
    if (!delivered) assert.notEqual(h.context.previewInfo, asked, label);
    // One fresh preview, at the zoom now shown and where the held pointer now is.
    const here = h.context.point({clientX: 500, clientY: 340}), from = h.context.gesture.start;
    assert.deepEqual([label, h.requests.length, h.requests[1]?.edit],
      [label, 2, {kind: 'move', selection: [{target: 'arrow', id: 0}], dx: here.x - from.x, dy: here.y - from.y, scale}]);
    const fresh = {session: 's', revision: 3, drawing: {}};
    await h.reply(1, fresh);
    assert.equal(h.context.previewInfo, fresh, label);
    // Releasing there commits exactly what the preview showed, once.
    h.release(500, 340); await h.flush();
    assert.deepEqual([label, h.performed], [label, [h.requests[1].edit]]);
  }
});

test('a held move whose document changed while held commits nothing at release; an unchanged one commits once', async () => {
  // label, change while the button is held, committed edits after release
  const rows = [
    ['unchanged', async () => {}, ['move']],
    ['a Shift+Arrow nudge completed', async h => { h.nudge(); await h.land(0); }, ['nudge']],
    ['a Shift+Arrow nudge still waiting', async h => { h.nudge(); await h.flush(); }, ['nudge']],
    ['the document replaced', async h => { h.context.editor.info = {session: 't', revision: 0}; }, []],
  ];
  for (const [label, change, committed] of rows) {
    const h = await heldMoveHarness();
    h.start();
    h.move(500, 340); await h.reply(0, {session: 's', revision: 3, drawing: {}});
    await change(h);
    h.release(500, 340); await h.flush();
    // Land whatever is still waiting; a dropped gesture never adds an edit later.
    for (let index = 0; index < h.performed.length; index++) await h.land(index);
    assert.deepEqual([label, h.performed.map(edit => (edit.scale === undefined ? 'nudge' : 'move')), h.context.gesture],
      [label, committed, null]);
    if (label === 'unchanged') {
      assert.deepEqual(h.performed[0], {kind: 'move', selection: [{target: 'arrow', id: 0}], dx: 100, dy: 40, scale: 1});
    }
  }
});

// The page's own held move with its view keys: the keydown handler, the zoom
// buttons' handlers, Fit to Window and Actual Size, over held preview replies.
// The view starts at 200 % so each key changes the scale.
async function heldMoveViewKeyHarness() {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const slice = (marker, close = '\n}\n', from = 0) => {
    const start = source.indexOf(marker, from), end = source.indexOf(close, start) + close.length;
    assert.ok(start >= 0 && end > start, marker);
    return source.slice(start, end);
  };
  const buttons = source.indexOf("$('zoom-in').onclick"), buttonsEnd = source.indexOf("$('save-as').onclick", buttons);
  assert.ok(buttons >= 0 && buttonsEnd > buttons);
  const keys = source.lastIndexOf("document.addEventListener('keydown'", source.indexOf("if (event.isComposing || document.querySelector('dialog[open]')) return;"));
  const code = [
    slice('const viewScale = ', '\n'), slice('function fitPage() {'), slice('function zoom(factor) {'), slice('function actualSize() {'),
    slice('function cancelGesture() {'), slice('async function edit(change) {'), slice('async function refreshGesturePreview() {'),
    slice('function moveRequest(active, end) {'), slice('function selectionGestureMoved(active, end) {'),
    slice('function finishSelection(active, end) {'),
    slice("canvas.addEventListener('pointermove', event => {", '\n});'), slice("canvas.addEventListener('pointerup', event => {", '\n});'),
    source.slice(buttons, buttonsEnd),
    slice("document.addEventListener('keydown', event => {", '\n});', keys), 'liveScale = viewScale;',
  ].join('\n');
  const requests = [], replies = [], performed = [], handlers = {}, listeners = {}, elements = {};
  const editor = {
    info: {session: 's', revision: 3, sheet: [842, 595]}, document: {}, busy: false, readOnly: false,
    perform(change) { performed.push(JSON.parse(JSON.stringify(change))); return Promise.resolve(); },
  };
  const context = {
    gesture: null, preview: null, previewSerial: 0, previewPending: null, previewInfo: null, pointerPosition: null,
    handleTarget: null, loading: false, markHover: {}, selection: new Set(['arrow:0']), chargeEdits: null,
    view: {x: -200, y: -150, width: 400, height: 300},
    ui: {drag_distance: 10, navigation: {min: .2, max: 5, step: 1.25, fit_margin: .9, zoom_keys: {'0': 'actual_size'},
      function_keys: {F5: 'actual_size', F6: 'fit'}, nudge_keys: {}, rotate_keys: {}, zoom_modifier: 'control'}},
    $: id => elements[id] ??= {click() { return this.onclick?.(); }},
    canvas: {clientWidth: 800, clientHeight: 600, hasPointerCapture: () => false, addEventListener: (type, handler) => { handlers[type] = handler; }},
    document: {addEventListener: (type, handler) => { listeners[type] = handler; }, querySelector: () => null},
    noteEditorElement: {contains: () => false}, editor, zoomView, selectedItems: () => [{target: 'arrow', id: 0}],
    point: event => ({x: context.view.x + event.clientX * context.view.width / 800, y: context.view.y + event.clientY * context.view.height / 600}),
    render() {}, refreshHover() {}, notice() {},
    sessionRequest: body => { requests.push(JSON.parse(JSON.stringify(body))); return new Promise(resolve => replies.push(resolve)); },
  };
  runInNewContext(code, context);
  const flush = () => new Promise(resolve => setImmediate(resolve));
  return {
    context, requests, performed, flush,
    start: () => {
      context.gesture = {kind: 'move', start: context.point({clientX: 400, clientY: 300}), pointer: 1, scale: 2, hasArrows: true, dragged: false,
        toggleHandle: null, released: false, selection: [{target: 'arrow', id: 0}], session: 's', revision: 3};
    },
    move: (clientX, clientY) => handlers.pointermove({clientX, clientY}),
    release: (clientX, clientY) => handlers.pointerup({clientX, clientY, shiftKey: false}),
    key: (key, ctrlKey = false) => listeners.keydown({key, ctrlKey, shiftKey: false, altKey: false, metaKey: false, isComposing: false,
      target: {matches: () => false, closest: () => null}, preventDefault() {}}),
    reply: async (index, value) => { replies[index](value); await flush(); },
  };
}

test('a held move preview follows F5, F6 and Ctrl+0: a reply asked before the view change is not shown, and the preview and release use the new view', async () => {
  const keys = [['F5 Actual Size', 'F5', false], ['F6 Fit to Window', 'F6', false], ['Ctrl+0 Actual Size', '0', true]];
  for (const [name, key, ctrl] of keys) {
    for (const delivered of [false, true]) {
      const label = `${name}: ${delivered ? 'preview shown before the key' : 'preview in flight across the key'}`;
      const h = await heldMoveViewKeyHarness();
      h.start();
      h.move(500, 340); await h.flush();
      assert.deepEqual([label, h.requests.length, h.requests[0].edit.scale], [label, 1, 2]);
      const asked = {session: 's', revision: 3, drawing: {}};
      if (delivered) { await h.reply(0, asked); assert.equal(h.context.previewInfo, asked, label); }
      h.key(key, ctrl);
      const scale = h.context.liveScale();
      assert.ok(Math.abs(scale - 2) > 1e-6, label);
      if (!delivered) await h.reply(0, asked);
      await h.flush();
      if (!delivered) assert.notEqual(h.context.previewInfo, asked, label);
      // One fresh preview, at the view now shown and where the held pointer now is.
      const here = h.context.point({clientX: 500, clientY: 340}), from = h.context.gesture.start;
      assert.deepEqual([label, h.requests.length, h.requests[1]?.edit],
        [label, 2, {kind: 'move', selection: [{target: 'arrow', id: 0}], dx: here.x - from.x, dy: here.y - from.y, scale}]);
      const fresh = {session: 's', revision: 3, drawing: {}};
      await h.reply(1, fresh);
      assert.equal(h.context.previewInfo, fresh, label);
      // Releasing without another pointer move commits what the preview showed, once.
      h.release(500, 340); await h.flush();
      assert.deepEqual([label, h.performed], [label, [h.requests[1].edit]]);
    }
  }
});

// The chemistry clipboard. SELECTION stands for a server copy reply; the
// server validates every paste, so these tests only follow the text.
const SELECTION = JSON.stringify({format: 'chemvas-selection', version: 3, atoms: [], bonds: [], rings: [], marks: [], scene_items: []});

// A system clipboard that grants or refuses writes and reads. A refused write
// rejects before reading its item, as a browser denying permission does.
function fakeClipboard({write = true, read = null, item = true} = {}) {
  const written = [], calls = [];
  class Item { constructor(data) { this.data = data; } }
  const clipboard = {
    written, calls,
    async write([entry]) {
      calls.push('write');
      if (!write) throw new Error('Write permission denied.');
      written.push(await (await entry.data['text/plain']).text());
    },
    async writeText(text) {
      calls.push('writeText');
      if (!write) throw new Error('Write permission denied.');
      written.push(text);
    },
    async readText() {
      if (read === null) throw new Error('Read permission denied.');
      return read;
    },
  };
  return {clipboard, ClipboardItem: item ? Item : undefined};
}

test('only Chemvas selection text is taken for chemistry', () => {
  assert.equal(isSelectionText(SELECTION), true);
  assert.equal(isSelectionText(`  ${SELECTION}`), true);
  for (const text of [null, undefined, '', 'plain text', '[]', '{"format":"other"}', '{"format":"chemvas-selection"', '{"format":"chemvas-document"}']) {
    assert.equal(isSelectionText(text), false, String(text));
  }
});

test('a paste prefers system chemistry and uses the window copy only where the system clipboard lacks it', () => {
  const shared = {text: 'WINDOW', system: true}, kept = {text: 'WINDOW', system: false};
  assert.equal(pasteText(SELECTION, kept), SELECTION);
  // Newer text copied elsewhere is not chemistry: nothing pastes.
  assert.equal(pasteText('hello', shared), null);
  // The copy never reached the system clipboard, or it cannot be read.
  assert.equal(pasteText('hello', kept), 'WINDOW');
  assert.equal(pasteText(null, shared), 'WINDOW');
  assert.equal(pasteText(null, null), null);
  assert.equal(pasteText('hello', null), null);
});

test('a copy starts its system write inside the gesture and falls back without losing the reply', async () => {
  let deliver;
  const granted = fakeClipboard();
  const pending = writeSelection(new Promise(resolve => { deliver = resolve; }), granted);
  // Called before the server reply arrives, while the user gesture lasts.
  assert.deepEqual(granted.clipboard.calls, ['write']);
  deliver(SELECTION);
  assert.deepEqual(await pending, {text: SELECTION, system: true});
  assert.deepEqual(granted.clipboard.written, [SELECTION]);
  const denied = fakeClipboard({write: false});
  assert.deepEqual(await writeSelection(Promise.resolve(SELECTION), denied), {text: SELECTION, system: false});
  const textOnly = fakeClipboard({item: false});
  assert.deepEqual(await writeSelection(Promise.resolve(SELECTION), textOnly), {text: SELECTION, system: true});
  assert.deepEqual(textOnly.clipboard.calls, ['writeText']);
  assert.deepEqual(await writeSelection(Promise.resolve(SELECTION), {}), {text: SELECTION, system: false});
  // A refused reply copies nothing, whether or not the write was refused too.
  for (const env of [fakeClipboard(), fakeClipboard({write: false})]) {
    await assert.rejects(writeSelection(Promise.reject(new Error('Select a structure')), env), /Select a structure/);
    assert.deepEqual(env.clipboard.written, []);
  }
});

test('Cut removes only after a usable copy, and only from the drawing it copied', async () => {
  const removed = [];
  const store = new ChemistryClipboard(fakeClipboard({write: false}));
  const remove = label => async () => { removed.push(label); return true; };
  await assert.rejects(copySelection({store, payload: Promise.reject(new Error('Select a structure')), cut: true, isCurrent: () => true, remove: remove('refused')}), /Select a structure/);
  assert.deepEqual([removed, store.local], [[], null]);
  // A copy kept only in this window is still usable, so Cut proceeds.
  let result = await copySelection({store, payload: Promise.resolve(SELECTION), cut: true, isCurrent: () => true, remove: remove('cut')});
  assert.deepEqual([result.removed, result.stale, result.copied.system, store.local.text, removed], [true, false, false, SELECTION, ['cut']]);
  result = await copySelection({store, payload: Promise.resolve('NEWER'), cut: true, isCurrent: () => false, remove: remove('stale')});
  assert.deepEqual([result.removed, result.stale, store.local.text, removed], [false, true, 'NEWER', ['cut']]);
  result = await copySelection({store, payload: Promise.resolve(SELECTION), isCurrent: () => true, remove: remove('copy')});
  assert.deepEqual([result.removed, removed], [false, ['cut']]);
});

// The page's own Copy/Cut and Paste actions over a fake system clipboard, a
// session whose copy replies come from `reply`, and an edit stand-in that
// accepts each change at the next revision.
async function clipboardActionHarness({clipboard = {}, reply = () => ({payload: SELECTION})} = {}) {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const slice = marker => {
    const start = source.indexOf(marker), end = source.indexOf('\n}\n', start) + 2;
    assert.ok(start >= 0 && end > start, marker);
    return source.slice(start, end);
  };
  const env = fakeClipboard(clipboard), requests = [], edits = [], notices = [];
  const context = {
    editor: {document: {}, busy: false, readOnly: false, info: {session: 's', revision: 4}},
    loading: false, gesture: null, selection: new Set(['atom:0', 'bond:0']),
    selectedItems: () => [{target: 'atom', id: 0}, {target: 'bond', id: 0}],
    api: async (_path, body) => { requests.push(JSON.parse(JSON.stringify(body))); return reply(body, context); },
    edit: async change => {
      // The page's objects come from the VM realm; compare them as this realm's.
      edits.push(JSON.parse(JSON.stringify(change)));
      context.editor.info = {...context.editor.info, revision: context.editor.info.revision + 1, pasted: change.kind === 'paste' ? [{target: 'atom', id: 9}] : null};
      return true;
    },
    notice: (...args) => notices.push(args), render() {}, cancelGesture() {},
    chemistryClipboard: new ChemistryClipboard(env), copySelection, Blob, ui: {max_clipboard_bytes: 4096},
  };
  runInNewContext([slice('async function copyChemistry(cut) {'), slice('async function pasteChemistry(systemText) {'), slice('async function pasteFromMenu() {')].join('\n'), context);
  return {context, env, requests, edits, notices};
}
const SELECTED = [{target: 'atom', id: 0}, {target: 'bond', id: 0}];

test('Copy asks for the selection at its revision; Cut then deletes that selection as one edit', async () => {
  const h = await clipboardActionHarness();
  await h.context.copyChemistry(false);
  assert.deepEqual(h.requests, [{session: 's', revision: 4, action: 'copy', selection: SELECTED}]);
  assert.deepEqual([h.env.clipboard.written, h.edits, h.notices], [[SELECTION], [], []]);
  await h.context.copyChemistry(true);
  assert.deepEqual(h.edits, [{kind: 'delete_selection', selection: SELECTED}]);
  assert.equal(h.context.selection.size, 0);
  // Nothing is selected now, so neither action asks again.
  await h.context.copyChemistry(false); await h.context.copyChemistry(true);
  assert.equal(h.requests.length, 2);
});

test('a refused copy cuts nothing and leaves no window copy', async () => {
  const h = await clipboardActionHarness({reply: () => { throw new Error('Select a structure or object on the canvas to copy.'); }});
  await h.context.copyChemistry(true);
  assert.deepEqual([h.edits, h.env.clipboard.written, h.context.chemistryClipboard.local, h.context.selection.size], [[], [], null, 2]);
  assert.deepEqual(h.notices, [['Select a structure or object on the canvas to copy.', true]]);
});

test('with the system clipboard refused, Cut still works and Paste uses this window copy', async () => {
  const h = await clipboardActionHarness({clipboard: {write: false}});
  await h.context.copyChemistry(true);
  assert.deepEqual(h.edits, [{kind: 'delete_selection', selection: SELECTED}]);
  assert.match(h.notices.at(-1)[0], /this browser window only/);
  // Unrelated system text, or none readable: the window copy pastes.
  for (const systemText of ['unrelated text', null]) await h.context.pasteChemistry(systemText);
  assert.deepEqual(h.edits.slice(1), [{kind: 'paste', payload: SELECTION}, {kind: 'paste', payload: SELECTION}]);
  assert.deepEqual([...h.context.selection], ['atom:9']);
});

test('Cut of a drawing changed meanwhile copies but deletes nothing', async () => {
  const h = await clipboardActionHarness({reply: (_body, context) => { context.editor.info = {session: 's', revision: 5}; return {payload: SELECTION}; }});
  await h.context.copyChemistry(true);
  assert.deepEqual([h.edits, h.env.clipboard.written, h.context.selection.size], [[], [SELECTION], 2]);
  assert.match(h.notices.at(-1)[0], /copied but not removed/);
});

test('Paste refuses plain text, unreadable clipboards, oversized text and read-only drawings without editing', async () => {
  const h = await clipboardActionHarness();
  await h.context.pasteChemistry('hello');
  await h.context.pasteChemistry(null);
  await h.context.pasteChemistry(`{"format":"chemvas-selection"}${' '.repeat(5000)}`);
  h.context.editor.readOnly = true;
  await h.context.pasteChemistry(SELECTION);
  assert.deepEqual(h.edits, []);
  assert.deepEqual(h.notices.map(([text, error]) => [text.split(/[.:]/)[0], error]), [
    ['The clipboard does not contain a Chemvas selection', true],
    ['The browser did not allow reading the clipboard', true],
    ['The Chemvas clipboard selection is too large to paste', true],
    ['This drawing is read-only in the browser adapter', true],
  ]);
  // A copy that reached the system clipboard is not pasted over newer text.
  h.context.editor.readOnly = false;
  await h.context.copyChemistry(false);
  await h.context.pasteChemistry('newer text');
  assert.deepEqual(h.edits, []);
  await h.context.pasteChemistry(SELECTION);
  assert.deepEqual(h.edits, [{kind: 'paste', payload: SELECTION}]);
});

test('menu Paste waiting on clipboard permission pastes nothing into a drawing replaced or edited meanwhile', async () => {
  for (const change of [
    info => ({...info, revision: info.revision + 1}),
    () => ({session: 's', revision: 9}),
    () => ({session: 'other', revision: 4}),
  ]) {
    let allow;
    const h = await clipboardActionHarness({clipboard: {read: new Promise(resolve => { allow = resolve; })}});
    const pasting = h.context.pasteFromMenu();
    // Load, recovery or an edit lands while the permission prompt is open.
    h.context.editor.info = change(h.context.editor.info);
    allow(SELECTION);
    await pasting;
    assert.deepEqual(h.edits, []);
    assert.deepEqual(h.notices, [['The drawing changed while the clipboard was being read. Nothing was pasted.', true]]);
  }
  // Unchanged, the same deferred read pastes once into its drawing.
  let allow;
  const h = await clipboardActionHarness({clipboard: {read: new Promise(resolve => { allow = resolve; })}});
  const pasting = h.context.pasteFromMenu();
  allow(SELECTION);
  await pasting;
  assert.deepEqual([h.edits, h.notices, [...h.context.selection]], [[{kind: 'paste', payload: SELECTION}], [], ['atom:9']]);
});

test('the startup notice counts only drafts no open window holds and reports unreadable recovery', async () => {
  const {runInNewContext} = await import('node:vm');
  const source = await webSource('app.mjs');
  const start = source.indexOf('async function offerRecovery() {');
  const code = source.slice(start, source.indexOf('\n}\n', start) + 2);
  const run = async reply => {
    const notices = [];
    const context = {
      sessionStorage: {getItem: () => null, removeItem() {}}, closedSessionKey: 'closed',
      editor: {info: {session: 's'}}, $: () => ({hidden: true}),
      api: async () => reply(), notice: (...args) => notices.push(args),
    };
    runInNewContext(code, context);
    await context.offerRecovery();
    return notices;
  };
  const entry = (open, problem = null) => ({id: 'd', name: 'Work.chemvas', open, problem});
  // Another tab's live draft is not earlier work.
  assert.deepEqual(await run(() => ({available: true, drafts: [entry(true)]})), []);
  const notices = await run(() => ({available: true, drafts: [entry(true), entry(false), entry(false, 'damaged')]}));
  assert.equal(notices.length, 1);
  assert.match(notices[0][0], /^Unsaved work from an earlier window can be recovered/);
  // An unreadable folder or a failed listing says so instead of nothing.
  assert.deepEqual(await run(() => ({available: false, drafts: [], message: 'The recovery folder could not be read.'})), [['The recovery folder could not be read.', true]]);
  assert.deepEqual(await run(() => { throw new Error('Listing failed.'); }), [['Listing failed.', true]]);
});

test('pasted items stay selected when the paste needs a font measurement first', async () => {
  const pasted = [{target: 'atom', id: 7}, {target: 'scene', id: 2}], calls = [];
  const result = await sessionDrawing({action: 'edit', edit: {kind: 'paste', payload: SELECTION}}, async request => {
    calls.push(request.action);
    return request.action === 'edit'
      ? {...info(), session: 'p', revision: 3, pasted, drawing: {needs_measurements: true, label_measurements: {}}}
      : {...info(), session: 'p', revision: 3, pasted: null};
  }, () => ({}));
  assert.deepEqual(calls, ['edit', 'measure']);
  assert.deepEqual(result.pasted, pasted);
});

test('recovery takes over a draft through the session; a lost reply only resynchronizes', async () => {
  const calls = [];
  let server = {...info(), session: 'live', revision: 1, name: 'Canvas 1.chemvas', dirty: false}, lose = true;
  const editor = new SessionClient(async request => {
    calls.push(request);
    if (request.action === 'recover_draft') {
      server = {...server, ...info(3), revision: 2, name: 'Work.chemvas', dirty: true};
      if (lose) throw new Error('Connection lost');
    }
    return server;
  });
  await editor.load(info());
  const draft = 'd'.repeat(24);
  await assert.rejects(editor.recover(draft, true), /refreshed/);
  assert.deepEqual(calls.slice(1).map(call => [call.action, call.revision, call.draft, call.takeover]),
    [['recover_draft', 1, draft, true], ['read', undefined, undefined, undefined]]);
  assert.deepEqual([editor.name, editor.dirty, editor.info.revision], ['Work.chemvas', true, 2]);
  lose = false;
  await editor.recover('e'.repeat(24));
  assert.equal('takeover' in calls.at(-1), false);
  assert.equal(calls.at(-1).revision, 2);
});
