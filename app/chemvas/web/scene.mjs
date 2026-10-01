// Display primitives supplied by the existing Chemvas rendering services.
function escapeText(value) {
  return String(value).replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;'}[char]));
}

const number = value => Number(value).toFixed(4);
const line = (x1, y1, x2, y2, extra = '') => `<line x1="${number(x1)}" y1="${number(y1)}" x2="${number(x2)}" y2="${number(y2)}" ${extra}/>`;

export function measureDocumentLineHeight(probe, font, text) {
  probe.style.font = font;
  const pixels = parseFloat(probe.style.fontSize);
  // A small CSS line box is already pixel-rounded. Measure the font's normal
  // line (including its gap) at a large em before applying Qt's final ceiling.
  probe.style.fontSize = '2048px';
  probe.textContent = text;
  return Math.ceil(probe.getBoundingClientRect().height * pixels / 2048);
}

const fixed = value => Math.round(value * 64) / 64;

export function measureNoteFont(probe, context, {italic, weight, pixels, family}) {
  // Measure at a large em, as QFontEngine reports unrounded 1/64 metrics.
  const font = `${italic ? 'italic ' : ''}${weight} 2048px ${family}`;
  context.font = font;
  const measured = context.measureText('H');
  probe.style.font = font;
  probe.textContent = 'H';
  const scale = pixels / 2048;
  const ascent = fixed(measured.fontBoundingBoxAscent * scale);
  const descent = fixed(measured.fontBoundingBoxDescent * scale);
  return {ascent, descent, leading: Math.max(0, fixed(probe.getBoundingClientRect().height * scale) - ascent - descent)};
}

// Qt sizes each note line from the fonts of its own runs and adds proportional
// spacing below the text, where CSS would divide it around the text. A zero-width
// strut gives every line Qt's height and baseline; the runs themselves take no
// line height, and scripts shift relatively like QTextLine's baseline offsets.
const noteFontOf = element => {
  const style = getComputedStyle(element);
  return {italic: style.fontStyle !== 'normal', weight: style.fontWeight, pixels: parseFloat(style.fontSize), family: style.fontFamily};
};

// The document font, the server's validated declarations and script offsets.
export function styleNoteText(root, spec, metrics) {
  Object.assign(root.style, {fontFamily: JSON.stringify(spec.family), fontSize: `${spec.pixels}px`, fontWeight: String(spec.weight), fontStyle: spec.italic ? 'italic' : 'normal', color: spec.color, textAlign: spec.align});
  // The CSP ignores style attributes; apply the declarations through CSSOM.
  for (const element of root.querySelectorAll('[data-style]')) {
    for (const declaration of element.dataset.style.split(';')) {
      const split = declaration.indexOf(':');
      if (split > 0) element.style.setProperty(declaration.slice(0, split).trim(), declaration.slice(split + 1).trim());
    }
  }
  for (const run of root.querySelectorAll('[data-script]')) {
    const base = metrics({...noteFontOf(run.parentElement), pixels: Number(run.dataset.basePixels)});
    const height = base.ascent + base.descent;
    run.style.top = `${run.dataset.script === 'sub' ? height / 6 : -height / 2}px`;
  }
}

export function layoutNoteText(root, spec, metrics) {
  const fontOf = noteFontOf;
  root.querySelectorAll('.note-strut').forEach(strut => strut.remove());
  styleNoteText(root, spec, metrics);
  for (const block of root.children) {
    const lines = [{after: null, fonts: []}];
    const walk = node => {
      for (const child of node.childNodes) {
        if (child.nodeType === Node.TEXT_NODE) {
          if (child.data) lines.at(-1).fonts.push(fontOf(child.parentElement));
        } else if (child.nodeName === 'BR') lines.push({after: child, fonts: []});
        else walk(child);
      }
    };
    walk(block);
    for (const line of lines) {
      const measured = (line.fonts.length ? line.fonts : [fontOf(block)]).map(metrics);
      const ascent = Math.max(...measured.map(font => font.ascent));
      const height = Math.ceil(ascent + Math.max(...measured.map(font => font.descent)) + Math.max(...measured.map(font => font.leading)));
      const pitch = fixed(height * spec.line_spacing);
      const strut = document.createElement('span');
      strut.className = 'note-strut';
      Object.assign(strut.style, {height: `${pitch}px`, verticalAlign: `${ascent - pitch}px`});
      if (line.after) line.after.after(strut);
      else block.prepend(strut);
    }
  }
}

// The note editor's DOM as QTextDocument blocks of formatted runs: one block
// per paragraph, runs carrying point size, weight, slant, decoration, colour and
// script alignment. <br> is a run of one character, as Qt's line separator.
export function noteBlocks(root, spec) {
  const blocks = [];
  let block = null;
  const open = element => {
    block = {style: element?.dataset?.style ?? 'margin-top:0px; margin-bottom:0px', align: element?.getAttribute('align') ?? null, runs: []};
    blocks.push(block);
  };
  const walk = (node, format) => {
    for (const child of node.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) {
        if (!block) open(null);
        if (child.data) block.runs.push({text: child.data, format});
        continue;
      }
      if (child.nodeType !== Node.ELEMENT_NODE || child.classList.contains('note-strut')) continue;
      const tag = child.nodeName.toLowerCase();
      if (tag === 'br') {
        if (!block) open(null);
        block.runs.push({br: true});
        continue;
      }
      if (tag === 'p' || tag === 'div') {
        open(child);
        walk(child, {...format});
        block = null;
        continue;
      }
      const next = {...format}, style = child.style;
      if (child.dataset.pt) next.pt = Number(child.dataset.pt);
      // QTextCharFormat is bold above QFont::Normal (400).
      if (tag === 'b' || tag === 'strong' || Number(style.fontWeight) > 400 || style.fontWeight === 'bold') next.bold = true;
      if (style.fontWeight === 'normal' || Number(style.fontWeight) && Number(style.fontWeight) <= 400) next.bold = false;
      if (tag === 'i' || tag === 'em' || style.fontStyle === 'italic') next.italic = true;
      if (style.fontStyle === 'normal') next.italic = false;
      if (tag === 'u' || style.textDecorationLine?.includes('underline')) next.underline = true;
      if (tag === 's' || tag === 'strike' || style.textDecorationLine?.includes('line-through')) next.strike = true;
      if (child.dataset.script) next.script = child.dataset.script;
      if (tag === 'sub') next.script = 'sub';
      if (tag === 'sup') next.script = 'super';
      if (style.color) next.color = style.color;
      if (tag === 'font' && child.getAttribute('color')) next.color = child.getAttribute('color');
      walk(child, next);
    }
  };
  walk(root, {pt: spec.point_size, bold: Number(spec.weight) > 400, italic: spec.italic, script: null});
  return blocks;
}

export function noteBlocksHtml(blocks, spec) {
  const escape = text => text.replace(/[&<>]/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[char]));
  const baseBold = Number(spec.weight) > 400;
  const declarations = format => [
    format.pt !== spec.point_size && `font-size:${format.pt}pt`,
    format.bold !== baseBold && `font-weight:${format.bold ? 700 : 400}`,
    format.italic !== spec.italic && `font-style:${format.italic ? 'italic' : 'normal'}`,
    (format.underline || format.strike) && `text-decoration:${[format.underline && 'underline', format.strike && 'line-through'].filter(Boolean).join(' ')}`,
    format.script && `vertical-align:${format.script}`,
    format.color && `color:${format.color}`,
  ].filter(Boolean).join('; ');
  return blocks.map(({style, align, runs}) => {
    // A browser keeps a trailing <br> as a placeholder; Qt would add a line.
    const kept = runs.at(-1)?.br ? runs.slice(0, -1) : runs;
    const parts = [];
    for (const run of kept) {
      if (run.br) { parts.push({html: '<br>'}); continue; }
      const css = declarations(run.format), last = parts.at(-1);
      if (last && last.css === css) last.text += run.text;
      else parts.push({css, text: run.text});
    }
    const body = parts.map(part => part.html ?? (part.css ? `<span style="${part.css}">${escape(part.text)}</span>` : escape(part.text))).join('');
    return `<p style="${style.replace(/"/g, '')}"${align ? ` align="${align}"` : ''}>${body}</p>`;
  }).join('');
}

export function serializeNoteEditor(root, spec) {
  return noteBlocksHtml(noteBlocks(root, spec), spec);
}

const blockLength = block => block.runs.reduce((length, run) => length + (run.br ? 1 : run.text.length), 0);

// A DOM position as a document offset: blocks are separated by one position.
export function noteTextOffset(root, spec, node, offset) {
  const range = document.createRange();
  range.setStart(root, 0);
  range.setEnd(node, offset);
  return noteBlocks(range.cloneContents(), spec).reduce((total, block, index) => total + blockLength(block) + (index ? 1 : 0), 0);
}

export function noteTextPosition(root, offset) {
  let remaining = offset;
  for (const [index, block] of [...root.children].entries()) {
    if (index) {
      if (remaining === 0) return [block, 0];
      remaining -= 1;
    }
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let node = walker.nextNode();
    if (remaining === 0 && !node) return [block, 0];
    for (; node; node = walker.nextNode()) {
      if (node.nodeType === Node.TEXT_NODE) {
        if (remaining <= node.data.length) return [node, remaining];
        remaining -= node.data.length;
      } else if (node.nodeName === 'BR') {
        if (remaining === 0) return [node.parentNode, [...node.parentNode.childNodes].indexOf(node)];
        remaining -= 1;
      }
    }
    if (remaining === 0) return [block, block.childNodes.length];
  }
  return [root, root.childNodes.length];
}

// QTextCursor formatting over [start, end): toggles follow the format before the
// cursor end, sizes step each run, and alignment applies to touched blocks.
export function formatNoteBlocks(blocks, start, end, action, [low, high]) {
  const spans = [];
  let offset = 0;
  blocks.forEach((block, index) => {
    if (index) offset += 1;
    const from = offset;
    offset += blockLength(block);
    if (from <= end && offset >= start) spans.push(block);
  });
  if (action.align) {
    for (const block of spans) {
      block.align = action.align;
      block.style = block.style.split(';').filter(item => !/^\s*text-align\s*:/.test(item)).join(';').trim();
    }
    return;
  }
  const current = noteFormatAt(blocks, end) ?? noteFormatAt(blocks, start + 1);
  const mutate = format => {
    const next = {...format};
    if (action.delta) next.pt = Math.max(low, Math.min(high, format.pt + action.delta));
    else if (action.key === 'bold') next.bold = !current?.bold;
    else if (action.key === 'italic') next.italic = !current?.italic;
    else {
      const script = action.key === 'superscript' ? 'super' : 'sub';
      next.script = current?.script === script ? null : script;
    }
    return next;
  };
  offset = 0;
  blocks.forEach((block, index) => {
    if (index) offset += 1;
    const runs = [];
    for (const run of block.runs) {
      const length = run.br ? 1 : run.text.length, from = offset, to = offset + length;
      offset = to;
      if (run.br || to <= start || from >= end) { runs.push(run); continue; }
      const a = Math.max(start, from) - from, b = Math.min(end, to) - from;
      if (a > 0) runs.push({text: run.text.slice(0, a), format: run.format});
      runs.push({text: run.text.slice(a, b), format: mutate(run.format)});
      if (b < length) runs.push({text: run.text.slice(b), format: run.format});
    }
    block.runs = runs;
  });
}

// The format of the character before a document offset.
function noteFormatAt(blocks, position) {
  let offset = 0;
  for (const [index, block] of blocks.entries()) {
    if (index) offset += 1;
    for (const run of block.runs) {
      const length = run.br ? 1 : run.text.length;
      if (!run.br && position > offset && position <= offset + length) return run.format;
      offset += length;
    }
  }
  return null;
}

// Buttons are checked only when the whole target shares a format.
export function noteFormatState(blocks, start, end, defaultAlign) {
  const formats = [], aligns = [];
  let offset = 0;
  blocks.forEach((block, index) => {
    if (index) offset += 1;
    const from = offset;
    for (const run of block.runs) {
      const length = run.br ? 1 : run.text.length;
      if (!run.br && (start === end ? start > offset && start <= offset + length : offset < end && offset + length > start)) formats.push(run.format);
      offset += length;
    }
    if (from <= end && offset >= start) aligns.push(block.align ?? defaultAlign);
  });
  const all = test => formats.length > 0 && formats.every(test);
  return {
    bold: all(format => format.bold), italic: all(format => format.italic),
    superscript: all(format => format.script === 'super'), subscript: all(format => format.script === 'sub'),
    ...Object.fromEntries(['left', 'center', 'right'].map(name => [name, aligns.length > 0 && aligns.every(align => align === name)])),
  };
}

export function measureAtomLabels(spec, context, measureLineHeight) {
  return Object.fromEntries(spec.queries.map(({key, text, pixels}) => {
    context.font = `${pixels}px ${JSON.stringify(spec.family)}`;
    const measured = context.measureText(text);
    const capital = context.measureText('H');
    return [key, {width: measured.width, bounding_width: measured.actualBoundingBoxLeft + measured.actualBoundingBoxRight, ascent: measured.fontBoundingBoxAscent, descent: measured.fontBoundingBoxDescent, cap_height: capital.actualBoundingBoxAscent, line_height: measureLineHeight(context.font, text)}];
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

function arrowSelectionMarkup(geometry, index, style, scale) {
  // Qt strokes each native subpath separately. Keep the head/stem overlap:
  // one mask for the whole arrow would erase those intersecting boundaries.
  const subpaths = [];
  for (const command of geometry.path) {
    if (command[0] === 'M') subpaths.push([]);
    subpaths.at(-1).push(command);
  }
  const edge = style.screen_width / scale;
  return subpaths.map((commands, part) => {
    if (commands.length < 2) return '';
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const [, values] of commands) for (let i = 0; i < values.length; i += 2) {
      minX = Math.min(minX, values[i]); maxX = Math.max(maxX, values[i]);
      minY = Math.min(minY, values[i + 1]); maxY = Math.max(maxY, values[i + 1]);
    }
    const pad = (geometry.selection_width + edge) / 2;
    const bounds = `x="${number(minX - pad)}" y="${number(minY - pad)}" width="${number(maxX - minX + pad * 2)}" height="${number(maxY - minY + pad * 2)}"`;
    const path = commands.map(([command, values]) => `${command}${values.map(number).join(' ')}`).join(' ');
    const id = `arrow-selection-${index}-${part}`;
    const inner = geometry.selection_width - edge;
    return `<mask id="${id}" maskUnits="userSpaceOnUse" maskContentUnits="userSpaceOnUse" ${bounds}><g fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="${path}" stroke="white" stroke-width="${number(geometry.selection_width + edge)}"/>${inner > 0 ? `<path d="${path}" stroke="black" stroke-width="${number(inner)}"/>` : ''}</g></mask><rect ${bounds} fill="${escapeText(style.color)}" mask="url(#${id})"/>`;
  }).join('');
}

function shapeMarkup(shape, attributes) {
  if (!shape.width || !shape.height) return `<path ${attributes} d="M${number(shape.x)} ${number(shape.y)} h${number(shape.width)} v${number(shape.height)} h${number(-shape.width)} Z"/>`;
  if (shape.kind === 'ellipse') return `<ellipse ${attributes} cx="${number(shape.x + shape.width / 2)}" cy="${number(shape.y + shape.height / 2)}" rx="${number(shape.width / 2)}" ry="${number(shape.height / 2)}"/>`;
  return `<rect ${attributes} x="${number(shape.x)}" y="${number(shape.y)}" width="${number(shape.width)}" height="${number(shape.height)}" rx="${number(shape.radius)}"/>`;
}

function selectionComponentsMarkup(components, style, scale, prefix) {
  const edge = style.screen_width / (2 * scale);
  return components.map((parts, index) => {
    let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
    const bounds = (x, y, pad = 0) => {
      left = Math.min(left,x-pad); top = Math.min(top,y-pad);
      right = Math.max(right,x+pad); bottom = Math.max(bottom,y+pad);
    };
    const shapes = [];
    for (const part of parts) {
      if (part.empty) continue;
      const shape = part.shape ?? part;
      if (shape.outline) {
        const outline = shape.outline;
        bounds(outline.x,outline.y,shape.width/2);
        bounds(outline.x+outline.width,outline.y+outline.height,shape.width/2);
        const attributes = `stroke-width="${number(shape.width)}" stroke-linecap="round" stroke-linejoin="round"`;
        shapes.push(shapeMarkup(outline,`fill="black" stroke="black" ${attributes}`));
      } else if (shape.line) {
        const [x1,y1,x2,y2] = shape.line;
        bounds(x1,y1,shape.width/2); bounds(x2,y2,shape.width/2);
        shapes.push(line(x1,y1,x2,y2,`stroke="black" stroke-width="${number(shape.width)}" stroke-linecap="round"`));
      } else if (shape.rect) {
        const [x,y,w,h] = shape.rect;
        bounds(x,y); bounds(x+w,y+h);
        shapes.push(`<rect x="${number(x)}" y="${number(y)}" width="${number(w)}" height="${number(h)}" rx="${number(Math.min(w,h)/2)}"/>`);
      } else if (shape.polygon) {
        for (const [x,y] of shape.polygon) bounds(x,y,(shape.width ?? 0)/2);
        shapes.push(`<polygon points="${shape.polygon.map(p=>p.map(number).join(',')).join(' ')}" ${shape.width ? `stroke="black" stroke-width="${number(shape.width)}" stroke-linejoin="round"` : ''}/>`);
      } else if (shape.path) {
        for (const [command, coordinates] of shape.path) for (let i = 0; i < coordinates.length; i += 2) bounds(coordinates[i],coordinates[i+1],shape.width/2);
        const d = shape.path.map(([command, coordinates]) => `${command}${coordinates.map(number).join(' ')}`).join(' ');
        shapes.push(`<path d="${d}" fill="none" stroke="black" stroke-width="${number(shape.width)}" stroke-linecap="round" stroke-linejoin="round"/>`);
      } else if (shape.text) {
        const [x,y,w,h] = shape.bounds ?? [shape.text.x, shape.text.y - shape.text.pixels, shape.text.pixels, shape.text.pixels];
        bounds(x,y,shape.width); bounds(x+w,y+h,shape.width);
        shapes.push(`<text x="${number(shape.text.x)}" y="${number(shape.text.y)}" font-family="${escapeText(shape.text.family)}" font-size="${number(shape.text.pixels)}" stroke="black" stroke-width="${number(shape.width)}" stroke-linejoin="round">${escapeText(shape.text.text)}</text>`);
      } else if (shape.dots) {
        for (const [x,y] of shape.dots) {
          bounds(x,y,shape.radius);
          shapes.push(`<circle cx="${number(x)}" cy="${number(y)}" r="${number(shape.radius)}"/>`);
        }
      }
    }
    if (!shapes.length) return '';
    const id = `${prefix}-${index}`;
    return `<filter id="${id}" filterUnits="userSpaceOnUse" x="${number(left-edge*2)}" y="${number(top-edge*2)}" width="${number(right-left+edge*4)}" height="${number(bottom-top+edge*4)}"><feMorphology in="SourceAlpha" operator="dilate" radius="${number(edge)}" result="outer"/><feMorphology in="SourceAlpha" operator="erode" radius="${number(edge)}" result="inner"/><feComposite in="outer" in2="inner" operator="out" result="edge"/><feFlood flood-color="${escapeText(style.color)}"/><feComposite in2="edge" operator="in"/></filter><g fill="black" stroke="none" filter="url(#${id})">${shapes.join('')}</g>`;
  }).join('');
}

export function selectionFrameMarkup(frame, drawing, handles, scale) {
  if (!frame) return {outline:'', handle:''};
  const rects = [...frame.rects];
  const nonempty = rects.filter(rect => rect[2] || rect[3]);
  const boxes = nonempty.length ? nonempty : rects.slice(-1);
  if (!boxes.length) return {outline:'', handle:''};
  const left = Math.min(...boxes.map(r=>r[0]))-frame.padding, top = Math.min(...boxes.map(r=>r[1]))-frame.padding;
  const right = Math.max(...boxes.map(r=>r[0]+r[2]))+frame.padding, bottom = Math.max(...boxes.map(r=>r[1]+r[3]))+frame.padding;
  const x = (left+right)/2, stem = handles.rotation_stem/scale, radius = handles.size/(2*scale);
  const style = `fill="none" stroke="${escapeText(drawing.selection_style.color)}" stroke-width="${drawing.selection_style.screen_width}" vector-effect="non-scaling-stroke"`;
  return {
    outline:`<rect x="${number(left)}" y="${number(top)}" width="${number(right-left)}" height="${number(bottom-top)}" rx="${handles.frame_radius}" ${style} pointer-events="none"/>`,
    handle:`<g data-handle="${handles.rotation_type}" role="button" aria-label="Rotate selection"><path d="M${number(x)} ${number(top)} L${number(x)} ${number(top-stem)}" ${style}/><circle cx="${number(x)}" cy="${number(top-stem-radius)}" r="${number(radius)}" stroke="${escapeText(handles.color)}" fill="#ffffff" stroke-width="1.5" vector-effect="non-scaling-stroke"/></g>`,
  };
}

// The selection keys a group selects together; an ungrouped key is its own unit.
export function groupUnit(key, units = []) {
  return units.find(unit => unit.includes(key)) ?? [key];
}

// Complete every group the selection touches, as the desktop expands a selection.
export function expandToGroups(selection, units = []) {
  const expanded = new Set(selection);
  for (const unit of units) if (unit.some(key => expanded.has(key))) unit.forEach(key => expanded.add(key));
  return expanded;
}

// Dashed group boxes: the members move as a unit, unlike the solid selection frame.
export function groupBoxesMarkup(boxes = [], drawing) {
  const style = drawing.selection_style, width = style.group_screen_width;
  const dash = (style.group_dash ?? []).map(length => number(length * width)).join(' ');
  return boxes.map(box => `<rect x="${number(box.x)}" y="${number(box.y)}" width="${number(box.width)}" height="${number(box.height)}" rx="${number(box.radius)}" fill="none" stroke="${escapeText(style.color)}" stroke-width="${number(width)}" stroke-dasharray="${dash}" vector-effect="non-scaling-stroke" pointer-events="none"/>`).join('');
}

// The circle and bars of a circled charge, drawn once and reused as its hit stroke.
function circledMarkPaths(mark) {
  return `<circle r="${number(mark.radius)}"/>${line(-mark.extent,0,mark.extent,0)}${mark.kind === 'circled_plus' ? line(0,-mark.extent,0,mark.extent) : ''}`;
}

function markGlyphMarkup(mark, family) {
  if (mark.kind === 'radical') return `<circle cx="${number(mark.x)}" cy="${number(mark.y)}" r="${number(mark.radius)}"/>`;
  if (mark.kind.startsWith('circled_')) return `<g transform="translate(${number(mark.x)} ${number(mark.y)})" stroke="${escapeText(mark.color)}" stroke-width="${number(mark.stroke)}" stroke-linecap="round" fill="none">${circledMarkPaths(mark)}</g>`;
  return mark.runs.map(run => `<text x="${number(run.x)}" y="${number(run.y)}" font-family="${escapeText(family)}" font-size="${number(run.pixels)}">${escapeText(run.text)}</text>`).join('');
}

// Python's round(), which the desktop painter's step count uses: halves to even.
const roundHalfEven = value => {
  const floor = Math.floor(value), rest = value - floor;
  return rest > 0.5 || (rest === 0.5 && floor % 2) ? floor + 1 : floor;
};

// The scene rect of an atom's visible item, as the desktop's valence feedback
// reads it: a label's selection rect (AtomLabelItem.boundingRect), or a hidden
// carbon's transparent dot, whose hit padding reaches the pick radius. A label
// not measured yet has none, so nothing is drawn rather than guessed.
export function valenceWarningBounds(document, drawing, id) {
  const atom = document.state.model.atoms[id];
  if (!atom || drawing.needs_measurements) return null;
  const rect = drawing.atom_selection_rects?.[id];
  if (rect) return [...rect];
  if (drawing.atom_labels?.[id] !== undefined) return null;
  const pick = drawing.atom_hit_radii?.[id];
  if (pick === undefined || pick === null) return [atom.x - 3, atom.y - 3, 6, 6];
  const radius = Math.max(pick, 0.6, drawing.line_width * 0.6);
  return [atom.x - radius, atom.y - radius, 2 * radius, 2 * radius];
}

// The desktop's valence feedback at screen size, like its painter: the item
// rect widened by 3 px, lowered by 3 px, then a 2 px zigzag along its bottom,
// drawn with a 1 px pen. As the painter draws only items meeting the exposed
// area, an item outside the visible scene rect draws nothing, and a zigzag
// keeps only its steps over the visible width and one beyond each edge, counted
// from the item's own left edge so panning never shifts them. One call draws at
// most MAX_WARNING_POINTS points, and warnings after that in the given atom
// order are left out until fewer are in view. A scale or view that is not
// finite and non-empty draws nothing, nor does an atom whose rect or points are
// not finite or whose steps cannot be counted exactly. The caller's layer takes
// no pointer input.
const MAX_WARNING_POINTS = 50000;
export function valenceWarningMarkup(document, ids, drawing, style, scale, viewport) {
  if (!style || !Number.isFinite(scale) || scale <= 0 || !Array.isArray(viewport) || viewport.length !== 4) return '';
  const [viewX, viewY, viewWidth, viewHeight] = viewport, viewRight = viewX + viewWidth, viewBottom = viewY + viewHeight;
  if (![viewX, viewY, viewRight, viewBottom].every(Number.isFinite) || !(viewWidth > 0 && viewHeight > 0)) return '';
  const paths = [];
  let budget = MAX_WARNING_POINTS;
  for (const id of ids ?? []) {
    const rect = valenceWarningBounds(document, drawing, id);
    if (!rect?.every(Number.isFinite) || rect[2] < 0 || rect[3] < 0) continue;
    const [x, y, width, height] = rect;
    if (!(x < viewRight && x + width > viewX && y < viewBottom && y + height > viewY)) continue;
    const left = x - 3 / scale, bottom = y + height + 3 / scale, span = Math.max(4, roundHalfEven(width * scale + 6));
    // Even steps from the item's left edge, the first and last just past the view.
    const first = Math.max(0, 2 * Math.floor((viewX - left) * scale / 2) - 2);
    const last = Math.min(span, 2 * Math.ceil((viewRight - left) * scale / 2) + 2);
    if (![left, bottom, bottom + 2 / scale, left + last / scale].every(Number.isFinite) || !(first <= last && last <= Number.MAX_SAFE_INTEGER)) continue;
    const count = Math.floor((last - first) / 2) + 1;
    if (count > budget) break;
    budget -= count;
    const points = [];
    for (let step = first; step <= last; step += 2) points.push(`${step === first ? 'M' : 'L'}${number(left + step / scale)} ${number(bottom + (step % 4 ? 2 : 0) / scale)}`);
    paths.push(`<path data-valence-warning="${id}" d="${points.join(' ')}" fill="none" stroke="${escapeText(style.color)}" stroke-width="1" stroke-linecap="square" stroke-linejoin="bevel" vector-effect="non-scaling-stroke"/>`);
  }
  return paths.join('');
}

export function sceneMarkup(document, {selection = new Set(), components = [], preview = null, drawing, handleTarget = null, handleStyle = null, scale = 1, showMarkOwners = true, markPreview = null, markHoverStyle = null, imageUrl = () => null, overlays = true} = {}) {
  const state = document.state;
  const atoms = {...state.model.atoms};
  let parts = [];
  const layers = [];
  const arrowOutlines = [];
  const finishLayer = (z, order = 0) => { layers.push({z, order, html: parts.join('')}); parts = []; };
  (drawing.images ?? []).forEach((image, index) => {
    // Pixels arrive by reference; the box stays pickable while they load.
    const url = imageUrl(image.ref);
    parts.push(`<g data-item="image:${index}" opacity="${number(image.opacity)}">${url ? `<image href="${escapeText(url)}" x="${number(image.x)}" y="${number(image.y)}" width="${number(image.width)}" height="${number(image.height)}" preserveAspectRatio="none"/>` : ''}<rect x="${number(image.x)}" y="${number(image.y)}" width="${number(image.width)}" height="${number(image.height)}" fill="transparent" pointer-events="all"/></g>`);
    finishLayer(image.z, 0);
  });
  (drawing.shapes ?? []).forEach((shape, index) => {
    const key = `shape:${index}`;
    const guide = preview?.kind === 'shape' && index === drawing.shapes.length - 1;
    const stroke = guide && shape.stroke === 'none' ? 'dashed' : shape.stroke;
    const color = guide ? '#787878' : shape.color;
    const attributes = `data-item="${key}" fill="${escapeText(shape.fill ?? 'transparent')}" fill-opacity="${number(shape.alpha ?? 1)}" stroke="${stroke === 'none' ? 'none' : escapeText(color)}" stroke-width="${number(shape.line_width)}" stroke-linecap="round" stroke-linejoin="round" pointer-events="all"${guide ? ' stroke-opacity="0.7059"' : ''}${stroke === 'dashed' ? ` stroke-dasharray="${number(shape.line_width * 4)} ${number(shape.line_width * 2)}"` : stroke === 'dotted' ? ` stroke-dasharray="${number(shape.line_width)} ${number(shape.line_width * 2)}"` : ''}`;
    parts.push(shapeMarkup(shape, attributes));
    finishLayer(shape.z ?? -10, 1);
  });
  for (const [index, ring] of (state.ring_fills ?? []).entries()) {
    parts.push(`<polygon data-item="ring:${index}" points="${ring.points.map(p => p.map(number).join(',')).join(' ')}" fill="${escapeText(ring.color ?? 'transparent')}" fill-opacity="${number(ring.alpha)}" pointer-events="all"/>`);
  }
  finishLayer(-5);
  state.model.bonds.forEach((bond, index) => {
    if (!bond) return;
    const key = `bond:${index}`;
    parts.push(`<g data-item="${key}" fill="none" stroke="${escapeText(bond.color)}" stroke-width="${drawing.line_width}" stroke-linecap="round">`);
    parts.push(`<title>Bond ${bond.a}–${bond.b}, ${escapeText(bond.style)}</title>`);
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
    const key = `atom:${id}`;
    parts.push(`<g data-item="${key}">`);
    parts.push(`<title>Atom ${id}: ${escapeText(atom.element)}</title>`);
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
  for (const mark of drawing.marks ?? []) {
    parts.push(`<g data-mark="${mark.id}" data-item="mark:${mark.id}" fill="${escapeText(mark.color)}" pointer-events="none">`);
    const owner = drawing.mark_owners?.[mark.id];
    // Qt shows the ownership guidance only on a selected mark's owner guide.
    const guided = showMarkOwners && selection.has(`mark:${mark.id}`) && owner?.tooltip;
    if (owner) parts.push(`<title>${escapeText(guided ? owner.tooltip : owner.text)}</title>`);
    parts.push(markGlyphMarkup(mark, drawing.label_measurements.family));
    if (mark.kind.startsWith('circled_')) {
      const width = Math.max(mark.stroke, (mark.hit_radius - mark.radius) * 2);
      parts.push(`<g transform="translate(${number(mark.x)} ${number(mark.y)})" stroke="transparent" stroke-width="${number(width)}" stroke-linecap="round" fill="none" pointer-events="stroke">${circledMarkPaths(mark)}</g>`);
    } else {
      const radius = Math.max(mark.hit_radius, mark.radius ?? 0);
      parts.push(`<circle cx="${number(mark.x)}" cy="${number(mark.y)}" r="${number(radius)}" fill="transparent" pointer-events="all"/>`);
      if (mark.hit_rect) {
        const [x,y,w,h] = mark.hit_rect;
        parts.push(`<rect x="${number(x)}" y="${number(y)}" width="${number(w)}" height="${number(h)}" fill="transparent" pointer-events="all"/>`);
      }
    }
    parts.push('</g>');
  }
  finishLayer(0);
  if (markPreview && markHoverStyle) {
    const rgba = ([r,g,b,a]) => `rgba(${r},${g},${b},${a/255})`;
    const color = rgba(markHoverStyle.color);
    parts.push(`<g data-mark-preview="true" fill="${color}" opacity="${number(markHoverStyle.opacity)}" pointer-events="none">${markGlyphMarkup({...markPreview.mark,color},drawing.label_measurements.family)}</g>`);
    finishLayer(markHoverStyle.z);
    if (markPreview.atom) {
      const [x,y,r] = markPreview.atom;
      parts.push(`<circle data-mark-hover-owner="${markPreview.owner}" cx="${number(x)}" cy="${number(y)}" r="${number(r)}" stroke="${rgba(markHoverStyle.pen)}" fill="${rgba(markHoverStyle.brush)}" stroke-width="1" pointer-events="none"/>`);
      finishLayer(markHoverStyle.atom_z);
    }
  }

  state.arrows.forEach((arrow, index) => {
    const geometry = drawing.arrows[index], color = escapeText(geometry.color);
    const path = geometry.path.map(([command, coordinates]) => `${command}${coordinates.map(number).join(' ')}`).join(' ');
    parts.push(`<g data-item="arrow:${index}" stroke="${color}" stroke-width="${number(geometry.width)}" stroke-linecap="${geometry.cap}" stroke-linejoin="${geometry.join}" fill="none">`);
    if (selection.has(`arrow:${index}`)) arrowOutlines.push(arrowSelectionMarkup(geometry, index, drawing.selection_style, scale));
    parts.push(`<path d="${path}"${geometry.dashed ? ` stroke-dasharray="${number(geometry.width * 4)} ${number(geometry.width * 2)}"` : ''}/>`);
    parts.push(`<path d="${path}" stroke="transparent" pointer-events="stroke"/>`);
    parts.push('</g>');
  });
  for (const label of drawing.arrow_labels ?? []) {
    parts.push(`<foreignObject data-item="arrow:${label.id}" x="${number(label.x)}" y="${number(label.y)}" width="${number(label.width)}" height="${number(label.height)}"><div xmlns="http://www.w3.org/1999/xhtml" class="arrow-label" data-arrow-label="${label.id}:${label.side}">${label.html}</div></foreignObject>`);
  }
  finishLayer(0);
  for (const note of drawing.notes ?? []) {
    // A QGraphicsTextItem rotates about its position; its box is a child item.
    parts.push(`<g data-item="note:${note.id}" transform="rotate(${number(note.rotation)} ${number(note.x)} ${number(note.y)})">`);
    const box = drawing.note_box;
    if (box) parts.push(`<rect x="${number(note.x - box.padding)}" y="${number(note.y - box.padding)}" width="${number(note.width + box.padding * 2)}" height="${number(note.height + box.padding * 2)}" fill="${box.fill ? escapeText(box.fill) : 'none'}" stroke="${box.stroke ? escapeText(box.stroke) : 'none'}" stroke-width="${number(box.width)}" stroke-linejoin="bevel" pointer-events="none"/>`);
    parts.push(`<foreignObject x="${number(note.x)}" y="${number(note.y)}" width="${number(note.width)}" height="${number(note.height)}"><div xmlns="http://www.w3.org/1999/xhtml" class="note-text" data-note-text="${note.id}">${note.html}</div></foreignObject>`);
    if (selection.has(`note:${note.id}`)) {
      // The note's own padded selection box, a fixed-width screen stroke.
      const pad = drawing.note_padding;
      parts.push(`<rect data-note-selection="${note.id}" x="${number(note.x - pad)}" y="${number(note.y - pad)}" width="${number(note.width + pad * 2)}" height="${number(note.height + pad * 2)}" fill="none" stroke="${escapeText(drawing.selection_style.color)}" stroke-width="${number(drawing.selection_style.screen_width / scale)}" stroke-linejoin="round" pointer-events="none"/>`);
    }
    parts.push('</g>');
  }
  finishLayer(0);
  // Qt populates brackets after arrows and before orbitals at the same depth.
  for (const [index, bracket] of (drawing.brackets ?? []).entries()) {
    // A dragged bracket previews in the native translucent grey.
    const color = preview?.kind === 'ts_bracket' && index === drawing.brackets.length - 1 ? 'rgba(120,120,120,0.549)' : escapeText(bracket.color);
    parts.push(`<g data-item="ts_bracket:${index}"><title>Bracket ${escapeText(bracket.kind)}</title>`);
    if (bracket.symbol) {
      const symbol = bracket.symbol;
      parts.push(`<text x="${number(symbol.x)}" y="${number(symbol.y)}" font-family="${escapeText(symbol.family)}" font-size="${number(symbol.pixels)}" fill="${color}" pointer-events="none">${escapeText(symbol.text)}</text>`);
      if (bracket.bounds) {
        const [x,y,w,h] = bracket.bounds;
        parts.push(`<rect x="${number(x)}" y="${number(y)}" width="${number(w)}" height="${number(h)}" fill="transparent" pointer-events="all"/>`);
      }
    } else {
      const path = bracket.path.map(([command, coordinates]) => `${command}${coordinates.map(number).join(' ')}`).join(' ');
      parts.push(`<path d="${path}" fill="none" stroke="${color}" stroke-width="${number(bracket.width)}" stroke-linecap="butt" stroke-linejoin="miter"/>`);
    }
    parts.push('</g>');
  }
  finishLayer(0);
  for (const [index, orbital] of (drawing.orbitals ?? []).entries()) {
    const [cx,cy] = orbital.center;
    parts.push(`<g data-item="orbital:${index}" transform="translate(${number(cx)} ${number(cy)}) rotate(${number(orbital.rotation)}) scale(${number(orbital.scale)}) translate(${number(-cx)} ${number(-cy)})" stroke="${escapeText(orbital.color)}" stroke-width="${number(orbital.width)}" stroke-linecap="round" stroke-linejoin="round" fill="none">`);
    parts.push(`<title>Orbital ${escapeText(orbital.kind)}</title>`);
    const [left,top,width,height] = orbital.hit_rect;
    parts.push(`<rect x="${number(left)}" y="${number(top)}" width="${number(width)}" height="${number(height)}" fill="transparent" stroke="none" pointer-events="all"/>`);
    for (const [x,y,width,height,positive] of orbital.ellipses) {
      parts.push(`<ellipse cx="${number(x+width/2)}" cy="${number(y+height/2)}" rx="${number(width/2)}" ry="${number(height/2)}" fill="${orbital.phase ? escapeText(positive ? orbital.positive : orbital.negative) : 'none'}" fill-opacity="${number(orbital.alpha)}"/>`);
    }
    if (orbital.node) parts.push(line(...orbital.node));
    parts.push('</g>');
  }
  finishLayer(0);
  if (arrowOutlines.length) parts.push(`<g pointer-events="none">${arrowOutlines.join('')}</g>`);
  if (components.length) parts.push(`<g pointer-events="none">${selectionComponentsMarkup(components, drawing.selection_style, scale, 'molecule-selection')}</g>`);
  const shapeComponents = (drawing.shapes ?? []).flatMap((shape,index) => selection.has(`shape:${index}`) ? [[shape.selection]] : []);
  if (shapeComponents.length) parts.push(`<g pointer-events="none">${selectionComponentsMarkup(shapeComponents, drawing.selection_style, scale, 'shape-selection')}</g>`);
  if (showMarkOwners) for (const [id, owner] of Object.entries(drawing.mark_owners ?? {})) {
    if (!selection.has(`mark:${id}`) || !owner.rect) continue;
    const [x,y,w,h] = owner.rect, width = drawing.selection_style.screen_width;
    parts.push(`<g data-mark-owner="${id}" fill="none" stroke="${escapeText(owner.color)}" stroke-width="${number(width)}" stroke-linecap="square" stroke-linejoin="round" stroke-dasharray="${number(width*4)} ${number(width*2)}" pointer-events="none"><ellipse cx="${number(x+w/2)}" cy="${number(y+h/2)}" rx="${number(w/2)}" ry="${number(h/2)}" vector-effect="non-scaling-stroke"/>${line(...owner.line, 'vector-effect="non-scaling-stroke"')}</g>`);
  }
  finishLayer(19);
  // A selected image's dashed box, like the desktop's group outline.
  (drawing.images ?? []).forEach((image, index) => { if (selection.has(`image:${index}`)) parts.push(groupBoxesMarkup([image.selection], drawing)); });
  if (overlays) parts.push('<g id="selection-frame"></g>');
  finishLayer(20);
  const [handleKind, handleId] = handleTarget?.split(':') ?? [];
  if (preview?.kind === 'line') parts.push(line(preview.start.x, preview.start.y, preview.end.x, preview.end.y, 'stroke="#0d9488" stroke-width="1.5" stroke-dasharray="3 2" pointer-events="none"'));
  const collection = {arrow: 'arrows', shape: 'shapes', orbital: 'orbitals'}[handleKind];
  const handleOwner = collection && handleStyle ? drawing[collection][handleId] : null;
  for (const {handle, point, snapped} of handleOwner?.handles ?? []) {
    const size = ['shape_n', 'shape_e', 'shape_s', 'shape_w'].includes(handle) ? handleStyle.edge_size : handleStyle.size;
    parts.push(`<circle data-handle="${handle}" data-${handleKind}-id="${handleId}" cx="${number(point[0])}" cy="${number(point[1])}" r="${number(size / (2 * scale))}" fill="${snapped ? escapeText(handleStyle.color) : '#ffffff'}" stroke="${escapeText(handleStyle.color)}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`);
  }
  if (preview?.kind === 'marquee') {
    const {start, end} = preview;
    parts.push(`<rect x="${number(Math.min(start.x, end.x))}" y="${number(Math.min(start.y, end.y))}" width="${number(Math.abs(end.x - start.x))}" height="${number(Math.abs(end.y - start.y))}" fill="Highlight" fill-opacity="0.12" stroke="Highlight" stroke-width="1" vector-effect="non-scaling-stroke" pointer-events="none"/>`);
  }
  if (overlays) parts.push('<g id="rotation-handle"></g>');
  finishLayer(30);
  return layers.sort((a, b) => a.z - b.z || a.order - b.order).map(layer => layer.html).join('');
}

// Display only the inserted part of a server candidate. Geometry and chemistry
// still come from the existing renderer; the committed scene is never replaced.
// One group opacity composites overlaps once, as the native preview picture does.
export function smilesPreviewMarkup(candidate, committed, opacity) {
  const source = candidate.document.state, original = committed.state;
  const state = {...source, model: {...source.model,
    atoms: Object.fromEntries(Object.entries(source.model.atoms).filter(([id]) => !Object.hasOwn(original.model.atoms, id))),
    bonds: source.model.bonds.map((bond, index) => index < original.model.bonds.length ? null : bond),
  }, arrows: [], ring_fills: []};
  const drawing = {...candidate.drawing, images: [], shapes: [], arrows: [], arrow_labels: [], notes: [], orbitals: [], brackets: [],
    marks: (candidate.drawing.marks ?? []).filter(mark => mark.id >= (original.marks ?? []).length)};
  return `<g opacity="${number(opacity)}">${sceneMarkup({...candidate.document, state}, {drawing, overlays: false, showMarkOwners: false})}</g>`;
}

// QGraphicsView's rubber band intersects item shapes; SVG owns the same
// operation on the materialized native geometry, including transparent targets.
// Targets the server's selection_buckets accepts; other SVG children only draw.
export function itemKey(element) {
  const key = element.closest('[data-item]')?.dataset.item;
  return key && /^(atom|bond|arrow|shape|ring|mark|orbital|ts_bracket|note|image):/.test(key) ? key : null;
}

export function marqueeSelection(svg, start, end, initial = [], additive = false) {
  // Firefox does not implement this SVG operation. Distinguish unsupported
  // geometry from an empty result so the caller can keep the prior selection.
  if (typeof svg.getIntersectionList !== 'function') return null;
  const matrix = svg.getCTM();
  const first = {x: matrix.a * start.x + matrix.c * start.y + matrix.e, y: matrix.b * start.x + matrix.d * start.y + matrix.f};
  const last = {x: matrix.a * end.x + matrix.c * end.y + matrix.e, y: matrix.b * end.x + matrix.d * end.y + matrix.f};
  const rect = svg.createSVGRect();
  rect.x = Math.min(first.x, last.x); rect.y = Math.min(first.y, last.y);
  rect.width = Math.abs(last.x - first.x); rect.height = Math.abs(last.y - first.y);
  const selected = new Set(additive ? initial : []);
  if (rect.width && rect.height) {
    for (const element of svg.getIntersectionList(rect, svg.querySelector('#drawing'))) {
      const key = itemKey(element);
      if (key) selected.add(key);
    }
  }
  return selected;
}

// SVG viewBox is the browser representation of the native view transform.
export function clampView(view, viewport, rect) {
  if (!rect || !viewport.width || !viewport.height) return view;
  const scale = Math.min(viewport.width / view.width, viewport.height / view.height);
  const width = viewport.width / scale, height = viewport.height / scale;
  const result = {x:view.x-(width-view.width)/2, y:view.y-(height-view.height)/2, width, height};
  for (const [axis, size, offset] of [['x','width',0],['y','height',1]]) {
    const minimum = rect[offset], extent = rect[offset+2];
    result[axis] = extent < result[size]
      ? minimum + (extent-result[size])/2
      : Math.max(minimum, Math.min(minimum+extent-result[size], result[axis]));
  }
  return result;
}

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


export function gridMarkup(sheet, grid, spec, bondLength, scale) {
  const step = bondLength * spec.step;
  if (!grid.enabled || step * scale < spec.minimum_spacing) return '';
  const tile = spec.tiles[grid.style];
  const lines = tile.lines.map(([x1,y1,x2,y2]) => `<line x1="${x1*step}" y1="${y1*step}" x2="${x2*step}" y2="${y2*step}"/>`).join('');
  return `<defs><pattern id="sheet-grid-pattern" patternUnits="userSpaceOnUse" x="0" y="0" width="${tile.size[0]*step}" height="${tile.size[1]*step}"><g stroke="${spec.color}" stroke-opacity="${grid.opacity}" stroke-width="${1/scale}" stroke-linecap="round">${lines}</g></pattern></defs><rect x="${-sheet[0]/2}" y="${-sheet[1]/2}" width="${sheet[0]}" height="${sheet[1]}" fill="url(#sheet-grid-pattern)"/>`;
}
