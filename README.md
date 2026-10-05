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

Chemvas is an open-source drawing tool for **reaction schemes that you can rebuild**. Every figure comes from an editable `.chemvas` file (JSON, version 9) and one command, so it can be re-rendered at a journal column width after any change. A script or an AI agent can edit the same file through checked patches instead of rewriting it.

## What Chemvas is for

**Reproducible publication schemes**

- `render-document` exports SVG, PDF, PNG and [CDXML](https://github.com/dhsohn/Chemvas/blob/main/docs/CDXML_EXPORT.md) without opening a window, fitted to a column width such as 84 mm or 174 mm.
- `check-layout` reports common label collisions and content outside the sheet before you export. It does not check every pair of objects.
- The [publication recipes](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.md) build finished figures from a script with a fixed bond length and font size, so every scheme in a manuscript has the same scale.

**Agent editing you can check**

- `inspect-document` lists every atom with a stable ID and every bond by its two atom IDs, plus the SHA-256 of the file.
- `apply-patch` takes a JSON patch of graph operations. It refuses a patch written against different file bytes, can check a patch with `--dry-run` without writing anything, validates the whole document, and writes to a new file only. The input file is never modified.
- Patches are checked for document structure, not for chemistry: element symbols and valence are not validated. Review the rendered figure before you use it.

**Drawing by hand**

- The desktop app draws structures, reaction arrows and labels, and provides alignment tools, autosave and session recovery. Drawings saved in the app work with every command above, and the reverse.

## Current limits

Chemvas does not replace ChemDraw for file exchange. Inputs that Chemvas cannot represent exactly are refused with an error rather than drawn incorrectly.

- **Opens:** `.chemvas`; SVG files that Chemvas exported with **Editable Chemvas SVG** checked (other SVG files cannot be opened); 2D MOL V2000 files within the subset Chemvas writes (bond orders 1–3, wedge and hash bonds, charges, radicals).
- **Refused:** CDX/CDXML, SDF and RXN files; MOL files with 3D coordinates, isotopes, aromatic bond type 4 or V3000.

## Install

Requires **Python 3.12+**.

```bash
pip install chemvas
chemvas
```

Drawing, figure export and the script quickstart use this install. Chemvas has no optional chemistry extra.

For local Windows packaging, see the [Windows packaging guide](https://github.com/dhsohn/Chemvas/blob/main/packaging/windows/README.md).

## Quickstart: from a script or agent

```bash
chemvas compose-document scheme.json --output scheme.chemvas
chemvas inspect-document scheme.chemvas > inspection.json
chemvas apply-patch scheme.chemvas patch.json --dry-run
chemvas apply-patch scheme.chemvas patch.json --output revised.chemvas
chemvas check-layout revised.chemvas
chemvas render-document revised.chemvas --output scheme.svg --width-mm 174
```

`scheme.json` describes atoms, bonds, arrows and notes. `patch.json` carries the `source_sha256` from `inspection.json` and the operations to apply. Each command writes a new file and refuses to overwrite an existing one, and `check-layout` exits with status 1 when it finds warnings. The formats and a worked example with images are in the [Agent CLI guide](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md).

## Quickstart: in the desktop app

![Chemvas walkthrough: insert structures, label an arrow, align the scheme, and export SVG](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.gif)

1. Choose the **Ring** tool (`J`) and click the left side of the canvas to place benzene. Choose **Bond** (`X`), drag one bond out from a ring atom to a new carbon, then drag a second bond from that carbon to a terminal atom. Hover the terminal atom, press `o`, then press **Enter** and set the label to `OH`.
2. Place a second benzene to the right. Drag one bond out from a ring atom to a new carbon, then drag a second bond from that carbon to a terminal atom. Hover the second bond and press `2` so only that bond becomes a double bond, then hover the terminal atom and press `o`. Select the **Arrow** tool, drag between the structures, and double-click the arrow to add condition labels.
3. Select both molecules (**Edit ▸ Select All**) and align them (**Edit ▸ Align ▸ Middle**).
4. Save the document (`.chemvas`). Export via **File ▸ Export Figure…** → **Plain SVG**, **Fit 2-column (174 mm)**.

For detailed instructions and example files, see the [step-by-step guide](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.md).

## Documentation

- [Browser adapter](https://github.com/dhsohn/Chemvas/blob/main/docs/WEB_ADAPTER.md): experimental web editor available when running from a source checkout (`chemvas --ui web`); omitted from installable wheel and sdist packages. Web source is experimental for future Leaf integration, not a standalone web product release.

- [Headless & Agent CLI](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md) · [Publication Schemes](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.md) · [Scheme Layout](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.md)
- [Drawing Tools & Shortcuts](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) · [MOL interchange](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#chemistry-io) · [Image Objects](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.md) · [Document compatibility](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.md)
- [Examples](https://github.com/dhsohn/Chemvas/tree/main/examples): Sample `.chemvas` documents and the scripts that build the publication figures.
- [Architecture](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.md) · [Contributing](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.md) · [Security](https://github.com/dhsohn/Chemvas/blob/main/SECURITY.md) · [Changelog](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) · [Releasing](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.md) · [License (MIT)](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)

Feedback and bug reports: [GitHub Issues](https://github.com/dhsohn/Chemvas/issues).

## How this was built

I'm a chemist, not a programmer. AI coding agents write the code in this repository.
I decide what Chemvas should do, record structural decisions as
[architecture decision records](https://github.com/dhsohn/Chemvas/tree/main/docs/adr),
keep saved drawings under a written
[compatibility policy](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.md),
and set the checks a change must pass before it merges.

I don't review the code line by line, so a change is accepted on evidence, not on an
agent's report that it works:

- `make check` runs lint, formatting and type checks, then runs each test file in its
  own process so Qt state cannot leak from one file into the next. CI runs the same
  per-file suite.
- Chemvas does not write `machine.json`. The calculation handoff and its
  project-local observation snapshot were removed with the chemistry backend
  ([ADR 0035](https://github.com/dhsohn/Chemvas/blob/main/docs/adr/0035-retire-rdkit-chemistry-provider.md)).
  Another project's decision to adopt a provider is outside this repository.
- High-impact changes, such as the document format, undo and rollback, and figure
  export, get an independent adversarial review from a separate agent.
