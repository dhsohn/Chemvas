# ADR 0042: Separate Ar display from generic aryl meaning

- Status: Proposed
- Date: 2026-10-11

## Problem

A GenericNickname named Ar is reparsed as argon by ChemDraw 25.0.2.14, including
when InterpretChemically is disabled. Changing the name to Aryl while retaining
Ar text also fails. Display preservation alone is insufficient chemical evidence.

## Decision

Require an explicit typed binding for ambiguous Ar. An element binding remains
Element 18; a generic_aryl binding creates a visible Ar Nickname containing the
documented ARY generic query. The original model is not rewritten. The native
query and its text are distinct from the displayed group label. Keep existing
outer bonds and, when bonded, one shared external point at the first neighbor.
Support the verified zero-to-two connection scope; refuse higher degree. No
specific ring, atom attachment site, or concrete substituent is invented.

Two separate inner external points lost the ARY definition during native save;
one shared point retained it with both original outer bonds. The actual OMe
witness retained all 48 ARY definitions and 238 outer bonds after save/reopen,
including its one two-contact group. A query cannot supply a unique molecular
formula; its corresponding warning remains. Native group expansion and external
query-engine behavior are not established by this representation.

## Evidence and related guard corrections

The CDX NodeType specification defines Nickname/Fragment as visible labels with
an internal fragment and ExternalConnectionPoint for attachment. The ChemDraw
17.1 user guide, Query Structures table (printed page 277), defines ARY as aryl.

- https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Node_Type.htm
- https://www.uni-ulm.de/fileadmin/website_uni_ulm/nawi.chemie/Downloads/ChemOffice/ChemDraw.pdf

Separately, consumer reference validation resolves inherited CaptionJustification
and LabelJustification before legacy Justification, rejects unproved added or
removed NumHydrogens, and compares graphic ArrowType. These are bounded fixes to
three reproduced reference-acceptance defects. Full visual fidelity and GUI
editing/Undo acceptance remain separate work.
