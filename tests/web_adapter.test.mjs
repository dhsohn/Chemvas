import test from 'node:test';
import assert from 'node:assert/strict';
import {SessionClient, sessionDrawing} from '../app/chemvas/web/transport.mjs';
import {sceneMarkup, measureAtomLabels, AtomLabelCache, clampView, zoomView, wheelView, pointInSheet, measureGlyphInk, marqueeSelection, measureDocumentLineHeight, selectionFrameMarkup, gridMarkup, smilesPreviewMarkup} from '../app/chemvas/web/scene.mjs';

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

// Execute the production event bodies against a small DOM port so input ordering
// is exercised without creating a second browser implementation in the test.
async function markInputHandlers(overrides = {}) {
  const {readFile} = await import('node:fs/promises');
  const {runInNewContext} = await import('node:vm');
  const source = await readFile(new URL('../app/chemvas/web/app.mjs', import.meta.url), 'utf8');
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

// Production insertion lifecycle, exercised with deferred HTTP responses.
async function smilesInputState(overrides = {}) {
  const {source, runInNewContext} = await markInputHandlers();
  const elements = new Map();
  const context = {
    smilesInsert: null, smilesPreviewPending: null, smilesGeneration: 0, previewPending: null, markHover: {pending:false}, templateHover:{request:null,result:null,pending:false}, loading: false,
    editor: {document: info().document, busy: false, readOnly: false, info: {session:'s',revision:1,sheet:[800,600]}},
    $: id => { if (!elements.has(id)) elements.set(id, {value:'CO'}); return elements.get(id); },
    render(){}, notice(){}, finishNoteEdit:async()=>{}, cancelGesture:()=>context.cancelSmilesInsert(),
    visibleSceneRect:()=>[-200,-100,400,200], pointInSheet,
    canvas:{focus(){}}, ui:{off_sheet_guidance:'outside'},
    sessionRequest:async request=>({...info(2), request}), edit:async()=>true,
    ...overrides,
  };
  const start = source.indexOf('// SMILES insertion is one disposable server candidate');
  const end = source.indexOf('// Mark placement also needs', start);
  assert.ok(start >= 0 && end > start);
  runInNewContext(source.slice(start,end), context);
  return {context,elements};
}

const flushSmiles = () => new Promise(resolve => setImmediate(resolve));

test('SMILES ghost displays only candidate additions at one group opacity', () => {
  const original = info(1), candidate = info(3);
  original.document.state.marks = [{kind:'plus'}];
  candidate.document.state.model.bonds = [null,{a:1,b:2,style:'single',color:'#123456'}];
  original.document.state.model.bonds = [null];
  candidate.drawing.bonds[1] = [{line:[50,40,70,40]}];
  candidate.drawing.brackets = [{kind:'parenthesis_left',path:[['M',[3,4]],['L',[7,8]]],width:1,color:'#000000'}];
  candidate.drawing.marks = [0,1].map(id=>({id,kind:'radical',x:50+id,y:40,radius:1,color:'#333333',hit_radius:4}));
  const before = JSON.stringify([original,candidate]);
  const markup = smilesPreviewMarkup(candidate, original.document, 0.5);
  assert.ok(markup.startsWith('<g opacity="0.5000">'));
  assert.ok(markup.includes('data-item="atom:1"') && markup.includes('data-item="bond:1"') && markup.includes('data-item="mark:1"'));
  assert.ok(!markup.includes('data-item="atom:0"') && !markup.includes('data-item="mark:0"'));
  assert.ok(!markup.includes('data-item="ts_bracket:0"'));
  assert.ok(!markup.includes('id="selection-frame"') && !markup.includes('id="rotation-handle"'));
  assert.equal(JSON.stringify([original,candidate]),before);
});

test('SMILES begins at viewport center and coalesces pointer motion without edits', async () => {
  const calls = [], releases = [], edits = [];
  const {context:c} = await smilesInputState({
    sessionRequest: request=>{calls.push(request);return new Promise(resolve=>releases.push(resolve));},
    edit:async change=>{edits.push(change);},
  });
  await c.beginSmilesInsert();
  assert.deepEqual([calls[0].edit.x,calls[0].edit.y],[0,0]);
  c.moveSmilesPreview({x:10,y:20}); c.moveSmilesPreview({x:30,y:40});
  assert.equal(calls.length,1);
  releases[0]({id:'old'}); await flushSmiles();
  assert.equal(calls.length,2); assert.deepEqual([calls[1].edit.x,calls[1].edit.y],[30,40]);
  releases[1]({id:'current'}); await c.smilesPreviewPending;
  assert.equal(c.smilesInsert.info.id,'current');
  assert.equal(edits.length,0);
  assert.equal(c.editor.info.revision,1);
});

test('SMILES late previews cannot return after cancellation, replacement or revision changes', async () => {
  for (const action of ['cancel','session','revision','readOnly']) {
    let release;
    const {context:c} = await smilesInputState({sessionRequest:()=>new Promise(resolve=>{release=resolve;})});
    await c.beginSmilesInsert();
    const active = c.smilesInsert, pending = c.smilesPreviewPending;
    if (action === 'cancel') c.cancelSmilesInsert();
    else if (action === 'readOnly') c.editor.readOnly=true;
    else c.editor.info[action] += 1;
    release({id:'stale'}); await pending;
    assert.equal(active.info,null);
    assert.equal(c.smilesInsert,null);
  }
});

test('SMILES off-sheet hides the ghost but keeps insertion pending for re-entry', async () => {
  const calls=[];
  const {context:c} = await smilesInputState({sessionRequest:async request=>{calls.push(request);return {id:'preview'};}});
  await c.beginSmilesInsert(); await c.smilesPreviewPending;
  c.moveSmilesPreview({x:500,y:0}); await flushSmiles();
  assert.equal(c.smilesInsert.info,null); assert.equal(c.smilesInsert.position,null);
  assert.equal(calls.length,1);
  c.moveSmilesPreview({x:10,y:20}); await c.smilesPreviewPending;
  assert.equal(c.smilesInsert.info.id,'preview'); assert.equal(calls.length,2);
});

test('SMILES click waits for measurements and commits once at the clicked position', async () => {
  const requests=[], releases=[], edits=[];
  const {context:c} = await smilesInputState({
    sessionRequest:request=>{requests.push(request);return new Promise(resolve=>releases.push(resolve));},
    edit:async change=>{edits.push(change);return true;},
  });
  await c.beginSmilesInsert();
  const first = c.commitSmilesInsert({x:71,y:83});
  await c.commitSmilesInsert({x:91,y:93});
  assert.equal(requests.length,1); assert.equal(edits.length,0);
  releases[0]({id:'initial'}); await flushSmiles();
  assert.equal(requests.length,2); assert.equal(c.loading,true);
  releases[1]({id:'ready'}); await first;
  assert.equal(edits.length,1); assert.deepEqual([edits[0].x,edits[0].y],[71,83]);
  assert.equal(c.smilesInsert,null); assert.equal(c.loading,false);
});

test('SMILES cancellation during final font preparation prevents the commit', async () => {
  const releases=[], edits=[];
  const {context:c} = await smilesInputState({
    sessionRequest:()=>new Promise(resolve=>releases.push(resolve)), edit:async change=>edits.push(change),
  });
  await c.beginSmilesInsert();
  const pending = c.commitSmilesInsert({x:10,y:20});
  releases[0]({}); await flushSmiles();
  c.cancelSmilesInsert(); releases[1]({}); await pending;
  assert.equal(edits.length,0); assert.equal(c.smilesInsert,null); assert.equal(c.loading,false);
});

test('SMILES parse failure clears only the transient mode and reports the error', async () => {
  const notices=[];
  const {context:c} = await smilesInputState({sessionRequest:async()=>{throw new Error('RDKit is unavailable');},notice:(...args)=>notices.push(args)});
  const original=c.editor.document;
  await c.beginSmilesInsert(); await c.smilesPreviewPending;
  assert.equal(c.smilesInsert,null); assert.equal(c.editor.document,original);
  assert.deepEqual(notices.at(-1),['RDKit is unavailable',true]);
});

test('SMILES begin cannot resurrect after cancellation while a note is being saved', async () => {
  for (const change of ['cancel','session']) {
    let finish;
    const calls=[];
    const {context:c} = await smilesInputState({finishNoteEdit:()=>new Promise(resolve=>{finish=resolve;}),sessionRequest:async request=>calls.push(request)});
    const pending=c.beginSmilesInsert();
    if (change === 'cancel') c.cancelSmilesInsert();
    else c.editor.info.session='replacement';
    finish(); await pending;
    assert.equal(c.smilesInsert,null); assert.equal(calls.length,0);
  }
});

test('SMILES begin follows its own completed note save without losing cancellation identity', async () => {
  let finish;
  const {context:c}=await smilesInputState();
  c.finishNoteEdit=()=>{c.cancelSmilesInsert();return new Promise(resolve=>{finish=resolve;});};
  const pending=c.beginSmilesInsert();
  c.editor.info.revision++;
  finish(); await pending; await c.smilesPreviewPending;
  assert.equal(c.smilesInsert.revision,2);
  assert.equal(c.smilesInsert.info.request.edit.smiles,'CO');
});

test('SMILES final preparation drains earlier gesture and mark font measurements', async () => {
  for (const older of ['gesture','mark','both']) {
    const requests=[], edits=[]; let finishGesture, finishMark;
    const {context:c}=await smilesInputState({sessionRequest:async request=>{requests.push(request);return {};},edit:async change=>edits.push(change)});
    await c.beginSmilesInsert(); await c.smilesPreviewPending;
    if (older !== 'mark') c.previewPending=new Promise(resolve=>{finishGesture=resolve;});
    if (older !== 'gesture') c.markHover.pending=new Promise(resolve=>{finishMark=resolve;});
    const pending=c.commitSmilesInsert({x:33,y:44});
    await flushSmiles();
    assert.equal(requests.length,1); assert.equal(edits.length,0);
    finishGesture?.();
    if (older === 'both') { await flushSmiles(); assert.equal(requests.length,1); }
    finishMark?.(); await pending;
    assert.equal(requests.length,2); assert.equal(edits.length,1);
    assert.deepEqual([requests[1].edit.x, requests[1].edit.y],[33,44]);
  }
});

test('SMILES cancellation while an older preview drains prevents preparation and commit', async () => {
  let finish;
  const requests=[], edits=[];
  const {context:c}=await smilesInputState({sessionRequest:async request=>{requests.push(request);return {};},edit:async change=>edits.push(change)});
  await c.beginSmilesInsert(); await c.smilesPreviewPending;
  c.previewPending=new Promise(resolve=>{finish=resolve;});
  const pending=c.commitSmilesInsert({x:33,y:44});
  c.cancelSmilesInsert(); finish(); await pending;
  assert.equal(requests.length,1); assert.equal(edits.length,0); assert.equal(c.smilesInsert,null);
});

test('SMILES can prepare after an older cancelled preview fails', async () => {
  let reject;
  const edits=[];
  const {context:c}=await smilesInputState({edit:async change=>edits.push(change)});
  await c.beginSmilesInsert(); await c.smilesPreviewPending;
  c.previewPending=new Promise((_,fail)=>{reject=fail;});
  const pending=c.commitSmilesInsert({x:33,y:44});
  reject(new Error('cancelled dagger')); await pending;
  assert.equal(edits.length,1); assert.equal(c.smilesInsert,null);
});

test('SMILES ignores activation before the UI or document is connected', async () => {
  for (const absent of ['ui','document']) {
    const {context:c}=await smilesInputState();
    if (absent === 'ui') c.ui=null;
    else {c.editor.document=null;c.editor.info=null;}
    await c.beginSmilesInsert();
    assert.equal(c.smilesInsert,null);
  }
});

test('a pending Text-tool pick cannot reopen an editor after SMILES begins', async () => {
  const {source,runInNewContext}=await markInputHandlers();
  const opened=[]; let finishPick;
  const {context:c}=await smilesInputState({tool:'note',point:event=>({x:event.clientX,y:event.clientY}),hitsAt:()=>[],viewScale:()=>1,
    beginNoteEdit:(...args)=>opened.push(args),api:()=>new Promise(resolve=>{finishPick=resolve;})});
  const start=source.indexOf('async function noteToolPress(event) {');
  const end=source.indexOf("noteEditorElement.addEventListener('focusout'",start);
  runInNewContext(source.slice(start,end),c);
  const pending=c.noteToolPress({clientX:12,clientY:34});
  await flushSmiles();
  await c.beginSmilesInsert(); await c.smilesPreviewPending;
  finishPick({target:null}); await pending;
  assert.ok(c.smilesInsert); assert.equal(opened.length,0);
});

test('a pending bond menu cannot appear after SMILES begins or is cancelled', async () => {
  const {source,runInNewContext}=await markInputHandlers();
  for (const cancel of [false,true]) {
    let finishMenu;
    const {context:c}=await smilesInputState({point:()=>({x:12,y:34}),hitsAt:()=>[],viewScale:()=>1,gesture:null,
      api:()=>new Promise(resolve=>{finishMenu=resolve;})});
    const start=source.indexOf('async function showBondMenu(event) {');
    const end=source.indexOf("document.addEventListener('pointerdown'",start);
    runInNewContext(source.slice(start,end),c);
    const menu=c.$('bond-menu');menu.hidden=true;
    const pending=c.showBondMenu({clientX:12,clientY:34});
    await c.beginSmilesInsert(); await c.smilesPreviewPending;
    if (cancel) c.cancelSmilesInsert();
    finishMenu({menu:{bond:1,entries:[]}}); await pending;
    assert.equal(menu.hidden,true);
  }
});

test('starting SMILES clears an existing Ring ghost and rejects its late preview', async () => {
  const {source,runInNewContext}=await markInputHandlers();
  let finish;
  const {context:c}=await smilesInputState({tool:'benzene',pointerPosition:{clientX:12,clientY:34},gesture:null,point:()=>({x:12,y:34}),
    ringTemplate:{size:6,style:'benzene'},document:{elementFromPoint:()=>null},api:()=>new Promise(resolve=>{finish=resolve;})});
  const start=source.indexOf('async function refreshTemplateHover() {');
  const end=source.indexOf('// Hover previews follow',start);
  runInNewContext(source.slice(start,end),c);
  c.templateHover.result={id:'old-ring'};
  const pending=c.refreshTemplateHover();
  await c.beginSmilesInsert(); await c.smilesPreviewPending;
  assert.equal(c.templateHover.result,null); assert.equal(c.templateHover.request,null);
  finish({preview:{id:'late-ring'}}); await pending;
  assert.equal(c.templateHover.result,null); assert.ok(c.smilesInsert);
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
  const {readFile} = await import('node:fs/promises');
  const {runInNewContext} = await import('node:vm');
  const {noteBlocks, noteBlocksHtml, serializeNoteEditor, styleNoteText, formatNoteBlocks, noteFormatState} = await import('../app/chemvas/web/scene.mjs');
  const source = await readFile(new URL('../app/chemvas/web/app.mjs', import.meta.url), 'utf8');
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
    smilesInsert: null,
  };
  const start = source.indexOf('function textFormatButton(spec, action, checkable = false) {');
  const end = source.indexOf('// SMILES insertion is one disposable server candidate', start);
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

// File > Export MOL's own handler over a held note commit and session reply.
async function exportMolHandler() {
  const {readFile} = await import('node:fs/promises');
  const {runInNewContext} = await import('node:vm');
  const source = await readFile(new URL('../app/chemvas/web/app.mjs', import.meta.url), 'utf8');
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
  const {readFile} = await import('node:fs/promises');
  const {runInNewContext} = await import('node:vm');
  const source = await readFile(new URL('../app/chemvas/web/app.mjs', import.meta.url), 'utf8');
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

test('a late note save failure reopens nothing over a newer note, SMILES or a document load', async () => {
  const rows = [
    ['a newer note', h => h.context.beginNoteEdit(7), true, ['A', 'B']],
    ['SMILES insertion', h => { h.context.smilesInsert = {smiles: 'C'}; }, false, []],
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
  Object.assign(h.context, {smilesGeneration: 0, point: event => ({x: event.clientX, y: event.clientY}), hitsAt: () => [], viewScale: () => 1});
  await h.open(7); await h.caret(2); await h.type('X');
  h.element.handlers.focusout({relatedTarget: null});
  void h.context.noteToolPress({clientX: 12, clientY: 34}); await h.settle();
  assert.deepEqual([h.replies.map(reply => reply.body.action), Boolean(h.context.noteEditor), h.chars(), h.notices],
    [[], true, ['A', 'B', 'X'], [['Note save failed.', true]]]);
});

test('a failed note save stops SMILES insertion without clearing its notice', async () => {
  const notices = [], requests = [];
  const {context: c} = await smilesInputState({finishNoteEdit: async () => false, notice: (...args) => notices.push(args),
    sessionRequest: async request => { requests.push(request); return {...info(2), request}; }});
  await c.beginSmilesInsert(); await flushSmiles();
  assert.deepEqual([c.smilesInsert, notices.length, requests.length], [null, 0, 0]);
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
