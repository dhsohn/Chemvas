# Your first reaction scheme

[한국어](FIRST_SCHEME.ko.md) · [Back to the introduction](../README.md)

Draw a benzyl alcohol oxidation scheme, save its editable `.cdxml` source, and export a vector figure for your manuscript.

![The completed scheme, exported from Chemvas](../examples/first-scheme.png)

## Start with the finished drawing

You can download the completed file [first-scheme.cdxml](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.cdxml) and open it directly (**File ▸ Open**).

Open, edit, and export with the standard installation:

```bash
pip install chemvas
chemvas
```

## 1. Draw and arrange structures

1. Choose the **Ring** tool (`J`) and click the left side of the canvas to place benzene.
2. Choose the **Bond** tool (`X`). From the upper-right ring atom, drag one bond up and right at 30°; that creates a new carbon. Drag a second bond down and right at 30° from that new carbon to a terminal atom.
3. Hover the terminal atom, press `o`, then press **Enter** and set the label to `OH`. Leave the new carbon unlabeled.
4. Switch to the **Select** tool (`Space`). Keep the ring upright and the `OH` label horizontal.
5. Place a second benzene to the right in the same orientation. From its upper-right atom, drag one bond up and right at 30°, then drag a second bond down and right at 30° from the new carbon to a terminal atom. Hover the second bond and press `2` so only that bond becomes a double bond. Hover the terminal atom and press `o`. Leave room between the structures for the arrow.

## 2. Draw and label the arrow

1. Choose the **Arrow** tool (`E`) and drag from left to right between the two structures.
2. Switch back to **Select** (`Space`) and double-click the arrow to open the label editor:

| Field | Enter | Appearance |
| --- | --- | --- |
| Above | Type `MnO2`, select only `2`, then click **Subscript x₂** | MnO₂ |
| Below | `oxidation` | oxidation |

3. Click **OK**. The labels are bound to the arrow and move along with it.
   - Format selected characters with **Subscript x₂** or **Superscript x²**. Use **Symbols** to insert symbols such as Δ and ‡.
   - The editor accepts visible text and formatting. Typing `MnO_2` does not apply a subscript and disables **OK**; remove the underscore and format the `2` as above.

## 3. Align and save

1. Select both molecules and the arrow (**Edit ▸ Select All**, `Ctrl+A` on Windows/Linux or `⌘A` on macOS).
2. Align their vertical centers with **Edit ▸ Align ▸ Middle**.
3. Save the editable document via **File ▸ Save As…** as `first-scheme.cdxml`.
4. Close the document, reopen the saved file, and check that both structures and the MnO₂ label are present. Double-click the arrow to confirm that the `2` is still formatted as a subscript.

## 4. Export the figure

Choose **File ▸ Export Figure…**:

| Option | Value | Description |
| --- | --- | --- |
| Format | Plain SVG | Clean vector output |
| Size | Fit 2-column (174 mm) | Fits standard 2-column journal layouts |
| Scope | Whole canvas | Exports the full scheme |
| Background | White | Opaque white background |

Click **Export** and save as `first-scheme.svg`. Arrow and atom labels are exported as vector outlines to preserve the drawn letter shapes. Keep the `.cdxml` file for future editing.

You can also download the pre-exported [SVG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.svg) and [300 DPI PNG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.png).

## Command-line workflow

You can also inspect, validate, and render `.cdxml` files directly from your terminal:

```bash
chemvas inspect-document first-scheme.cdxml
chemvas check-layout first-scheme.cdxml
chemvas render-document first-scheme.cdxml --output first-scheme-rendered.svg
```

- `inspect-document`: Summarizes atoms, bonds, labels, and document metadata as JSON.
- `check-layout`: Reports selected label collisions and content outside the sheet.
- `render-document`: Renders the document directly to SVG or PDF without launching the graphical desktop app.

For further CLI options, see the [CLI guide](AGENT_CLI.md).
