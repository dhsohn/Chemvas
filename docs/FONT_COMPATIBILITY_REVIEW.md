# Font compatibility review — proposed design

[한국어](FONT_COMPATIBILITY_REVIEW.ko.md)

This is a measured design proposal, not an implemented GUI or an accepted
cross-platform document conversion. The renderer and authored document remain
unchanged. No font installation is required for the Windows preview plan below.

## What should be checked

Check each actual exported text run and its character subset, face and style.
A document may legitimately use several fonts. A single-family coverage rule
would reject the valid source: its 316 spans all have glyphs in their assigned
Mac faces. It already separates one `₆` and six `−` instances into Helvetica;
other captions use Apple SD Gothic Neo and atom/mark runs use Arial. The 169
unique characters include 98 precomposed Hangul syllables and no combining marks.
Greek `Δ`, dagger `‡`, superscript `⁻` and subscript digits must be distinguished
from ordinary Korean/Latin text; they are not all generic missing symbols.

For the current Windows target, Apple/Helvetica requests become logical Arial.
Actual native EMF controls show Gulim for Korean and Microsoft Sans Serif for
some superscript/subscript fallback. The text is rendered, but the original
physical fonts and layout are not thereby preserved. A font-table name and an
operating-system request that resolves successfully do not prove face identity.
The WPF name Gill Sans resolves here to Gill Sans Ultra Bold; it was omitted by
the earlier GDI-only name intersection. Name inventories must state their source.

## Proposed warning and choices

When reviewing a CDXML export for a declared target, show one scoped message:
“This document renders on this Mac. The selected Windows target substitutes
Apple SD Gothic Neo and Helvetica; matching appearance and layout are unverified.”
Do not report all 169 characters as missing or require a new font installation.
Keep editing and ordinary export available, retaining the existing strict
consumer-acceptance gate. An unknown target profile is “not verified”, not “font
missing”. Expected source fallback is normal and is not itself a warning.

Offer two explicit choices, with the first selected by default:

1. **Keep original typography.** Preserve every source font/run and continue with
   the existing authored document. Target substitutions remain disclosed.
2. **Preview a separate Windows derivative.** Use only verified existing target
   faces, showing the actual affected title, Korean caption, formula and symbols.
   This is a preview until the user explicitly chooses to create a new copy.

The measured Windows plan uses Malgun Gothic regular/bold as the primary face
and Tahoma for `⁻`, `₆` and `−`, which its physical Malgun faces lack. The union
covers all 169 source characters. Twelve actual ChemDraw controls compare six
original requests with six explicit-plan counterparts: `FPh / OMe`,
`Ar = 4-FC₆H₄`, a Korean caption, `ΔGcomp`, `(kcal mol⁻¹)` and `−50`. These controls
preserve text and style intent; they do not establish whole-document layout or
Mac appearance equivalence. Do not convert Unicode symbols into different text
or use a synthetic bold silently.

## Preview provenance and review

Show the source Mac render, actual target render with its current substitutions,
and an explicitly labelled target-plan render. Include measured face names,
versions and style plus where fallback begins; disclose unavailable target
rendering. A Mac without Malgun Gothic must not display its own implicit
fallback as a genuine Malgun preview. In that situation, inspect an actual target
render or show “target preview unavailable”. The native controls in the review
bundle are document exports, not screenshots or a new UI implementation.

For any derivative, preserve character sequence and run styling, compare glyph
coverage, origins, baselines, wrapping, overlap and bounds, then run the existing
strict native reference checks against the newly authored derivative. Keep
source acceptance and derivative acceptance separate. A character-coverage pass
must not become a whole-document fidelity pass.

## Ownership and persistence proposal

Reuse the exporter's shaped-run segmentation, UTF-16/cluster refusal rules and
actual raw fonts. Store evidence by source hash, target environment, font face
version and run text; invalidate it when those change. Separate “requested face
absent”, “characters missing in resolved face”, “unexpected physical fallback”,
and “layout not measured”. Data inspection should be side-effect-free. UI and
platform adapters may collect host font data; pure export features should consume
typed observations and must not import Qt, query remote hosts or install fonts.

Apply an accepted plan to a clone using existing text-formatting/document owners,
with an explicit new output path and the existing no-overwrite contract. Do not
change global defaults, map all Arial/Helvetica names together, rewrite an open
source document or loosen validation. A same-document action, if later designed,
would need its own explicit user intent and one reversible history transaction.
No schema, UI, native bridge or automatic font-mapping behavior is implemented by
this proposal.
