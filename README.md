# LiteDraw

## Current Issues
- Atom label cutouts are inconsistent for single bonds: when replacing a joint atom label, only one of the connected single bonds is trimmed while others still overlap the label.
- Benzene ring double bonds: trimming is excessive when a ring atom label is introduced, and inner double-bond segments do not reliably match the intended shorter inner-line style.
- Undo after multiple consecutive atom label changes reverts all label edits at once instead of only the most recent change.
- Importing a SMILES structure clears all existing drawings on the canvas.
- SMILES insertion always appears at a fixed location; it should insert at the clicked position, with a transparent preview on hover. The same hover preview issue applies to rings, templates, and bond placement.
- Hover highlight style: prefer a soft gray circular hover indicator around atoms/bonds instead of changing to a blue line highlight.
- Color and ring fill icons should be redesigned to be more intuitive for users.
- Add save/load functionality for the current canvas.
- Curved double arrow rendering: arrowhead placement looks incorrect.
- Left toolbar separator (dotted line) is mispositioned and should be removed.
- Add a shortcut to edit the hovered atom label via Shift + letter key combination.
- Orbital drawing does not align to the molecular geometry; it appears as a fixed shape simply overlaid on bonds.
- Orbital and template icons should be redesigned to be more intuitive.
- Arrow/orbital/template dropdowns show only text labels; they should preview the expected structure shape.
- When Wedge/Hash is selected, clicking an existing bond still cycles single/double/triple instead of switching to wedge/hash.
- Add copy-to-clipboard as image for selected molecules (to paste into external files).
- Bond length control should move to the top toolbar.
- Add export/conversion from current 2D structure to 3D `.xyz`.
