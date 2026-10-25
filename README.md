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

Chemvas is an **open-source desktop app for drawing molecules and reaction schemes, then exporting them for a paper**. Draw on the canvas or use scripts to keep a set of figures at the same scale. Save the editable source as `.cdxml` and export the finished figure as SVG, PDF or PNG.

![Drawing structures, labelling an arrow and aligning a reaction scheme in Chemvas](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.gif)

## From a drawing to a paper

- **Draw structures and schemes.** Place rings, bonds, reaction arrows and labels on the canvas, then align them. Autosave and session recovery help you pick up your work.
- **Revise the source and export again.** Open, edit and save supported single-page CDXML files. Export figures at a journal column width such as 84 mm or 174 mm.
- **Keep figures at the same scale.** The [publication examples](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.md) use fixed bond lengths and font sizes across a manuscript's figures.
- **Script repeated edits.** Compose, inspect, patch and render documents from the command line. `check-layout` detects selected label collisions and content outside the sheet. The [CLI guide](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md) covers its scope and the patch format.

## Install

Runs on macOS, Windows and Linux with **Python 3.12+**.

```bash
pip install chemvas
chemvas
```

Standalone downloads for the first stable release are being prepared for the
[three-platform target matrix](https://github.com/dhsohn/Chemvas/blob/main/docs/RELEASE_ACCEPTANCE.md). Its native installation
checks are still pending; the Python installation above remains available.

To build a Windows executable locally, follow the [packaging guide](https://github.com/dhsohn/Chemvas/blob/main/packaging/windows/README.md).

## Draw your first scheme

1. Choose the **Ring** tool (`J`) and click the left side of the canvas to place benzene. Choose **Bond** (`X`), drag one bond out from a ring atom to a new carbon, then drag a second bond from that carbon to a terminal atom. Hover the terminal atom, press `o`, then press **Enter** and set the label to `OH`.
2. Place a second benzene to the right. Drag one bond out from a ring atom to a new carbon, then drag a second bond from that carbon to a terminal atom. Hover the second bond and press `2` so only that bond becomes a double bond, then hover the terminal atom and press `o`. Select the **Arrow** tool, drag between the structures, and double-click the arrow to add condition labels.
3. Select both molecules (**Edit ▸ Select All**) and align them (**Edit ▸ Align ▸ Middle**).
4. Save the document (`.cdxml`). Export via **File ▸ Export Figure…** → **Plain SVG**, **Fit 2-column (174 mm)**.

The [first-scheme tutorial](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.md) walks through each step and includes the finished drawing.

## Edit and export with a script

```bash
chemvas compose-document scheme.json --output scheme.cdxml
chemvas inspect-document scheme.cdxml > inspection.json
chemvas apply-patch scheme.cdxml patch.json --dry-run
chemvas apply-patch scheme.cdxml patch.json --output revised.cdxml
chemvas check-layout revised.cdxml
chemvas render-document revised.cdxml --output scheme.svg --width-mm 174
```

`scheme.json` describes atoms, bonds, arrows and notes. `patch.json` contains the operations and the `source_sha256` from `inspection.json`. A patch applies only to the file bytes it was prepared for and writes its result to a new file. Output commands refuse to overwrite existing files. `check-layout` returns exit code 1 when it finds warnings.

Patch validation checks document structure. Element symbols, valence and the chemical meaning of the finished figure need your review. See the [CLI guide](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md) for input formats and a worked example.

## File formats

- **Editable source:** supported single-page `.cdxml`. Imported files use Chemvas drawing styles while native fragments, reaction references and vector objects retain their source XML. Edits that cannot preserve them are rejected before saving.
- **Structure import:** supported 2D MOL V2000 with bond orders 1–3, wedge and hash bonds, charges and radicals.
- **Figure output:** SVG, PDF and PNG. SVG is an output format; it cannot be reopened for editing. [CDXML export](https://github.com/dhsohn/Chemvas/blob/main/docs/CDXML_EXPORT.md) is also available.
- **Unsupported input:** binary CDX, multipage CDXML, SDF, RXN, and MOL files with 3D coordinates, isotopes, aromatic bond type 4 or V3000.

See the [document compatibility policy](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.md) and [CDXML format scope](https://github.com/dhsohn/Chemvas/blob/main/docs/adr/0058-desktop-cdxml-documents.md) for preservation details.

## Explore

- [Drawing tools and shortcuts](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) · [Image objects](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.md)
- [Publication examples](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.md) · [Scheme layout](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.md) · [Example files](https://github.com/dhsohn/Chemvas/tree/main/examples)
- [Architecture](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.md) · [Contributing](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.md) · [Security](https://github.com/dhsohn/Chemvas/blob/main/SECURITY.md) · [Changelog](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) · [Releasing](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.md) · [MIT license](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)
- [Browser adapter](https://github.com/dhsohn/Chemvas/blob/main/docs/WEB_ADAPTER.md): an experimental source-checkout feature, launched with `chemvas --ui web`. It is excluded from distribution packages.

Found a rough edge or have an idea? Open a [GitHub issue](https://github.com/dhsohn/Chemvas/issues).

## How this was built

I build Chemvas for use in chemistry research. I set the requirements, document formats and validation criteria, and use AI coding agents to write the code.

Design decisions live in [ADRs](https://github.com/dhsohn/Chemvas/tree/main/docs/adr), and the [compatibility policy](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.md) defines how saved drawings are preserved. Locally, `make check` runs lint, formatting, type checks and tests in separate processes for each test file. GitHub CI runs quality checks, a package smoke test and secret scanning.
