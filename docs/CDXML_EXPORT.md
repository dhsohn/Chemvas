# CDXML Export

[한국어](CDXML_EXPORT.ko.md)

Chemvas exports editable CDXML (ChemDraw XML) through File > Export Figure
(`.cdxml` format) and the CLI `render-document --output file.cdxml`.

ChemDraw checks are bounded to the cases described below; they do not establish
whole-document visual equivalence. CDXML import is not supported;
the `.chemvas` format remains the document truth.

## Supported

| Area   | What is emitted                                          |
|--------|----------------------------------------------------------|
| Atoms  | Pure elements (periodic table), colour, explicit C, Charge annotation; the group labels `Me`, `Ph`, `tBu` as `Nickname` nodes with their full internal graph (see Atom labels) |
| Bonds  | single/1, double_center/2 (`Center`), side-placed double/2 and double_outer/2 (`Left`/`Right` chosen from drawn lines, including benzene and ring doubles), triple/3, legacy order-2/3 bonds stored with single style, wedge/1 (`WedgeBegin`), hash/1 (`WedgedHashBegin`) with narrow end at begin atom; bold_in/1 and bold_out/1 (`Bold`, see Native bold bonds) |
| Lines  | Headless solid, bold and dashed lines (`LineType="Dashed"`, consumer dash pattern), endpoint-order BoundingBox |
| Arrows | Arrow as grouped line components (shaft + head), M/L path commands only |
| TS brackets | `square_pair`, `square_left` as grouped unheaded arrows on the drawn M/L vertices; `dagger`, `double_dagger` as one `<t>` with the exact glyph (see Dashed lines and TS brackets) |
| Shapes | rect, circle; stroke-only, fill-only, or same colour    |
| Notes  | Per-line `<t>` with per-run resolved font family, size, bold face, colour; script lines use positioned sub/superscript runs |
| Other  | Unpainted ring records (transparent default fill without stroke) are ignored so rings export |

## Refused (with error before any file is written)

| Area     | What is refused                                         |
|----------|---------------------------------------------------------|
| Atoms    | Other aliases (incl. Ac/Ts, `t-Bu`, `Et`, `OMe`), identifier hydrogens such as `Hᵃ` without a typed binding, fixed-fragment group labels without exactly one plain single attachment, generic aryl with unsupported connections, or labels with a charge/radical, radicals, unsupported or standalone scene marks; hidden atoms are excluded and bonds to them are refused |
| Bonds    | bold_center, non-single bold, chemical dotted with an order other than the exact integer 1, double_either; bonds where drawn side line or narrow begin orientation cannot be confirmed; mismatched style/order |
| Lines    | Wavy; mirrored                                    |
| TS brackets | Parentheses, braces; transformed, translucent or outlined items; items not painting their record; dagger glyph fallback |
| Arrows   | Curved, double, other kinds, labels, mirrored           |
| Shapes   | Ellipse, rounded_rect, dashed/dotted stroke, translucent fill, mixed colours |
| Notes    | Italic, underline (all styles including dash/dot/wave), overline, strikeout, unsupported vertical alignment, non-mixed-case capitalization (uppercase, small caps), custom word spacing, non-default font stretch, lists, tables, non-conformal or projective transforms, non-400/700 weights, non-left alignment, boxes/borders, unavailable glyph outlines, ambiguous mixed-font clusters or surrogate mappings |
| Stacking | Overlapping interleaved fragment ink; actual note/fragment ink contact across fragment layers; line, arrow or dagger TS bracket bounding contact; square-bracket stroke contact that reverses paint order; unproved child-mark ink overlap; atom/bond scene items split by another atom/bond; INT16 drawable `Z` overflow (32767) |
| Other    | Visible ring fills (stroke or fill with alpha > 0), images, orbitals, perspective, groups, empty pages |

## Atom labels

A label is exported with chemistry only when its meaning is typed; the label
text, colour, neighbours and legends are never used to guess it. The drawn
label text, resolved font family, colour and painted baseline are retained.
Sizes use the nearest native twentieth point (at most 0.025 pt encoding error).
Leading/trailing facing-glyph anchors use explicit Left/Right justification;
see ADR 0048. Native baseline and font-face differences remain possible.

- **Pure element symbols** become `<n Element=Z>` as before.
- **`Me`, `Ph`, `tBu`** become `NodeType="Nickname"` nodes. Each holds an
  inner `<fragment>` with the group's carbons (`NumHydrogens` 3 for methyl,
  Kekulé phenyl with one ipso carbon, tert-butyl with a central carbon and
  three methyls) and one `ExternalConnectionPoint` placed on the outside
  neighbour. The outside bond keeps its native `B`/`E` order and ends on the
  nickname node. The group needs exactly one ordinary single attachment; zero
  or several attachments, a double/triple/wedge/hash attachment, and a charge
  or radical annotation on the group are refused. Other aliases are refused.
- **Literal `Ar`** is ambiguous without a typed binding and is refused. An
  explicit `generic_aryl()` retains the visible `Ar` as a `Nickname` containing
  a native `GenericNickname="ARY"` query. Explicit `element_identity("Ar")`
  remains argon. No fixed ring or substitution pattern is inferred.
- **`H` with superscript lowercase identifier letters** (`Hᵃ`, `Hᵇ`) is
  refused unless typed: it is never read as an isotope, a charge or helium.

A caller can pass typed meanings with
`preflight_cdxml(..., label_bindings={atom_id: CdxmlLabelBinding...})` and the
same mapping to `serialize_cdxml`:

| Binding | Applies to | Emitted |
|---------|-----------|---------|
| `element_identity("Ar")` | `Ar` | `Element="18"` |
| `element_identity("H")` | `H` + superscript letters | `Element="1"`, no `Isotope`, exact label |
| `generic_aryl()` | `Ar`, zero to two existing order-1 single/wedge/hash/dotted connections | Visible `Ar` nickname; internal `ARY` query and one shared external connection point when bonded |
| `aryl_fragment("Ph")` | `Ar` with one plain single attachment | `Nickname` with the phenyl graph, label `Ar` |
| `aryl_fragment("4-F-Ph")` | `Ar` with one plain single attachment, or one order-1 wedge/hash with `Ar` at `bond.b` and an unbound elemental narrow `bond.a` | `Nickname` with a fixed para-fluorophenyl graph (`C6H4F`, F on carbon para to ipso), label `Ar`; stereo bonds use `WedgeBegin`/`WedgedHashBegin` like wide-end `Ph` |
| `aryl_label(author_note)` | `Ar` (typed API or v2 sidecar; visible in export scope) | Page `<t InterpretChemically="no">` with visible `Ar` text (label geometry from the scene), Chemvas `objecttag`s for the exact `author_note` and caption metadata (`atom_id`, unexpanded aryl, no chemical atom identity); **no** `<n>` for Ar. Refuses if Ar has any non-documentary bond in the document, including when the other endpoint is outside the export selection |

Each meaning takes exactly its own field as an exact `str` (`element` for
`element_identity`, `fragment` for `aryl_fragment`, `author_note` for
`aryl_label`, none for `generic_aryl`).
A binding with an extra or conflicting field, a missing or non-`str` value, or
an unknown meaning is refused; it is never dropped or converted.

Bindings are not stored in the `.chemvas` file. The CLI reads the explicit
sidecar; the GUI passes none, so an ambiguous `Ar` refuses there. The typed export
plan separates displayed text from chemical meaning. The `ARY` query represents
an unspecified aryl group, not a concrete molecular structure or formula.

Generic aryl at the wide end of an order-1 wedge/hash retains the stored
narrow-to-wide B/E and native WedgeBegin/WedgedHashBegin display. Eight mirrored
O/P-to-Ar controls preserve ARY, no Element=18, native endpoints and increasing
paint width after SaveAs and fresh-process reopen. The complete OMe witness
retains its 28 generic-Ar stereo connections. This does not assign absolute CIP
configuration to an unspecified aryl query or approve a fixed phenyl binding.
Concrete aryl_fragment("Ph") on wedge/hash remains refused, as do ambiguous
unbound Ar and a drawn stereo direction that contradicts stored bond.a.

`aryl_fragment` identifiers (`Ph`, `4-F-Ph`) are explicit binding names only.
Legends such as `Ar = 4-FC6H4` are not read; a literal `4-F-Ph` atom label
always refuses. Only drawn `Ar` plus `aryl_fragment("4-F-Ph")` selects the
graph. The fixed `4-F-Ph` fragment attachment contract is separate from generic aryl;
generic aryl retains the outer connections on a nickname with one shared query attachment. Ortho/meta fluorophenyl names and `MeOPh` have no
verified graph and are refused. The `4-F-Ph` graph is producer-encoded native
CDXML; ChemDraw display and chemical roundtrip are not verified.

### Label-binding sidecar (CLI)

`render-document --cdxml-label-bindings labels.json` reads a strict JSON
sidecar written by the person who drew the figure and knows what each label
means. Chemvas never writes one by itself and never guesses a meaning:

```bash
chemvas render-document doc.chemvas --output out.cdxml --cdxml-label-bindings labels.json
```

```json
{
  "format": "chemvas-cdxml-label-bindings",
  "version": 1,
  "source_sha256": "<SHA-256 of the exact .chemvas bytes>",
  "bindings": [
    {"atom_id": 1, "expected_label": "Ar", "meaning": "generic_aryl"},
    {"atom_id": 4, "expected_label": "Ar", "meaning": "aryl_fragment", "fragment": "Ph"},
    {"atom_id": 7, "expected_label": "Hᵃ", "meaning": "element", "element": "H"}
  ]
}
```

- `source_sha256` is the SHA-256 of the exact input `.chemvas` bytes. Editing
  or replacing the document changes it, and a sidecar written for other bytes
  is refused. The CLI reads the document once; the digest, the label check and
  the exported drawing all come from those same bytes.
- Each binding names one `atom_id`, the exact drawn label `expected_label`
  (compared code point by code point, no normalization) and one `meaning`:
  `element` (with `element`), `generic_aryl`, or `aryl_fragment` (with
  `fragment`). The exporter then applies the binding table above and may still
  refuse.
- Refused before any output is written: non-strict JSON (duplicate keys,
  NaN/Infinity, trailing data), a wrong `format` or `version`, unknown keys or
  meanings, wrong types (a `bool` or `1.0` is not an atom id), an empty or
  repeated binding, a digest mismatch, an atom that is missing, hidden or
  outside the export scope, a label mismatch, and any exporter refusal.
- The option is an error for SVG, PDF and PNG output. A failed export leaves
  existing files untouched, and the source document is never modified.
- The report gains `cdxml_label_bindings` with the sidecar path, its SHA-256,
  the bound source SHA-256 and the applied bindings. Version `2` sidecars also
  echo `version` and `documentary_contacts` in that report block; version `1`
  reports stay unchanged.

**Version 2 (documentary TS contacts).** Adds `documentary_contacts` and the
`aryl_label` binding. Every listed contact must match a live order-1 dotted
bond in the exported document; permitted contacts export as dashed line
graphics (not `<b>`). Other order-1 dotted bonds retain chemical `<b Order="1" Display="Dash">` encoding. Drawn
`Ar` under `aryl_label` becomes a non-chemical page caption, not a node; any
remaining chemical bond on that Ar refuses. See
[ADR 0038](adr/0038-documentary-contacts-and-aryl-labels.md) (Proposed).
ChemDraw 25.0.2.14 was observed to relabel prior node encodings as argon;
consumer display, metadata retention, and chemical roundtrip are not verified.

The sidecar does not change the `.chemvas` schema or the GUI. Bindings for a
real figure must come from its author; a test fixture's bindings say nothing
about any real `Ar` or `Hᵃ`.

## Dashed lines and TS brackets

These follow the drawn record exactly, with one uniform scale; nothing is
inferred, aligned or flattened.

- **Dashed line** (`line_dashed`): one `<arrow LineType="Dashed">` with the record's directed Tail3D/Head3D endpoints, the arrow line
  width and colour, like a solid line. CDXML `LineType` has no dash length or
  gap, so the dash pattern is drawn by the consumer and can differ from the
  Chemvas pattern; the line stays dashed. It is never split into solid pieces
  or replaced by an image.
- **Square TS bracket** (`square_pair`, `square_left`): one `<group>` of
  unheaded `arrow` elements, one per `L` command of `bracket_path_commands`, on the same
  rectangle and bond length the scene uses. Width is
  `bracket_stroke_width(bond_line_width)` times the scale and colour is the
  item's paint. The vertices are exact; the corner joins and line ends are
  drawn by the consumer (the scene strokes with flat caps and mitre joins).
- **Dagger TS bracket** (`dagger`, `double_dagger`): one `<t>` holding the
  exact † (U+2020) or ‡ (U+2021) at the `bracket_symbol_layout` baseline
  anchor, in the resolved family of the glyph font, at its pixel size times
  the scale. A glyph that needs a fallback font or has no outline is refused.
- Refused: parentheses and braces (cubic strokes), a bracket item that is
  moved, scaled, rotated, translucent or outlined, an item that no longer
  paints the path of its record, and a dagger whose glyph run or font does not
  match its kind.
- Stacking: a bracket between a bonded molecule's bonds and atom labels in
  z-order (the default z-values) is refused when it touches the bounding rect
  of any of that molecule's atom or bond items. A square bracket is compared
  by what it paints, not by its own bounding rect: the exact stroke
  rectangles (width `bracket_stroke_width(bond_line_width)`, flat ends,
  mitre-filled corners), with each free end lengthened by half the width
  because a consumer may draw square caps. So a bracket drawn around a
  structure exports when its strokes stay clear of the molecule; touching
  counts as contact. Dagger brackets, and a square bracket whose painted
  geometry cannot be fixed exactly, keep the bounding-rect rule. The
  molecule is then written as one fragment above the bracket; no painted
  area changes order because the two do not overlap.
- Z order: the CDX ZOrder property (`Z`, INT16) applies to Node, Bond, Text
  and Graphic/Arrow objects, not to Group, Fragment or Page; a missing `Z` counts
  as 0 and objects sharing 0 are ordered arbitrarily. Every `n`, `b`, `t`
  `graphic` and `arrow` (each bracket stroke and arrow segment included) therefore
  carries its own positive `Z` and no `group` or `fragment` does. Page
  objects keep their scene order and each takes one contiguous block; inside
  a molecule the atoms and bonds follow their scene paint order, a node
  directly before its contracted group and label. Exceeding 32767 is refused
  before any output is written.

## Scale

One uniform scale `s = out_w_pt / source_w` applies to all coordinates,
font sizes, line widths, and geometry. When no `--width-mm` is given, the
CLI sizes by bond length (no fixed page width); the GUI custom-width
default is 84 mm. Use `--width-mm 170` for a 170 mm page.
Numeric precision is 12 significant digits.

## Font handling

Atom labels retain their existing resolved-font and fallback guards. Notes use
font family and pixel size from the glyph runs of their painted QTextDocument.
Simple mixed-font text is split into existing `<s>` runs in original UTF-16
character order, with the same line baseline, colour and face. Mixed clusters,
surrogates, non-monotone positions, unequal baselines, incompatible faces and
unavailable glyph outlines are refused; no font installation or source text
replacement is performed.

## GUI and CLI

- **GUI**: File > Export Figure > CDXML format. The dialog label reads
  "CDXML - ChemDraw XML (not verified in ChemDraw)".
- **CLI**: `chemvas render-document doc.chemvas --output out.cdxml`
  (also accepts `--width-mm`, `--background`, and `--cdxml-label-bindings`
  for the sidecar above). `--min-font-pt` is not supported for CDXML output.

## Source format

The `.chemvas` source document is never modified by export. Preflight checks
run before output is written, preserving existing destination files on error.
CDXML import is not supported; `.chemvas` remains the editable source document,
and CLI export is not a roundtrip.

## Limitations

- Double bond side and spacing come from the drawn centerlines. The saved native
  SVG controls place positive page-normal displacement on CDXML `Left`, and the
  inverse on `Right`. Each double carries BondSpacing relative to its actual
  B-E distance, including the scene's 1.1 spacing factor. Native controls cover
  planar six-membered rings and isolated 20/40/80-unit doubles; general consumer
  appearance remains unverified.
- ChemDraw 25.0.2.14 truncates per-bond spacing percentages to tenths on save.
  The length-80 control reopens at 4.80 pt versus a 4.84 pt target; the 170 mm
  OMe drawing has at most 0.0087 pt spacing difference. Native coordinate
  serialization also rounds positions. Export does not move atoms to mask this.
- Chemical consumers: targeted tests check RDKit's interpretation of the molecular
  graph, formal charges, and wedge/hash stereochemistry from exported CDXML;
  the RDKit parser ignores
  `DoublePosition`. ChemDraw visual equivalence is not verified.
- Grouped arrows use unheaded native line primitives and shapes use graphics, not
  ChemDraw reaction tools.
- No full CDXML compatibility, DTD validity, full roundtrip/import, or broad
  consumer interoperability is claimed.
- The DTD is not included and DTD validity is not claimed.
- Nickname, GenericNickname and ExternalConnectionPoint nodes, their
  internal coordinates, `NumHydrogens`, and the exact-label `<t>` on those
  nodes follow the public CDX specification mirror. The bounded generic-aryl
  save/reopen result below is verified in ChemDraw 25.0.2.14; native group
  expansion, interactive reconnection and other consumer behavior remain unverified.
- Font charset, U+2028 soft breaks, tab characters, round caps/joins,
  hydrogen inference, and `CaptionLineHeight` are emitted but their
  consumer behaviour is unproved.

### Existing dotted chemical bonds

Native `Bond.style="dotted"` with order exactly integer 1 exports as a chemical
fragment `<b Order="1" Display="Dash">`; it keeps its endpoints and participates
in the chemical graph. Independent `Arrow.kind="line_dashed"` remains a dashed
page arrow. Only explicit documentary permissions opt a bond into the existing
nonchemical graphic contract. No native schema, clipboard, tool or bond enum is
added. For chemical dotted bonds, including literal/generic Ar connections, other
orders and mutable bool/float orders refuse in both preflight and serialization.
This exact-type claim does not cover the separate explicit documentary API.
Explicit generic aryl bindings retain zero to two supported outer connections;
three or more refuse. The nickname contains one ARY query and, when connected,
one shared ExternalConnectionPoint at the first neighbor. No specific aryl atom
or substitution site is inferred. Native ChemDraw 25.0.2.14 save/reopen retained
all 48 ARY definitions and 238 top-level bonds in the bounded OMe witness,
including its one two-contact group. No node became argon. One generic query
still reports that its molecular formula cannot be computed. A mixed witness
also checks explicit argon independently. This is native graph retention, not
manual editing, group-expansion, or downstream query-engine validation.
See [ADR 0042](adr/0042-native-generic-aryl-meaning.md).

## Note rotation

Notes preserve their painted glyph font declarations and mapped text baseline under positive
uniform affine scale and rotation. `RotationAngle` uses signed degrees multiplied
by 65536; shear, reflection, non-uniform scale and projective transforms are refused.
ChemDraw may substitute fonts: the observed Korean note retained its text and
baseline after save/reopen but its font and glyph extent changed. This mapping does
not guarantee identical glyph geometry on a consumer with different fonts.

## Atom-attached text marks

Visible atom-attached plus/minus marks preserve their source glyph, font and mapped
baseline as a node-child objecttag with a relative offset. ChemDraw 25 preserved
the displayed mark through individual atom movement, Undo/Redo and save/reopen.
The producer still emits the original node Charge; consumer re-save was observed
to omit it. No charge inference or chemical-analysis retention is promised.
Standalone marks, unsupported transforms and overlapping ink with unproved child
paint order are refused. Square-bracket interleaving uses painted ink and the
fragment's actual page rank; a contacting stroke whose order would reverse refuses.

Note and fragment overlap checks use the existing Qt painted-ink bounds, rather
than text hit-box margins; actual overlapping interleaved paint still refuses.

### Native bold bonds

The single Bold tokens (`bold_in` and `bold_out`) with order exactly integer 1 export as a
chemical `<b Order="1" Display="Bold" BoldWidth="…">`. It keeps the original
begin/end nodes, their positions and the bond colour. `BoldWidth` is the Qt
renderer’s effective stroke width, uniformly scaled with the figure. When the
renderer draws an ordinary line because the bold width is no larger than the
line width (within its 1e-6 threshold), the bond uses that line width. The
document’s existing default BoldWidth is unchanged.

Both tokens now use one centered Qt strip (ADR 0046), also for old documents.
No atom is moved and no detached graphic replaces a bond. Label clearance and
mixed junctions still require consumer comparison; isolated strip agreement is
not a claim of full-document or GUI equivalence. `bold_center`, non-single bold
orders and bold connections to generic/literal Ar remain refused.

Historical evidence before the common-renderer change:
ChemDraw 25.0.2.14 passed open/save/fresh-process reopen for synthetic default
and runtime custom-width witnesses, each with 12 nodes and six bonds. The
default witness additionally passed moving one labelled endpoint, Undo/Redo,
save and fresh-process reopen with the other 11 nodes fixed and connectivity
and effective widths preserved. Custom-width editing was not separately tested.
Saved default BoldWidth rounded from 4.75817199341 to 4.76 pt; custom BoldWidth
rounded from 7.14874683616 to 7.15 pt. Default native SVG measurement confirmed
the width but showed that the native strip is centred on the atom axis while
the source strip centre is offset by 1.29768327 pt. Exact outline equivalence
failed. These checks do not accept consumer chemical warnings or chemical
interpretation, and do not establish full-product or deployment acceptance.

## Experimental consumer-measured caption placement

The optional CLI flag `--cdxml-layout-reference layout.json` moves selected notes
using text bounds saved by a particular consumer. Export normally, open that
CDXML in the intended consumer, and save a new CDXML without editing. Version 2
binds the measurements to the exact source, uncorrected producer, label-binding
sidecar and complete export options. Version 1 is refused. Construct the strict
JSON sidecar from those actual files; the frames below illustrate the fields,
not dimensions to copy:

```json
{
  "version": 2,
  "source_sha256": "<exact .chemvas SHA-256>",
  "producer_sha256": "<uncorrected CDXML SHA-256>",
  "consumer_sha256": "<saved consumer CDXML SHA-256>",
  "consumer_file": "consumer-saved.cdxml",
  "notes": [
    0,
    1
  ],
  "export_options": {
    "format": "cdxml",
    "scope": "sheet",
    "sizing": "bond",
    "background": "white",
    "dpi": 300,
    "width_mm": 170,
    "max_height_mm": null,
    "min_font_pt": null
  },
  "label_bindings_sha256": null,
  "producer_frame": [
    0,
    0,
    481.889763779528,
    600
  ],
  "consumer_frame": [
    0,
    0,
    540,
    719.75
  ],
  "font_mapping": {
    "Arial": "Arial"
  },
  "consumer_environment": {
    "creation_program": "ChemDraw 25.0.2.14",
    "platform": "Windows",
    "executable_sha256": "<consumer executable SHA-256>"
  }
}
```

`notes` contains distinct zero-based document note indices. All lines belonging
to a selected note translate together. `label_bindings_sha256` is the digest of
the exact binding sidecar, or `null` when absent. Frames are `[left, top, right,
bottom]` in points. Both frames must match their respective files. The producer
frame is independently checked against the current export plan; a consumer can
use a different drawing or print page. Coordinate scale, text ink bounds and the
consumer page dimensions are separate measurements. No consumer-page equality
is implied by a requested producer width.

`font_mapping` names every used source family and its expected consumer family.
A substitution must be explicit; it does not preserve the source font. Text
sizes are compared exactly or within 0.025 pt when the consumer quantizes to
0.05 pt. Source font names and sizes in the corrected producer remain unchanged.
The consumer creation-program field is checked, but the declared platform and
executable digest do not authenticate the current runtime or installed fonts.

Every text is matched by its object path, including atom labels and attached
marks whose IDs can be removed by a consumer. Character content, font identity,
size, face, color, baseline, rotation and effective justification are checked.
Inherited CaptionJustification/LabelJustification take precedence over legacy
Justification. Added or removed explicit hydrogen counts and changed graphic
ArrowType are refused. Unproved native hydrogen normalization may therefore
refuse a reference; it is not silently accepted. Molecular
node/bond inventories, connectivity, element/label semantics, coordinates, and
specified stroke/scale values are compared with the uncorrected producer.
These checks reject incompatible references; they do not prove exhaustive
visual equivalence or validate every consumer-specific graphic extension.

Only selected note positions may change. The pass restores original horizontal
note gaps and uses available space to contain measured ink. Placement uses the intersection of the declared producer and consumer frames.
Every selected note must retain at least 1 mm on each side after **all** movements, with an additional
0.02 pt rounding reserve. The rounding tolerance is not the safety margin.
Unsupported collisions or insufficient room refuse without resizing fonts or
pages and without writing an output. Existing source overlaps and clearance to
molecules/graphics are outside this placement operation.

`consumer_file` is relative to the sidecar or absolute. The sidecar limit is
1 MiB and the consumer XML limit is 64 MiB. Use identical options and a fresh
output path for the second pass:

```sh
chemvas render-document input.chemvas --output corrected.cdxml \
  --width-mm 170 --cdxml-layout-reference layout.json
```

The report marks this path experimental and records hashes, frames, expected
fonts, substitution and runtime-verification limits. Default caption placement
is unchanged. CDXML colors now retain full floating-point channel precision to
avoid a consumer truncating a source channel by one 8-bit step. Native
open/save/reopen measurements are separate from manual GUI editing or Undo/Redo
verification. See [ADR 0041](adr/0041-consumer-measured-caption-layout.md).

### Native formal-charge preservation

A charged atomic node with a visible label is a native Fragment containing its
canonical atom/charge definition and one external point per existing outer bond.
BondOrdering/ConnectionOrder preserve multiple attachments. Visible label and
attached ± marks keep their positions; outer bonds and stereo remain unchanged.
This avoids ChemDraw reparsing plain P/O labels as neutral despite Charge fields.
The OMe witness retains P+×4/O−×4 after native save/reopen; MOL graph comparison
retains 288 atoms, 286 bonds and all 30 wedge/hash displays. This is bounded chemical
evidence, not raw-reference acceptance or complete visual/editing acceptance.
See [ADR 0043](adr/0043-native-formal-charge-definitions.md).

### Native label interpretation and hydrogen counts

The native save/reopen witness covers exact P/O/H element labels and the verified
Me/tBu fragment labels. These labels set `InterpretChemically="yes"`, retaining
their graph, text and layout. Other label spellings keep their previous behavior;
identifier H labels and Ar bound to a concrete fragment must not be reparsed from
their visible spelling. Charged and generic-aryl definitions keep their own mapping.

A missing `NumHydrogens` is not always zero. Native omission/explicit-count changes
are recorded separately from chemistry changes. The consumer-reference validator recognizes only the witnessed omission forms:
unlabeled neutral C with bond sum 1/4; exact P/O/H and P+/O- labels with the
recorded bond sums; and ARY query bookkeeping. It rejects unsupported counts,
contexts and explicit-to-explicit changes. Definition fragments may be renumbered
only under the same atom owner, with every member and ordered port retained.
This does not generalize a valence engine or approve the raw native OMe reference.
The seven exceptional TS counts additionally require the witnessed all-order-1
bond composition, display/direction and charged-definition or page-level H
context (ADR 0045); an equal bond-order sum alone is insufficient.
Native valence warnings caused by the original graph remain visible. See ADR 0044.

Native valence warnings on a research/TS drawing do not by themselves indicate
exporter corruption. The stored order-1 dotted bonds, source charges and explicit
labels are preserved; no fractional bond orders or normal-valence repairs are
inferred. [ADR 0045](adr/0045-native-reference-semantic-normalization.md).


Native line-width preservation and reference checks follow [ADR 0047](adr/0047-native-line-width-and-reference-spacing.md).
Legacy line graphics lose local width in the measured consumer; unheaded arrows
retain it. Effective arrow width/color, endpoints and ownership are checked,
including only verified SupersededBy fallback relationships. Native arrow IDs
change on successive saves: adjacent-save provenance is required; arbitrary
ID remapping is not permitted. Bond-local/inherited BondSpacing percentages are
also checked, so native truncation is refused rather than hidden by the point
coordinate tolerance. These changes do not approve the remaining font, label,
color or filled-shape differences.

## Native text and overlapping paint order

ADR 0048 records shared compact-label anchors, nearest twentieth-point size
encoding, and bounded native save/reopen evidence. A matching family name does
not establish identical font binaries or glyph fallback. The full reference
gate remains closed on unresolved font, baseline, charge and color differences.
For a straight stroke overlapping an opaque axis-aligned filled rectangle, the
reference must retain their relative paint order; numeric Z renumbering is
allowed. This check does not claim general overlap coverage.

## Review a native save and recover its palette

Keep the original exported CDXML and its first ChemDraw 25.0.2.14 SaveAs file.
Inspect the original colors and any native font/style substitutions:

```bash
chemvas review-cdxml producer.cdxml --native first-save.cdxml
```

To create a new copy with the exact original palette values:

```bash
chemvas review-cdxml producer.cdxml --native first-save.cdxml --recover-palette recovered.cdxml
```

The output must be a new `.cdxml` path. This command preserves all bytes outside
color-table component values, checks matching logical colors on corresponding
objects and text, and requires the exact measured four-place native values.
Nearby edited values and unknown writer versions are refused.
It does not modify `.chemvas` documents or apply the reported nearest stable
colors. Inputs are limited to 64 MiB each and canonical eight-bit producer RGB.

The JSON report's `full_fidelity_accepted` remains `false`: an exit code of zero
means the requested analysis or bounded recovery completed. Fonts, glyphs,
geometry and chemistry still need their separate checks. In particular, an
unavailable source font can be replaced by the native application; charset/name
changes do not install its physical glyphs. This command reports that change.

The measured native writer rounds again on each SaveAs. Recover each known
save before importing it again, keeping the original producer as authority.
Already degraded or arbitrarily edited native files are outside this recovery
contract. Native CDX preserved colors in the measured controls, but that does
not certify full document or font fidelity. See [ADR 0051](adr/0051-measured-native-cdxml-palette-recovery.md).


Exact palette values do not authenticate the writer or prove first-save history.
An intentional edit that yields identical bytes cannot be detected. This command
is an explicit operation for a first save whose provenance and intent the caller
knows; leave unknown-history or edited files unchanged. The report retains
`provenance_runtime_verified: false`. XML comments are preserved; only real
palette elements are edited, and the output palette is parsed and verified
before a new file is created. See [ADR 0052](adr/0052-parse-and-verify-native-palette-recovery.md).

## Editable text font contract

A CDXML font request names a logical family and style; it does not establish that
the receiving application has the same physical face, version or fallback. Keep
the authored request and actual painted fallback runs. A missing face is an
explicit compatibility limit, never permission to relabel or replace source text.
Matching names alone do not accept a consumer reference.

For a cross-platform derivative, first establish that both endpoints provide the
intended regular/bold faces and every required character, including Korean and
chemical superscripts/subscripts. Then verify actual consumer glyphs, word
origins, baselines and layout. Select a shared family deliberately on a separate
copy only after author approval; do not silently change an existing document.
A Latin-only Arial control is insufficient evidence for a multilingual figure.

In the measured regression, all 316 exported spans have glyph coverage in their
assigned Mac faces. Seven spans already use Helvetica for subscript six or the
minus sign. These intended fallback runs are valid; a single-family coverage
requirement would incorrectly reject this document. The target Windows host
lacks that original Apple/Helvetica composition. Native outputs still render
text using Arial plus physical Gulim/Microsoft Sans Serif fallback, so absence
of the requested face must not be described as universal missing glyphs.

The initial 21-name intersection used the Windows GDI list; WPF also reports
Gill Sans, whose request resolves here to Gill Sans Ultra Bold. Inventory names
must be qualified by the API and resolved physical face. An existing Windows
Malgun Gothic/Tahoma regular/bold run plan covers all 169 source characters
without installation. That establishes character availability, not the original
Mac appearance, metrics or full-document layout. Font substitution remains an
explicit choice on a separate derivative, never an automatic renderer change.
See the [proposed font review design](FONT_COMPATIBILITY_REVIEW.md), which is a
design and measured preview plan, not an implemented GUI feature. Mac ChemDraw
roundtrip remains unverified when the application is unavailable.


## Reviewed label meanings in desktop export

Select CDXML in **File → Export Figure**, then browse to the reviewed binding
JSON for the current saved drawing. A binding is never selected automatically
or carried into the next export dialog. Save any edits, review meanings for that
saved version, and choose its matching binding. Unsaved changes, stale bindings,
external file replacements and uncertain snapshots refuse before writing.
The source drawing is not changed and label meanings are not guessed.

Bold line annotations use the common flat stroke width in native unheaded
arrows. HTML and CSS sub/superscripts retain native face bits, bold/color/font
formatting and measured glyph sizes. Lines containing scripts use separately
positioned, individually editable native text runs to preserve shaped placement.
Normal lines keep their existing encoding. Italic, decorations and other
unsupported combinations continue to refuse. See [ADR 0053](adr/0053-reviewed-desktop-cdxml-and-script-geometry.md).

Reviewed desktop CDXML uses one detached snapshot of the checked saved document
for meanings, preflight and output. Deleting a bond and saving can compact its
saved ID without changing editor history; a freshly reviewed v2 documentary
contact binding now works immediately, without reopening. Visibility and
selection use saved references. Groups that touch the export scope still refuse;
groups outside selection remain outside it. Source bytes, sidecar IDs and the
live editor are unchanged. See [ADR 0054](adr/0054-saved-cdxml-export-snapshot.md).
