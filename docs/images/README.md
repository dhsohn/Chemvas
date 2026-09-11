# Demo and branding media

The introduction leads with the actual figure exported from
[first-scheme.chemvas](../../examples/first-scheme.chemvas), followed by a short
walkthrough of the desktop workflow. The example is a schematic drawing exercise;
it is not an experimental result.

| Asset | Source and purpose |
| --- | --- |
| `examples/first-scheme.png` | 300 DPI, 174 mm PNG export; the README's completed result. |
| `examples/first-scheme.svg` | Plain SVG using the 174 mm preset, with outlined atom/arrow labels and no embedded source document. |
| `demo.gif` | Real Qt UI/canvas frames with chapter captions and edited pauses. |
| `demo.png` | A still of the completed drawing in the app. |
| `walkthrough-drawing.gif` | Reference-guide walkthrough: bonds by dragging, bond order and element hotkeys, a charge, a fused benzene ring. |
| `walkthrough-arrows.gif` | Reference-guide walkthrough: reaction, equilibrium and curved arrows, the arrow-label dialog, a Line-tool reaction profile with snapping connectors. |
| `walkthrough-editing.gif` | Reference-guide walkthrough: move, rotate with the knob, flip, align, distribute. |
| `walkthrough-chemistry.gif` | Reference-guide walkthrough: open a molfile, Molecule Info, export MOL and 3D XYZ (RDKit). |
| `walkthrough-images.gif` | Image-objects walkthrough: insert a synthetic PNG, move it, resize and lighten it in Image Properties. |
| `walkthrough-arrange.gif` | Scheme-layout walkthrough: group structures with captions, Edit ▸ Arrange Scheme…, one arranged row. |
| `cli-*.png` | CLI guide and scheme-layout figures: the documented example commands run on small synthetic inputs and rendered with `render-document` (compose, insert-template, apply-patch before/after, layout-document arrange, align-y and wrap before/after). |
| `publication-*.png` | The final PNGs of `examples/publication_scheme.py` (`pair`, `independent-parts`) and `examples/publication_comparison.py` (`comparison`). |
| `banner.png` | Existing Chemvas mark and the new tagline, rendered at 1360×270. |
| `social-preview.png` | 1280×640 sharing card, including the actual example SVG. |

## Regenerate the walkthrough

Use the repository's development environment with the optional RDKit backend:

```bash
python -m pip install -e ".[dev,rdkit]"
QT_QPA_PLATFORM=offscreen python scripts/capture_first_scheme.py --output-dir /tmp/chemvas-demo-capture
```

Choose an empty output directory. The script refuses a non-empty directory and
uses a temporary app-data/config/cache profile. It never opens existing user
documents or starts session recovery. It chooses the Ring tool and inserts the
two structures through the SMILES controls on its options bar, rotates each
selection, opens the actual atom-label and
arrow-label dialogs, aligns the scheme, saves the document, and exports it
through the desktop figure-export service. The export-options dialog is real;
the output path is supplied by the script to avoid recording a user's file picker.
Trailing whitespace in the generated SVG is removed for repository hygiene;
the drawing's elements, attributes, and glyph paths are not changed.

The walkthrough calls the atom-label action directly: this also works on
Wayland, which may refuse synthetic global pointer motion. The tutorial describes
the user's hover-and-Enter shortcut. The committed capture was produced offscreen;
a Wayland run also completed and produced an identical editable document in the
capture environment. This is not a Windows or macOS acceptance claim.

Captions and cursor highlights are added around/to the captured UI frames.
Pauses are edited for readability, so the GIF is not a speed measurement.
Qt, fonts, display scaling, and RDKit versions can change the output. The
committed files are a reviewed capture, not a cross-machine byte-reproduction
guarantee.

Review the output, then copy the five files to their intended destinations:

```bash
cp /tmp/chemvas-demo-capture/first-scheme.chemvas examples/first-scheme.chemvas
cp /tmp/chemvas-demo-capture/first-scheme.svg examples/first-scheme.svg
cp /tmp/chemvas-demo-capture/first-scheme.png examples/first-scheme.png
cp /tmp/chemvas-demo-capture/demo.gif docs/images/demo.gif
cp /tmp/chemvas-demo-capture/demo.png docs/images/demo.png
```

Check the saved drawing and its command-line rendering using a new output path:

```bash
chemvas inspect-document examples/first-scheme.chemvas
chemvas check-layout examples/first-scheme.chemvas
chemvas render-document examples/first-scheme.chemvas --output /tmp/first-scheme-check.svg
```

The command-line render uses preset bond-length sizing. The example SVG and PNG
use the desktop export's 174 mm setting.

The example SVG includes outlined arrow labels, preserving the canvas's shaped
glyphs and subscript/superscript positions. The sharing card renders this SVG
directly; it does not repair the output. The SVG records a width of 173.919 mm
after the exporter rounds the nominal 174 mm preset.

## Regenerate the reference walkthroughs

The four `walkthrough-*.gif` files come from the same harness
([walkthrough_capture.py](../../scripts/walkthrough_capture.py)) as the first
scheme, one topic per GIF:

```bash
QT_QPA_PLATFORM=offscreen python scripts/capture_walkthroughs.py --output-dir /tmp/chemvas-walkthroughs
```

`--topic drawing|arrows|editing|chemistry|images|arrange` regenerates one of
them. The images topic inserts a synthetic spectrum through the same function
**File ▸ Insert Image…** calls after its file picker; the arrange topic builds
two grouped structures off camera and drives the real Arrange Scheme dialog. The editing,
chemistry and arrange topics place structures from SMILES and therefore need
the optional RDKit backend. The chemistry topic additionally writes an aspirin
molfile into the output directory, opens it the way **File ▸ Open** does, and
drives the Molecule Info window and the MOL and XYZ exports through the same
services the menu actions call, with the output paths supplied by the script
instead of a file picker. Copy the reviewed GIFs to `docs/images/`.

## Regenerate the CLI and publication figures

```bash
QT_QPA_PLATFORM=offscreen python scripts/render_doc_figures.py --output-dir /tmp/chemvas-doc-figures
```

The script writes each documented example input into `work/`, runs the public
commands exactly as the guides show them, renders the results with
`render-document` at 300 dpi, runs the two publication examples, and leaves the
figures in `figures/`. Review them, then copy `figures/*.png` to `docs/images/`.
RDKit is not needed; repeated runs give byte-identical PNGs in one environment.

## Regenerate the branding

After updating the example SVG:

```bash
QT_QPA_PLATFORM=offscreen python scripts/generate_branding_images.py
```

The [branding script](../../scripts/generate_branding_images.py) reuses the
existing mark and reads the example SVG; it does not redraw the chemistry.

`social-preview.png` must be uploaded separately under **GitHub ▸ Settings ▸
General ▸ Social preview**. Committing it does not change the repository's
configured sharing image. The app icon remains in `app/chemvas/assets/icon/`.

The package summary lives in [pyproject.toml](../../pyproject.toml). The GitHub
About description is a separate setting; the corresponding copy is:

> An open-source desktop canvas for chemical structures and reaction schemes,
> with publication-ready export and scriptable document workflows.

README and documentation links use `main` URLs so they also work on PyPI after
publication. New media and tutorial URLs will become available when these files
reach `main` on GitHub. PyPI's long description updates with a subsequent package
release.
