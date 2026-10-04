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
| Bonds  | single/1, double_center/2 (`Center`), side-placed double/2 (`Left`/`Right` chosen from drawn lines, including benzene and ring doubles), triple/3, legacy order-2/3 bonds stored with single style, wedge/1 (`WedgeBegin`), hash/1 (`WedgedHashBegin`) with narrow end at begin atom |
| Lines  | Headless solid lines, endpoint-order BoundingBox         |
| Arrows | Arrow as grouped line components (shaft + head), M/L path commands only |
| Shapes | rect, circle; stroke-only, fill-only, or same colour    |
| Notes  | Per-line `<t>` with per-run resolved font family, size, bold face, colour |
| Other  | Unpainted ring records (transparent default fill without stroke) are ignored so rings export |

## Refused (with error before any file is written)

| Area     | What is refused                                         |
|----------|---------------------------------------------------------|
| Atoms    | Aliases (incl. Ac/Ts), radicals, scene marks; hidden atoms are excluded and bonds to them are refused |
| Bonds    | Bold, dotted, double_outer, double_either; bonds where drawn side line or narrow begin orientation cannot be confirmed; mismatched style/order |
| Lines    | Dashed, wavy, bold; mirrored                            |
| Arrows   | Curved, double, other kinds, labels, mirrored           |
| Shapes   | Ellipse, rounded_rect, dashed/dotted stroke, translucent fill, mixed colours |
| Notes    | Italic, underline (all styles including dash/dot/wave), overline, strikeout, sub/superscript, non-mixed-case capitalization (uppercase, small caps), custom word spacing, non-default font stretch, lists, tables, rotation, non-400/700 weights, non-left alignment, boxes/borders, glyph fallback fonts (including CJK/emoji when the primary font cannot render them) |
| Stacking | Fragment layer interleaving, overlapping interleaved fragments. Under default z-values, any note, line, or arrow whose bounding rect touches a bonded molecule's items is refused, as are two bonded molecules with touching item bounds (pick halos included) |
| Other    | Visible ring fills (stroke or fill with alpha > 0), brackets, images, orbitals, perspective, groups, empty pages |

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

The `.chemvas` source document is never modified by export. Preflight checks
run before output is written, preserving existing destination files on error.
CDXML import is not supported; `.chemvas` remains the editable source document,
and CLI export is not a roundtrip.

## Limitations

- Double bond side convention: `DoublePosition` is emitted as `Left` or `Right`
  viewed from atom B to atom E, derived from drawn line offsets, matching the
  public specification mirror ([ChemApps CDXML reference](https://chemapps.stolaf.edu/iupac/cdx/sdk/IntroCDXML.htm),
  which defines `Right` as placing the secondary line to the right when looking
  from B to E). Physical consumer appearance and ChemDraw visual rendering
  remain unverified.
- Chemical consumers: targeted tests check RDKit's interpretation of the molecular
  graph, formal charges, and wedge/hash stereochemistry from exported CDXML;
  the RDKit parser ignores
  `DoublePosition`. ChemDraw visual equivalence is not verified.
- Grouped arrows and shapes are exported as CDXML graphics, not as native
  ChemDraw reaction tools.
- No full CDXML compatibility, DTD validity, full roundtrip/import, or broad
  consumer interoperability is claimed.
- The DTD is not included and DTD validity is not claimed.
- Font charset, U+2028 soft breaks, tab characters, round caps/joins,
  hydrogen inference, and `CaptionLineHeight` are emitted but their
  consumer behaviour is unproved.
