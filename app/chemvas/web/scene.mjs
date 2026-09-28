// Display primitives supplied by the existing Chemvas rendering services.
function escapeText(value) {
  return String(value).replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;'}[char]));
}

const number = value => Number(value).toFixed(4);
const line = (x1, y1, x2, y2, extra = '') => `<line x1="${number(x1)}" y1="${number(y1)}" x2="${number(x2)}" y2="${number(y2)}" ${extra}/>`;

export function measureAtomLabels(spec, context, measureLineHeight) {
  return Object.fromEntries(spec.queries.map(({key, text, pixels}) => {
    context.font = `${pixels}px ${JSON.stringify(spec.family)}`;
    const measured = context.measureText(text);
    const capital = context.measureText('H');
    return [key, {width: measured.width, ascent: measured.fontBoundingBoxAscent, descent: measured.fontBoundingBoxDescent, cap_height: capital.actualBoundingBoxAscent, line_height: measureLineHeight(context.font, text)}];
  }));
}

// Only the font engine boundary is browser-specific; hulls and bond clipping stay in Python.
export function measureGlyphInk(context, family, {text, pixels}) {
  const font = `${pixels}px ${JSON.stringify(family)}`;
  context.font = font;
  const box = context.measureText(text);
  const width = box.actualBoundingBoxLeft + box.actualBoundingBoxRight;
  const height = box.actualBoundingBoxAscent + box.actualBoundingBoxDescent;
  if (!width || !height) return [];
  // Bound raster work even for very long labels or imported large font sizes.
  const scale = Math.min(8, 2048 / (width + 4), 512 / (height + 4));
  const ox = (2 + box.actualBoundingBoxLeft) * scale, oy = (2 + box.actualBoundingBoxAscent) * scale;
  context.canvas.width = Math.ceil((width + 4) * scale);
  context.canvas.height = Math.ceil((height + 4) * scale);
  context.font = font;
  context.setTransform(scale, 0, 0, scale, ox, oy);
  context.fillText(text, 0, 0);
  const w = context.canvas.width, h = context.canvas.height;
  const {data} = context.getImageData(0, 0, w, h);
  const points = [];
  for (let y = 0; y < h; y++) {
    let left = 0, right = w - 1;
    // Half coverage excludes the faint antialias fringe outside the glyph outline.
    while (left < w && data[(y * w + left) * 4 + 3] < 128) left++;
    if (left === w) continue;
    while (right > left && data[(y * w + right) * 4 + 3] < 128) right--;
    for (const [x, row] of [[left, y], [right + 1, y], [left, y + 1], [right + 1, y + 1]]) {
      // Raster hinting can cross the font engine's reported ink bounds.
      points.push([
        Math.max(-box.actualBoundingBoxLeft, Math.min(box.actualBoundingBoxRight, (x - ox) / scale)),
        Math.max(-box.actualBoundingBoxAscent, Math.min(box.actualBoundingBoxDescent, (row - oy) / scale)),
      ]);
    }
  }
  context.setTransform(1, 0, 0, 1, 0, 0);
  return points;
}

export class AtomLabelCache {
  #metrics = new Map();
  #ink = new Map();

  measure(spec, context, measureLineHeight) {
    const keyFor = query => JSON.stringify([spec.family, query.key, query.pixels]);
    const missing = spec.queries.filter(query => !this.#metrics.has(keyFor(query)));
    const measured = measureAtomLabels({...spec, queries: missing}, context, measureLineHeight);
    const metrics = new Map(), ink = new Map(), result = {family: spec.family, metrics: {}, ink: {}};
    for (const query of spec.queries) {
      const key = keyFor(query), glyph = `${query.pixels}:${query.text}`;
      const glyphKey = JSON.stringify([spec.family, glyph]);
      const value = this.#metrics.get(key) ?? measured[query.key];
      const points = ink.get(glyphKey) ?? this.#ink.get(glyphKey) ?? measureGlyphInk(context, spec.family, query);
      metrics.set(key, value);
      ink.set(glyphKey, points);
      result.metrics[query.key] = value;
      result.ink[glyph] = points;
    }
    // Replace, rather than accumulate, fonts from discarded drawings.
    this.#metrics = metrics;
    this.#ink = ink;
    return result;
  }
}

export function sceneMarkup(document, {selection = new Set(), preview = null, drawing, handleTarget = null, handleStyle = null, scale = 1} = {}) {
  const state = document.state;
  const atoms = {...state.model.atoms};
  let parts = [];
  const layers = [];
  const finishLayer = (z, order = 0) => { layers.push({z, order, html: parts.join('')}); parts = []; };
  (drawing.shapes ?? []).forEach((shape, index) => {
    const key = `shape:${index}`;
    const guide = preview?.kind === 'shape' && index === drawing.shapes.length - 1;
    const stroke = guide && shape.stroke === 'none' ? 'dashed' : shape.stroke;
    const color = guide ? '#787878' : shape.color;
    const attributes = `data-item="${key}" fill="${escapeText(shape.fill ?? 'transparent')}" fill-opacity="${number(shape.alpha ?? 1)}" stroke="${stroke === 'none' ? 'none' : escapeText(color)}" stroke-width="${number(shape.line_width)}" stroke-linecap="round" stroke-linejoin="round" pointer-events="all"${guide ? ' stroke-opacity="0.7059"' : ''}${stroke === 'dashed' ? ` stroke-dasharray="${number(shape.line_width * 4)} ${number(shape.line_width * 2)}"` : stroke === 'dotted' ? ` stroke-dasharray="${number(shape.line_width)} ${number(shape.line_width * 2)}"` : ''}`;
    if (shape.kind === 'ellipse') parts.push(`<ellipse ${attributes} cx="${number(shape.x + shape.width / 2)}" cy="${number(shape.y + shape.height / 2)}" rx="${number(shape.width / 2)}" ry="${number(shape.height / 2)}"/>`);
    else if (!shape.width || !shape.height) parts.push(`<path ${attributes} d="M${number(shape.x)} ${number(shape.y)} h${number(shape.width)} v${number(shape.height)} h${number(-shape.width)} Z"/>`);
    else parts.push(`<rect ${attributes} x="${number(shape.x)}" y="${number(shape.y)}" width="${number(shape.width)}" height="${number(shape.height)}" rx="${number(shape.radius)}"/>`);
    finishLayer(shape.z ?? -10, 1);
  });
  for (const [index, ring] of (state.ring_fills ?? []).entries()) {
    parts.push(`<polygon data-item="ring:${index}" points="${ring.points.map(p => p.map(number).join(',')).join(' ')}" fill="${escapeText(ring.color ?? 'transparent')}" fill-opacity="${number(ring.alpha)}" pointer-events="all"/>`);
  }
  finishLayer(-5);
  state.model.bonds.forEach((bond, index) => {
    if (!bond) return;
    const a = atoms[bond.a], b = atoms[bond.b];
    const key = `bond:${index}`;
    parts.push(`<g data-item="${key}" fill="none" stroke="${escapeText(bond.color)}" stroke-width="${drawing.line_width}" stroke-linecap="round">`);
    parts.push(`<title>Bond ${bond.a}–${bond.b}, ${escapeText(bond.style)}</title>`);
    if (selection.has(key)) parts.push(line(a.x, a.y, b.x, b.y, 'stroke="#0d9488" stroke-width="7" opacity="0.2" pointer-events="none"'));
    // No bond/ring algorithm lives here: the desktop planner supplied these primitives.
    for (const primitive of drawing.bonds[index] ?? []) {
      if (primitive.line) {
        const [x1, y1, x2, y2] = primitive.line;
        if (x1 !== x2 || y1 !== y2) parts.push(line(x1, y1, x2, y2));
      }
      else if (primitive.dots) {
        for (const [x, y] of primitive.dots) parts.push(`<circle cx="${number(x)}" cy="${number(y)}" r="${number(primitive.radius)}" fill="${escapeText(bond.color)}" stroke="none"/>`);
      }
      else if (primitive.polygon) parts.push(`<polygon points="${primitive.polygon.map(p => p.map(number).join(',')).join(' ')}" fill="${escapeText(bond.color)}" ${primitive.outlined ? '' : 'stroke="none"'}/>`);
    }
    parts.push('</g>');
  });
  finishLayer(0);
  for (const [id, atom] of Object.entries(atoms)) {
    const key = `atom:${id}`, x = number(atom.x), y = number(atom.y);
    parts.push(`<g data-item="${key}">`);
    parts.push(`<title>Atom ${id}: ${escapeText(atom.element)}</title>`);
    if (selection.has(key)) parts.push(`<circle cx="${x}" cy="${y}" r="7" fill="#d6ece7" stroke="#0d9488" stroke-width="0.8" pointer-events="none"/>`);
    const runs = drawing.atom_layouts?.[id] ?? [];
    for (const run of runs) {
      parts.push(`<text x="${number(run.x)}" y="${number(run.y)}" font-family="${escapeText(drawing.label_measurements.family)}" font-size="${number(run.pixels)}" fill="${escapeText(atom.color)}" pointer-events="none">${escapeText(run.text)}</text>`);
    }
    const rect = drawing.atom_hit_rects?.[id];
    if (rect) parts.push(`<rect x="${number(rect[0])}" y="${number(rect[1])}" width="${number(rect[2])}" height="${number(rect[3])}" fill="transparent" pointer-events="all"/>`);
    const offset = runs.length ? drawing.label_measurements.offset : 0;
    const radius = drawing.atom_hit_radii[id];
    if (radius !== null) parts.push(`<circle cx="${number(atom.x + offset)}" cy="${number(atom.y - offset)}" r="${number(radius)}" fill="transparent" pointer-events="all"/>`);
    parts.push('</g>');
  }
  finishLayer(3);
  state.arrows.forEach((arrow, index) => {
    const geometry = drawing.arrows[index], color = escapeText(geometry.color);
    const path = geometry.path.map(([command, coordinates]) => `${command}${coordinates.map(number).join(' ')}`).join(' ');
    parts.push(`<g data-item="arrow:${index}" stroke="${color}" stroke-width="${number(geometry.width)}" stroke-linecap="${geometry.cap}" stroke-linejoin="${geometry.join}" fill="none">`);
    if (selection.has(`arrow:${index}`)) parts.push(`<path d="${path}" stroke="#0d9488" stroke-width="7" opacity="0.2" pointer-events="none"/>`);
    parts.push(`<path d="${path}"${geometry.dashed ? ` stroke-dasharray="${number(geometry.width * 4)} ${number(geometry.width * 2)}"` : ''}/>`);
    parts.push(`<path d="${path}" stroke="transparent" pointer-events="stroke"/>`);
    parts.push('</g>');
  });
  for (const label of drawing.arrow_labels ?? []) {
    parts.push(`<foreignObject data-item="arrow:${label.id}" x="${number(label.x)}" y="${number(label.y)}" width="${number(label.width)}" height="${number(label.height)}"><div xmlns="http://www.w3.org/1999/xhtml" class="arrow-label" data-arrow-label="${label.id}:${label.side}">${label.html}</div></foreignObject>`);
  }
  finishLayer(0);
  state.notes.forEach((note, index) => {
    parts.push(`<text data-item="note:${index}" x="${number(note.x)}" y="${number(note.y)}" font-family="${escapeText(state.settings.text_font_family)}" font-size="${number(state.settings.text_font_size)}" fill="${selection.has(`note:${index}`) ? '#0d9488' : escapeText(state.settings.text_color)}">`);
    String(note.text).split('\n').forEach((text, i) => parts.push(`<tspan x="${number(note.x)}" dy="${i ? '1.2em' : '0'}">${escapeText(text)}</tspan>`));
    parts.push('</text>');
  });
  finishLayer(0);
  const [handleKind, handleId] = handleTarget?.split(':') ?? [];
  if (handleKind === 'arrow' && handleStyle && drawing.arrows[handleId]) {
    for (const {handle, point, snapped} of drawing.arrows[handleId].handles) {
      parts.push(`<circle data-handle="${handle}" data-arrow-id="${handleId}" cx="${number(point[0])}" cy="${number(point[1])}" r="${number(handleStyle.size / (2 * scale))}" fill="${snapped ? escapeText(handleStyle.color) : '#ffffff'}" stroke="${escapeText(handleStyle.color)}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`);
    }
  }
  if (preview?.kind === 'line') parts.push(line(preview.start.x, preview.start.y, preview.end.x, preview.end.y, 'stroke="#0d9488" stroke-width="1.5" stroke-dasharray="3 2" pointer-events="none"'));
  if (handleKind === 'shape' && handleStyle && drawing.shapes[handleId]) {
    for (const {handle, point} of drawing.shapes[handleId].handles) {
      const size = ['shape_n', 'shape_e', 'shape_s', 'shape_w'].includes(handle) ? handleStyle.edge_size : handleStyle.size;
      parts.push(`<circle data-handle="${handle}" data-shape-id="${handleId}" cx="${number(point[0])}" cy="${number(point[1])}" r="${number(size / (2 * scale))}" fill="#ffffff" stroke="${escapeText(handleStyle.color)}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`);
    }
  }
  if (preview?.kind === 'marquee') {
    const {start, end} = preview;
    parts.push(`<rect x="${number(Math.min(start.x, end.x))}" y="${number(Math.min(start.y, end.y))}" width="${number(Math.abs(end.x - start.x))}" height="${number(Math.abs(end.y - start.y))}" fill="Highlight" fill-opacity="0.12" stroke="Highlight" stroke-width="1" vector-effect="non-scaling-stroke" pointer-events="none"/>`);
  }
  finishLayer(30);
  return layers.sort((a, b) => a.z - b.z || a.order - b.order).map(layer => layer.html).join('');
}

// QGraphicsView's rubber band intersects item shapes; SVG owns the same
// operation on the materialized native geometry, including transparent targets.
export function marqueeSelection(svg, start, end, initial = [], additive = false) {
  const matrix = svg.getCTM();
  const first = {x: matrix.a * start.x + matrix.c * start.y + matrix.e, y: matrix.b * start.x + matrix.d * start.y + matrix.f};
  const last = {x: matrix.a * end.x + matrix.c * end.y + matrix.e, y: matrix.b * end.x + matrix.d * end.y + matrix.f};
  const rect = svg.createSVGRect();
  rect.x = Math.min(first.x, last.x); rect.y = Math.min(first.y, last.y);
  rect.width = Math.abs(last.x - first.x); rect.height = Math.abs(last.y - first.y);
  const selected = new Set(additive ? initial : []);
  if (rect.width && rect.height) {
    for (const element of svg.getIntersectionList(rect, svg.querySelector('#drawing'))) {
      const key = element.closest('[data-item]')?.dataset.item;
      if (key && /^(atom|bond|arrow|shape|ring):/.test(key)) selected.add(key);
    }
  }
  return selected;
}

// SVG viewBox is the browser representation of the native view transform.
export function zoomView(view, viewport, factor, policy, position = {x: viewport.width / 2, y: viewport.height / 2}) {
  const scale = Math.min(viewport.width / view.width, viewport.height / view.height);
  const next = Math.max(policy.min, Math.min(policy.max, scale / factor));
  const left = view.x - (viewport.width / scale - view.width) / 2;
  const top = view.y - (viewport.height / scale - view.height) / 2;
  return {x: left + position.x / scale - position.x / next, y: top + position.y / scale - position.y / next, width: viewport.width / next, height: viewport.height / next};
}

export function wheelView(view, viewport, event, policy, lineHeight) {
  const dx = event.deltaX * (event.deltaMode === 1 ? lineHeight : event.deltaMode === 2 ? viewport.width : 1);
  const dy = event.deltaY * (event.deltaMode === 1 ? lineHeight : event.deltaMode === 2 ? viewport.height : 1);
  if (event.ctrlKey || (policy.zoom_modifier === 'meta' && event.metaKey)) {
    if (!dy) return view;
    // Browser deltas have the opposite sign to Qt's wheel deltas.
    return zoomView(view, viewport, policy.wheel_base ** (dy * policy.angle_per_pixel), policy, event.position);
  }
  const scale = Math.min(viewport.width / view.width, viewport.height / view.height);
  return {...view, x: view.x + dx / scale, y: view.y + dy / scale};
}

// Adapt the centered sheet rectangle to browser pointer coordinates.
export function pointInSheet({x, y}, [width, height]) {
  return x >= -width / 2 && x <= width / 2 && y >= -height / 2 && y <= height / 2;
}
