import test from 'node:test';
import assert from 'node:assert/strict';
import {SessionClient, sessionDrawing} from '../app/chemvas/web/transport.mjs';
import {sceneMarkup, measureAtomLabels, AtomLabelCache, zoomView, wheelView, pointInSheet, measureGlyphInk, marqueeSelection, measureDocumentLineHeight, selectionFrameMarkup, gridMarkup} from '../app/chemvas/web/scene.mjs';

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
      return ['bond:0', 'bond:0', 'ring:0', 'shape:1', 'arrow:2', 'note:0', null].map(key => ({closest: () => key && ({dataset:{item:key}})}));
    },
  };
  const start = {x:40,y:30}, end = {x:10,y:5};
  assert.deepEqual([...marqueeSelection(svg,start,end,base,true)], ['atom:9','bond:0','ring:0','shape:1','arrow:2']);
  assert.deepEqual([...marqueeSelection(svg,end,start,base)], ['bond:0','ring:0','shape:1','arrow:2']);
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


test('imported marks draw native geometry and escape custom text without edit targets', () => {
  const source = info();
  source.drawing.marks = [
    {id:0, kind:'radical', x:12, y:15, radius:1.2, color:'#123456'},
    {id:1, kind:'circled_plus', x:20, y:25, radius:4, stroke:0.975, extent:1.92, color:'#123456'},
    {id:2, kind:'circled_minus', x:30, y:35, radius:4, stroke:0.975, extent:1.92, color:'#123456'},
    {id:3, kind:'plus', color:'#123456', runs:[{x:40, y:45, pixels:13, text:'<script>"&'}]},
    {id:4, kind:'minus', color:'#123456', runs:[]},
  ];
  const before = JSON.stringify(source);
  const markup = sceneMarkup(source.document, {drawing:source.drawing});
  assert.equal((markup.match(/data-mark=/g) ?? []).length, 5);
  assert.ok(markup.includes('<circle cx="12.0000" cy="15.0000" r="1.2000"/>'));
  assert.equal((markup.match(/<circle r="4.0000"/g) ?? []).length, 2);
  assert.equal((markup.match(/<line /g) ?? []).length, 3);
  assert.ok(markup.includes('stroke-width="0.9750"'));
  assert.ok(markup.includes('&lt;script&gt;&quot;&amp;'));
  assert.ok(!markup.includes('<script>') && !markup.includes('data-item="mark:'));
  assert.equal(JSON.stringify(source), before);
});
