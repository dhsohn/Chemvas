# ADR 0064: Visual arrow-label editing

Status: Accepted

## Context

Desktop arrow labels exposed storage markup even after adding formatting buttons.
The user should edit the rendered text directly.

## Decision

Use a QTextEdit with normal, subscript and superscript character formats. Buttons
toggle the selected format or the format for subsequent input. One shared toolbar
targets the last focused label input, retaining its selection while a control or
symbol menu has focus. Remove the syntax
help, example prose and duplicate preview panes. Keep symbol insertion and
keyboard navigation.

Keep the existing document string contract and web parser. Decode existing labels
into visual runs. Preserve the original value byte-for-byte when its visible runs
are unchanged, including after undo. Serialize changed runs only when parsing the
result reproduces every character and role; reject ambiguous literal marker text
instead of changing its meaning. Keep the existing stored character limit while
showing the limit as a faint placeholder only in empty inputs. Invalid values
show a short error; valid input has no separate counter row.

## Consequences

No document migration is required. Desktop input no longer interprets newly typed
markup. The legacy storage grammar cannot represent every literal underscore or
caret sequence; those edits cannot be accepted until representable. A future
structured label contract would remove that limitation across all consumers.
