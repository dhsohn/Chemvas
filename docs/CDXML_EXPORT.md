# CDXML Export

[한국어](CDXML_EXPORT.ko.md)

Chemvas exports editable CDXML (ChemDraw XML) through File > Export Figure
(`.cdxml` format) and the CLI `render-document --output file.cdxml`.

**This output is not verified in ChemDraw.** CDXML import is not supported;
the `.chemvas` format remains the document truth.

## Supported

| Area   | What is emitted                                          |
|--------|----------------------------------------------------------|
| Atoms  | Pure elements (periodic table), colour, explicit C, Charge annotation |
| Bonds  | single/1, double_center/2, triple/3                      |
| Lines  | Headless solid lines, endpoint-order BoundingBox         |
| Arrows | Arrow as grouped line components (shaft + head), M/L path commands only |
| Shapes | rect, circle; stroke-only, fill-only, or same colour    |
| Notes  | Per-line `<t>` with per-run resolved font family, size, bold face, colour |

## Refused (with error before any file is written)

| Area     | What is refused                                         |
|----------|---------------------------------------------------------|
| Atoms    | Aliases (incl. Ac/Ts), radicals, scene marks; hidden atoms are excluded and bonds to them are refused |
| Bonds    | Wedge, hash, bold, dotted, double_either, ring-side; mismatched style/order |
| Lines    | Dashed, wavy, bold; mirrored                            |
| Arrows   | Curved, double, other kinds, labels, mirrored           |
| Shapes   | Ellipse, rounded_rect, dashed/dotted stroke, translucent fill, mixed colours |
| Notes    | Italic, underline (all styles including dash/dot/wave), overline, strikeout, sub/superscript, non-mixed-case capitalization (uppercase, small caps), custom word spacing, non-default font stretch, lists, tables, rotation, non-400/700 weights, non-left alignment, boxes/borders, glyph fallback fonts (including CJK/emoji when the primary font cannot render them) |
| Stacking | Fragment layer interleaving, overlapping interleaved fragments. Under default z-values, any note, line, or arrow whose bounding rect touches a bonded molecule's items is refused, as are two bonded molecules with touching item bounds (pick halos included) |
| Other    | Ring fills, brackets, images, orbitals, perspective, groups, empty pages |

## Scale

One uniform scale `s = out_w_pt / source_w` applies to all coordinates,
font sizes, line widths, and geometry. When no `--width-mm` is given, the
CLI sizes by bond length (no fixed page width); the GUI custom-width
default is 84 mm. Use `--width-mm 170` for a 170 mm page.
Numeric precision is 12 significant digits.

## Font handling

Font family is the actual resolved font (`QFontInfo`), not the requested
name. If any glyph in a text run falls back to a different font (detected
via `QTextLayout.glyphRuns()`), export refuses with an error naming the
fallback font and the primary font.

## GUI and CLI

- **GUI**: File > Export Figure > CDXML format. The dialog label reads
  "CDXML - ChemDraw XML (not verified in ChemDraw)".
- **CLI**: `chemvas render-document doc.chemvas --output out.cdxml`
  (also accepts `--width-mm`, `--background`). `--min-font-pt` is not
  supported for CDXML output.

## Source format

The `.chemvas` source document is never modified by export. CDXML import
is refused; there is no round-trip.

## Limitations

- Grouped arrows and shapes are exported as CDXML graphics, not as native
  ChemDraw reaction tools.
- No consumer interoperability verification has been performed.
- The DTD is not included and DTD validity is not claimed.
- Font charset, U+2028 soft breaks, tab characters, round caps/joins,
  hydrogen inference, and `CaptionLineHeight` are emitted but their
  consumer behaviour is unproved.
