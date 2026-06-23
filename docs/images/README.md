# Screenshots & demo media

The README's hero image is **`demo.png`** (already in place — a reaction scheme plus
several organocatalyst structures). The items below are optional extras you can add
later to enrich the README.

## Nice-to-have extras

| File | What it should show | Suggested size |
| --- | --- | --- |
| `demo.gif` | A 5–10s loop: draw a structure → type a SMILES and Render → export a figure. Motion sells a drawing tool. | ≤ 1200px wide, a few MB |
| `molecule-info.png` | The Molecule Info window with the interactive 3D preview. | ~1200px wide |
| `export-dialog.png` | The figure-export dialog (format/size/DPI options). | ~1000px wide |

If you replace `demo.png` with a different hero, keep the filename or update the
`![...](docs/images/demo.png)` reference in
[`README.md`](../../README.md) and [`README.ko.md`](../../README.ko.md).

## How to capture (macOS)

Still image of a region:

```bash
# interactive crosshair → saves a PNG to ~/Desktop
screencapture -i ~/Desktop/hero.png
```

Or press <kbd>⌘</kbd><kbd>⇧</kbd><kbd>4</kbd> and drag. Move the result here as
`docs/images/hero.png`.

For a short GIF, [Kap](https://getkap.co) (free, open source) is the easiest — record
the window, export as GIF. From the command line you can also record a `.mov` with
<kbd>⌘</kbd><kbd>⇧</kbd><kbd>5</kbd> and convert it:

```bash
# with ffmpeg + gifski for a crisp, small GIF
ffmpeg -i recording.mov -vf "fps=15,scale=1000:-1" -f yuv4mpegpipe - \
  | gifski -o demo.gif -
```

## Tips

- Use a clean canvas and the default ACS style so the structure reads clearly.
- Trim dead time from the GIF; keep it short so it loops nicely on GitHub.
- Keep file sizes reasonable (GitHub renders inline; multi-MB GIFs feel sluggish).
