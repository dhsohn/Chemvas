# Structure and Caption Layout

[한국어](SCHEME_LAYOUT.ko.md)

`layout-document` aligns reaction structures and captions into clean, publication-ready rows. It automatically centers captions beneath each molecule, aligns text baselines, and enforces uniform column widths across parallel reactions.

## Arranging from the Desktop GUI

![Arrange Scheme walkthrough: group each structure with its caption, open the dialog, choose captions and the arrow, click Arrange](images/walkthrough-arrange.gif)

1. **Group Structures with Captions**: Select each complete molecule along with its caption notes and press **Edit ▸ Group** (`Ctrl+G`).
2. **Open Arrange Dialog**: Go to **Edit ▸ Arrange Scheme…**. Each group forms an independent block.
3. **Configure Captions & Arrows**:
   - Assign notes as **Structure caption** or **Attached note**.
   - Select connecting arrows between blocks.
4. **Set Spacing & Wrap**: Specify gaps and an optional **Wrap width**, then click **Arrange**. You can undo any changes anytime with `Ctrl+Z`.

## Arranging via CLI

You can script the layout pipeline using `layout-document`:

```bash
chemvas inspect-document scheme.chemvas
chemvas layout-document scheme.chemvas --layout layout.json --output arranged.chemvas
chemvas check-layout arranged.chemvas
chemvas render-document arranged.chemvas --output arranged.svg --width-mm 174 --max-height-mm 120
```

### Layout Specification (Arrange Mode)

A standard layout request aligns blocks along rows and positions captions underneath:

```json
{
  "format": "chemvas-scheme-layout",
  "version": 1,
  "source_sha256": "<64 lowercase hexadecimal characters>",
  "gap": 12,
  "row_gap": 24,
  "caption_gap": 8,
  "line_gap": 4,
  "rows": [{
    "blocks": [
      {"atoms": [0, 1, 2], "captions": [0, 1], "anchor_atom": 0},
      {"atoms": [3, 4, 5], "captions": [2, 3], "anchor_atom": 3,
       "items": [["ts_brackets", 0]]}
    ],
    "arrows": [0]
  }]
}
```

![Before layout: the second structure sits higher, its captions further down and the bracket loosely around it](images/cli-layout-arrange-before.png)

![After layout: both blocks share a row, captions are centred below each structure at common baselines, the bracket moved with its block](images/cli-layout-arrange-after.png)

- **`blocks`**: Array of molecular units. `atoms` specifies atom IDs, `captions` lists note indices (top to bottom), and `anchor_atom` optionally aligns a specific reaction center.
- **`column_group`**: Shared identifier across rows to enforce identical column widths for comparison schemes.
- **`caption_alignment`**: `"row"` aligns captions across a shared baseline; `"structure"` centers each caption directly below its molecule.

## Aligning Molecular Drawings Only (`align-y`)

When horizontal spacing and captions are already positioned, use `"mode": "align-y"` to align the vertical centers of molecules without moving text or arrows:

```json
{
  "format": "chemvas-scheme-layout",
  "version": 1,
  "mode": "align-y",
  "source_sha256": "<64 lowercase hexadecimal characters>",
  "rows": [{
    "reference_blocks": [0],
    "blocks": [
      {"atoms": [0, 1, 2], "captions": [0]},
      {"atoms": [3, 4, 5, 6], "captions": [1],
       "parts": [[3, 4, 5], [6]]}
    ]
  }]
}
```

![Before align-y: the product chain and the Cl⁻ sit well above the reactant](images/cli-layout-align-y-before.png)

![After align-y: both parts moved down to the reactant's molecular midline, captions untouched](images/cli-layout-align-y-after.png)

- **`reference_blocks`**: Zero-based block indices whose vertical center acts as the target alignment line.
- **`parts`**: Defines sub-units within a block that can shift vertically independently (e.g., a counter-ion or separate reagent).

## Wrapping Long Pathways

To wrap long multi-step pathways into multiple rows, specify `"max_row_width"` in canvas units:

![Before wrapping: four states and three arrows in one long row](images/cli-layout-wrap-before.png)

![After wrapping with max_row_width 320: two lines, the continuation arrow at the start of the second line](images/cli-layout-wrap-after.png)

When a reaction wraps:
- Blocks are kept intact without splitting.
- The connecting arrow that crosses a line break moves to the start of the next line, clearly indicating continuation.

## Verifying & Guarding Layouts

Before finalizing figures, enforce minimum font size and height constraints during headless rendering:

```bash
chemvas render-document arranged.chemvas --output arranged.svg --width-mm 174 --min-font-pt 6
```

- `--min-font-pt`: Rejects exports if scaling causes any text (including sub/superscripts) to fall below the specified threshold.
- `--max-height-mm`: Rejects exports that exceed the journal's maximum allowable figure height.
