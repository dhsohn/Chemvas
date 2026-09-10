# Your first reaction scheme

[한국어](FIRST_SCHEME.ko.md) · [Back to the introduction](../README.md)

Build a small scheme, keep the editable drawing, and export a vector figure.
The example shows benzyl alcohol and benzaldehyde with a manganese dioxide
oxidation label. It is a drawing exercise, not an experimental procedure or a
reported result. For background on this reaction class, see
[Gritter, DuPre and Wallace, *Nature* 202, 179–181 (1964)](https://doi.org/10.1038/202179a0).

![The completed scheme, exported from Chemvas](../examples/first-scheme.png)

## Start with the finished drawing

Download [first-scheme.chemvas](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.chemvas)
and open it with **File ▸ Open**. If your browser displays JSON, use **Save link
as…** and keep the `.chemvas` extension. The example files are separate downloads,
not installed by pip.

You can edit and export the finished drawing with the core installation:

```bash
pip install chemvas
chemvas
```

Python 3.12+ is required. To recreate the SMILES insertion steps below, install
the optional RDKit backend instead:

```bash
pip install "chemvas[rdkit]"
```

## 1. Insert and arrange two structures

1. Choose the **Ring** tool and enter `OCc1ccccc1` in the SMILES field of its
   options bar. Click **Insert**, then click on the left of the canvas to place
   benzyl alcohol.
2. For the orientation in the example, select the molecule with **Select** and
   press **Alt+Up** three times to rotate it by −45°. You can also enter an angle
   through **Edit ▸ Rotate…**.
3. Hover over the alcohol oxygen and press **Enter**. Set the atom label to
   `OH` and confirm. This makes the hydroxyl hydrogen visible in the drawing.
4. Insert `O=Cc1ccccc1` to the right for benzaldehyde. Select just that molecule
   and rotate it in the same way. Leave room for the arrow between them.

The starting orientation can vary with the RDKit version. Rotate as needed;
the saved example already has its coordinates. Use the zoom control at the
bottom right to make the structures comfortable to work on.

## 2. Draw and label the arrow

Choose **Arrow** and drag from left to right between the structures. Hold
**Shift** while dragging to lock the angle. Switch to **Select** and
double-click the arrow:

| Field | Enter | Appearance |
| --- | --- | --- |
| Above | `MnO_2` | MnO₂ |
| Below | `oxidation` | oxidation |

Confirm with **OK**. These labels belong to the arrow and follow it when it
moves. The underscore formats a subscript; braces group longer subscripts,
such as `k_{obs}`. In your own scheme, use these fields for your reaction
conditions. The exercise supplies no amounts, times, yields, or measured data.

## 3. Align and save

Use **Edit ▸ Select All**, then **Edit ▸ Align ▸ Middle**. Each connected molecule
moves as a unit. Click an empty area to clear the selection and inspect the
result. Use **File ▸ Save As…** to save `first-scheme.chemvas`.

## 4. Export the figure

Choose **File ▸ Export Figure…**:

| Option | Value |
| --- | --- |
| Format | Plain SVG - vector |
| Size | Fit 2-column (174 mm) |
| Scope | Whole canvas |
| Background | White |
| Editable Chemvas SVG | Unchecked |

Export to `first-scheme.svg`. Atom and arrow labels are outlined, and the selected column
width is nominally 174 mm (the example SVG records 173.919 mm after rounding).
Keep the `.chemvas` document as the editable source. The same dialog also offers
PDF, PNG, and TIFF.

The [downloadable SVG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.svg)
and [300 DPI PNG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.png)
were exported using these settings.

Arrow labels are exported as glyph outlines, which preserves the canvas's
subscript/superscript placement in SVG. Keep the source document for text
editing: outlined glyphs are shapes, not editable SVG text.

## Try the command line

From the directory containing the downloaded drawing:

```bash
chemvas inspect-document first-scheme.chemvas
chemvas check-layout first-scheme.chemvas
chemvas render-document first-scheme.chemvas --output first-scheme-rendered.svg
```

These commands work without RDKit. Inspection reports the structures and
document metadata; layout checking reports supported text/shape warnings without
editing anything. It does not validate the reaction or check every atom-label
and arrow overlap. Rendering writes a new SVG and reports its dimensions and
hash. Choose a new output name on each run: existing files are refused.

The command uses preset bond-length sizing, so its physical size differs from
the 174 mm desktop export. See the [CLI reference](AGENT_CLI.md) for the exact
render guarantees and supported document operations.

## About the walkthrough

The [short GIF](images/demo.gif) captures real Qt controls and canvas edits, with
pauses shortened and chapter captions added. It is a scripted walkthrough, not
a speed benchmark. The [capture script](../scripts/capture_first_scheme.py)
produces the drawing, SVG, PNG, and screenshots together from synthetic inputs;
[media notes](images/README.md) describe regeneration.
