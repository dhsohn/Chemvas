# ADR 0021: Ring-changing correspondences counted up to symmetry

- Status: Accepted
- Date: 2026-09-27

## Problem

The structural suggestion pairs embeddings of the maximum common
substructure (MCS) of a step's reactant and product
(`core/rdkit_correspondence.py`). #485 (a1bb8ea1) let a suggestion cross
ring formation or opening, and its changelog entry states the rule that
followed: "Ambiguous ring-changing matches now request explicit atom mappings
instead of selecting an arbitrary embedding". A step whose ring atom count
changes, or whose anchor-compatible embeddings differ in which query atoms and
bonds lie in rings, was refused with "multiple structural atom
correspondences" as soon as two embedding pairs gave different atom pairs.

That count treated correspondences the drawing cannot tell apart as
different. At a9452997, before this change, the tests fixed such refusals:
breaking any bond of a
cyclohexane to draw a bicyclopropyl
(`test_equal_ring_atom_counts_do_not_bypass_topology_review`), a pentane
laid across a cyclopropane ring in either direction
(`test_complete_copy_still_reviews_ring_crossing_partners`), and the CF3
rotations of a Schreiner thiourea beside a ring-forming substrate, refused
with 25 of its 32 atoms mapped
(`test_ring_change_beside_a_symmetric_catalyst_is_narrowed_by_anchors`).

The review also listed every embedding of each endpoint before applying the
existing mappings, up to the candidate limit of 10,000. #496 (a4329174)
bounded the other searches but left this one, as its commit message records:
"A ring-changing step on a connected symmetric structure without a complete
copy still needs every shared atom anchored".
`test_fully_anchored_ring_change_on_a_connected_symmetric_structure` fixed
that a 5-exo cyclisation on Pd(PPh3)3, whose 64-atom shared structure embeds
in 663,552 ways on each side, ended at the candidate limit with 63 of those
atoms mapped.

On 2026-09-27 the maintainer decided to count these correspondences up to
the symmetry of the drawing, so that partial mappings, or none, can complete
such a step.

## Decision

Two correspondences are the same when an automorphism of the reactant and one
of the product together carry one onto the other and the existing mappings
onto themselves. The mappings are kept as a set of pairs, not atom by atom:
the automorphisms may move a mapped atom when they move its partner to the
partner of its image. Two bonded mapped carbons of a cubane, which the
automorphisms swap together with their partners, therefore leave one
correspondence where holding each in place would leave two. The
automorphisms keep each atom's drawn element, formal charge, radical
electrons, isotope and hydrogen count and each bond's order and aromaticity.
The drawn element is recorded on every atom the suggestion builds, because
the tolerant build reads an alias such as Me as carbon. Bond styles such as
wedge, hash or dotted are not kept, since the build reads bond orders only.
Automorphisms keep ring membership, so correspondences with different ring
signatures never merge and the ring review of #485 stands.

Where the review requires one correspondence, it now requires one class.
Where it does not, a single ring signature across the classes leaves the
choice to the first, as before. The paths that return a pair without that
review are unchanged. When the embeddings were listed, on both endpoints or
on one beside a fixed complete copy, and their pairings stay within the
candidate limit, the listed correspondences are compared directly: a single
correspondence returns the pair it returned before, and several are compared
by canonical form when the budget below covers a form for each. Every pair
returned at a9452997 is therefore returned unchanged. The symmetry search
decides the rest, in place of the refusals at the candidate limit of the
complete-copy and full enumeration searches and of the "Too many
ring-changing correspondences" refusal, which is removed.

The search places query positions outward from the one with the fewest
candidate pairs. Each position keeps only atoms with a distinct bonded atom
for each of its query neighbours, and an atom that is some position's only
choice leaves every other position; a position is checked again only when a
domain it depends on shrinks. At each position the candidates are cut to one
per class of the automorphisms that fix every atom placed so far: on each
endpoint with the mapped atoms fixed as well, then, when there are mappings,
on both endpoints together with the mapping pairs carried onto themselves.

A class is decided by a canonical form: the graph, with a mark on each atom
for what the automorphisms keep and for the atoms held in place, relabelled
by RDKit's canonical ranking. Equal forms prove an automorphism, since mapping
the atoms of equal rank onto one another keeps every mark and bond. Symmetry
classes from the ranking with ties left unbroken are not used to merge,
because such invariants can be coarser than the classes of automorphisms.
Correspondences are compared the same way on both endpoints joined by a
zero-order bond for each atom pair, with the mapped atoms marked.

A review may visit twenty atoms for each candidate the limit allows, 200,000
in all: every atom of a graph brought to canonical form and every atom placed
or checked against a query position counts, so the review's time is bounded
however large the drawing. A search that spends the budget, while narrowing
domains or placing atoms, ends with the candidate-limit refusal, naming
existing mappings when there are any.

## Verification and limits

`tests/test_ring_changing_correspondence.py` covers the decision:

- The 5-exo cyclisation on Pd(PPh3)3 is suggested within five seconds with no
  mapping, with its three reacting carbons mapped, with every shared atom but
  one mapped and with all of them
  (`test_ring_change_on_a_connected_symmetric_structure_is_suggested`), and
  beside a naphthylphosphine, whose fused ring no phenyl ring of the shared
  structure is tried in
  (`test_ring_change_beside_a_naphthylphosphine_is_suggested`).
- Correspondences the drawing relates are suggested
  (`test_ring_changes_equivalent_by_symmetry_are_suggested`,
  `test_ring_change_beside_a_symmetric_catalyst_is_suggested`,
  `test_identical_components_pair_as_one_correspondence`), while alternatives
  a charge, radical, methyl or alias tells apart are still refused: the
  equal-ring-count, ring-crossing, complete-copy and bond-order tests, and
  `test_symmetry_keeps_aliases_apart_from_the_atoms_they_collapse_to`.
- The mappings are compared as a set of pairs, marked and held on each
  endpoint and joined across both, in the listed comparison and in the search
  alike (`test_existing_mappings_are_kept_as_a_set_of_pairs`, including the
  cubane).
- Pairs from listed embeddings are kept where mappings break symmetries the
  shared structure keeps: an aldol beside three diphenylphosphino groups and a
  hemiacetal beside nine or twelve mapped phenyl rings
  (`test_mapped_ligands_that_break_the_symmetry_keep_the_listed_pair`,
  `test_mapped_aryl_rings_along_a_chain_keep_the_listed_pair`).
- Reviews end within two seconds on a 207-atom chain, with and without a
  mapping (`test_ring_change_on_a_long_chain_is_reviewed_promptly`), and on
  thirty mapped phenyl rings, where listing the embeddings reaches the limit.
  An asymmetric alternative beside Pd(PPh3)3 is refused as multiple until it
  is mapped
  (`test_asymmetric_alternatives_beside_a_symmetric_structure_are_refused`),
  and an anchor no correspondence holds is refused as misaligned
  (`test_anchor_on_a_ligand_that_differs_far_from_it_is_refused_promptly`).
- Mappings that break the symmetry of the shared structure in pieces, one
  ortho carbon in each phenyl ring of the 5-exo cyclisation, end at the
  candidate limit within five seconds
  (`test_symmetry_review_is_bounded_when_mappings_break_the_symmetry`), and
  the refusal names the mappings on the complete-copy path too
  (`test_fixed_copy_review_at_the_limit_names_the_existing_mappings`).

When this record was written, differential runs against a9452997 compared
about 12,800 reviews of steps built from small molecules with random
mappings, half of them with a lowered candidate limit, and about 1,700 reviews
of steps on molecules of up to about 70 atoms with a random share of the
shared atoms mapped. Every pair a9452997 returned was returned unchanged, and
where a brute-force count of the classes could be made, every other
suggestion or refusal agreed with it. Those harnesses are not part of the
repository.

Unequal canonical forms keep two classes apart on the assumption that RDKit
ranks isomorphic graphs alike; where it does not, the review refuses a step it
could suggest, and never merges correspondences. The search does not use the
shared structure's own symmetry. Where the mappings break a symmetry of the
endpoints that the shared structure keeps and the embeddings are too many to
list, it meets each correspondence once per relabelling before the forms
merge them, so mappings on scattered atoms of symmetric ligands can still end
at the candidate limit. A review that reaches it took up to about 1.2 seconds
on the recording machine, where listing the embeddings had refused within a
tenth of a second. Stereochemistry is not compared, as in the substructure
search itself. The review does not bound the MCS search, whose five-second
timeout RDKit does not always keep.
