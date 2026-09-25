# Your first reaction scheme

[한국어](FIRST_SCHEME.ko.md) · [Back to the introduction](../README.md)

Learn how to draw a reaction scheme, save the editable `.chemvas` document, and export a publication-ready vector figure. This tutorial walks through creating a simple benzyl alcohol oxidation scheme.

![The completed scheme, exported from Chemvas](../examples/first-scheme.png)

## Start with the finished drawing

You can download the completed file [first-scheme.chemvas](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.chemvas) and open it directly (**File ▸ Open**).

Basic viewing, editing, and exporting work with the standard installation:

```bash
pip install chemvas
chemvas
```

To insert structures via SMILES (Step 1), install the optional RDKit backend:

```bash
pip install "chemvas[rdkit]"
```

## 1. Insert and arrange structures

1. Type `OCc1ccccc1` into the SMILES input field below the toolbar.
2. Click **Insert**, then click on the left side of the canvas to place benzyl alcohol.
3. Switch to the **Select** tool (`Space`), select the molecule, and press **Alt+Up** three times to rotate it by −45° (or use **Edit ▸ Rotate…**).
4. Hover over the alcohol oxygen atom, press **Enter**, and change the label to `OH` so the hydrogen is explicitly visible.
5. In the SMILES field, enter `O=Cc1ccccc1`, click **Insert**, and place benzaldehyde to the right. Rotate it to match the left structure, leaving space for the reaction arrow in the middle.

## 2. Draw and label the arrow

1. Choose the **Arrow** tool (`E`) and drag from left to right between the two structures.
2. Switch back to **Select** (`Space`) and double-click the arrow to open the label editor:

| Field | Enter | Appearance |
| --- | --- | --- |
| Above | `MnO_2` | MnO₂ |
| Below | `oxidation` | oxidation |

3. Click **OK**. The labels are bound to the arrow and move along with it.
   - Use underscores for subscripts (`MnO_2` → MnO₂).
   - Use curly braces for multi-character sub/superscripts (e.g., `K_{2}CO_{3}`, `\Delta G^{\ddagger}`).

## 3. Align and save

1. Select both molecules and the arrow (**Edit ▸ Select All** or `Ctrl+A`).
2. Align their vertical centers with **Edit ▸ Align ▸ Middle**.
3. Save the editable document via **File ▸ Save As…** as `first-scheme.chemvas`.

## 4. Export the figure

Choose **File ▸ Export Figure…**:

| Option | Value | Description |
| --- | --- | --- |
| Format | Plain SVG | Clean vector output |
| Size | Fit 2-column (174 mm) | Fits standard 2-column journal layouts |
| Scope | Whole canvas | Exports the full scheme |
| Background | White | Opaque white background |
| Editable Chemvas SVG | Unchecked | Standard vector graphics |

Click **Export** and save as `first-scheme.svg`. Arrow and atom labels are exported as vector outlines to preserve formatting across any viewer. Keep the `.chemvas` file for future editing.

You can also download the pre-exported [SVG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.svg) and [300 DPI PNG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.png).

## Command-line workflow

You can also inspect, validate, and render `.chemvas` files directly from your terminal:

```bash
chemvas inspect-document first-scheme.chemvas
chemvas check-layout first-scheme.chemvas
chemvas render-document first-scheme.chemvas --output first-scheme-rendered.svg
```

- `inspect-document`: Summarizes atoms, bonds, labels, and document metadata as JSON.
- `check-layout`: Validates element boundaries and reports warnings (overlaps, out-of-bounds text).
- `render-document`: Renders the document directly to SVG or PDF without launching the graphical desktop app.

For further CLI options, see the [Agent CLI guide](AGENT_CLI.md).
