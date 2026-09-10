<p align="center">
  <img src="https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/banner.png" alt="Chemvas — Draw interactively. Automate safely. Export exactly." width="680">
</p>

<p align="center">
  <a href="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml"><img src="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/chemvas/"><img src="https://img.shields.io/pypi/v/chemvas" alt="PyPI"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+"></a>
  <a href="https://github.com/dhsohn/Chemvas/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
</p>

<p align="center"><b>English</b> · <a href="https://github.com/dhsohn/Chemvas/blob/main/README.ko.md">한국어</a></p>

Chemvas is an **open-source desktop canvas for chemical structures and reaction
schemes**, with publication-ready export and scriptable document workflows.

![A benzyl alcohol oxidation scheme exported directly from Chemvas](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.png)

[Open the editable drawing](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.chemvas) ·
[Get the SVG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.svg) ·
[Follow the walkthrough](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.md)

## Draw interactively. Automate safely. Export exactly.

- **Draw interactively.** Sketch structures, insert SMILES, label reaction arrows,
  and align molecules on a desktop canvas. Keep working in an editable drawing
  with autosave and crash recovery. SMILES insertion needs the optional RDKit backend.
- **Automate safely.** Compose, inspect, check layouts, and render documents from
  scripts. Graph edits check the source file's hash and validate the proposed
  changes before writing a new document.
- **Export exactly.** Save SVG, PDF, PNG, or TIFF with explicit physical-size
  presets, including 84 mm and 174 mm column widths. Keep the editable document
  alongside the exported figure.

## Install and draw

Requires **Python 3.12+**. Install with SMILES support for the walkthrough:

```bash
pip install "chemvas[rdkit]"
chemvas
```

For drawing and figure export without RDKit, use `pip install chemvas`.
PyQt6 is included in either installation. Desktop installers are not available
yet; the supported distribution is the Python package.

For local Windows executable and installer builds, see the
[Windows preparation guide](https://github.com/dhsohn/Chemvas/blob/main/packaging/windows/README.md).

## Your first reaction scheme

![Chemvas walkthrough: insert structures, label an arrow, align the scheme, and export SVG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.gif)

This edited walkthrough uses the real application. The drawing is a schematic
illustration, not an experimental result.

1. Choose the **Ring** tool, enter `OCc1ccccc1` in the SMILES field of its
   options bar, click **Insert**, then click to place the structure. Hover over its oxygen, press **Enter**, and set the label to
   `OH`.
2. Insert `O=Cc1ccccc1` to the right. Choose **Arrow** and drag between the two
   structures. Double-click the arrow to add its labels.
3. Select the scheme, then choose **Edit ▸ Align ▸ Middle**.
4. Save the drawing as `.chemvas`. Use **File ▸ Export Figure…** to export
   **Plain SVG** at **Fit 2-column (174 mm)**.

The [step-by-step guide](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.md)
includes the label text, downloadable files, and a command-line export example.
The saved drawing opens and exports without RDKit.

## Work with drawings from scripts

After downloading `first-scheme.chemvas`, try:

```bash
chemvas inspect-document first-scheme.chemvas
chemvas check-layout first-scheme.chemvas
chemvas render-document first-scheme.chemvas --output first-scheme-rendered.svg
chemvas render-document first-scheme.chemvas --output first-scheme.pdf --width-mm 174
```

Rendering exports one drawing to SVG, PNG, or a single-page vector PDF. It
creates a new file and leaves the source drawing untouched. This
command defaults to preset bond-length sizing; add `--width-mm 174` to request
a column width, or `--max-height-mm 120` to reject an overly tall figure without
shrinking it. Layout checks cover visible note and
atom-label text, shape borders, and arrow–structure crossings, not every possible
overlap in a chemical scheme.

See the [document CLI guide](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md)
for composition, Graph Patch, render guarantees, and limits.
PNG/JPEG experimental panels can be embedded alongside structures using
**File ▸ Insert Image**, clipboard paste, or the composition CLI. Use
**Edit ▸ Image Properties** to set their size, aspect ratio and opacity;
see [image objects](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.md) for the schema and limits.

For structure names and energies that stay aligned, use
[explicit scheme layout](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.md) to arrange structure/caption
blocks and keep them together as native groups.

That layout also accepts a `max_row_width` budget for long pathways. Use
`render-document --min-font-pt 6` with SVG or PNG to reject glyphs smaller than your
chosen threshold, including subscripts; the value is not a journal preset.

In the desktop, group each structure with its notes and use **Edit ▸ Arrange
Scheme…** to set rows, reading order, captions and optional wrapping as one
undoable edit. **File ▸ Export Figure…** also accepts a custom width and optional
height limit. Minimum-font checking is available for whole-canvas SVG and PNG.

For already-spaced drawings, `layout-document` with `mode: "align-y"` moves only
molecular Y positions, keeping captions and all X positions fixed. Agents can
also `insert-template` with native benzene/chair/regular-ring geometry and use
Graph Patch `set_terminal_angle` for a specified terminal bond angle. Layout
diagnostics now include nonincident atom-label–bond and attached-charge–bond ink.
The [publication recipe](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.md) shows common print scale,
real scripts, explicit independent parts and no duplicate figure heading.

## More workflows and documentation

- **Chemistry I/O:** SMILES import, MOL interchange, molecule information, and
  3D XYZ export. Some operations require RDKit; see the
  [reference](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#chemistry-io).
- **Calculation handoff (RDKit):** elementary steps and reviewed precomplexes, exported as one `machine.json` per step. [Details](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md#calculation-states-and-elementary-steps).
- **Documents:** editable `.chemvas` JSON files (version 7).
  [Drawing tools and shortcuts](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) ·
  [More examples](https://github.com/dhsohn/Chemvas/tree/main/examples) ·
  [Current limits and roadmap](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#roadmap--not-yet-supported).

## Contribute

Try the example and [share what got in your way](https://github.com/dhsohn/Chemvas/issues).
Small reproducible drawings, installation feedback, and documentation improvements
are useful contributions. If Chemvas is useful to you, a star helps others find it.

For development, read
[CONTRIBUTING](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.md).
`make check` runs lint, formatting, type checking, the file-isolated test suite,
and document-handoff conformance checks.

[Architecture](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.md) ·
[Changelog](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) ·
[Releasing](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.md) ·
[MIT License](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)
