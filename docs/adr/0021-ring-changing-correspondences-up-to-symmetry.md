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
different. At bd6101fd the tests fixed such refusals: breaking any bond of a
cyclohexane to draw a bicyclopropyl
(`test_equal_ring_atom_counts_do_not_bypass_topology_review`), a pentane
laid across a cyclopropane ring in either direction
(`test_complete_copy_still_reviews_ring_crossing_partners`), and the CF3
rotations of a Schreiner thiourea beside a ring-forming substrate, refused
with 25 of its 32 atoms mapped
(`test_ring_change_beside_a_symmetric_catalyst_is_narrowed_by_anchors`).

The review also listed every embedding of each endpoint before applying the
existing mappings, up to the candidate limit of 10,000. The #496 commits
bounded the other searches but left this one, as 4db5b9b1 records: "A
ring-changing step on a connected symmetric structure without a complete copy
still needs every shared atom anchored".
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
onto themselves. The automorphisms keep each atom's drawn element,
formal charge, radical electrons, isotope and hydrogen count and each bond's
order and aromaticity. The drawn element is recorded on every atom the
suggestion builds, because the tolerant build reads an alias such as Me as
carbon. Automorphisms keep ring membership, so correspondences with different
ring signatures never merge and the ring review of #485 stands.

Where the review requires one correspondence, it now requires one class.
Where it does not, a single ring signature across the classes leaves the
choice to the first, as before. Every path that returned a pair at bd6101fd
returns the same pair. The symmetry review replaces the refusals that ended
the other paths: the candidate limit of the complete-copy and full
enumeration searches, the "Too many ring-changing correspondences" refusal,
which is removed, and the pairwise comparison of listed correspondences.

The review places query positions outward from the one with the fewest
candidate pairs. Each position keeps only atoms with a distinct bonded atom
for each of its query neighbours, and an atom that is some position's only
choice leaves every other position. At each position the candidates are cut
to one per class of the automorphisms that fix every atom placed so far: on
each endpoint with the mapped atoms fixed as well, then, when there are
mappings, on both endpoints together with the mapping pairs carried onto
themselves.

A class is decided by a canonical form: the graph, with a mark on each atom
for what the automorphisms keep and for the atoms held in place, relabelled
by RDKit's canonical ranking. Equal forms prove an automorphism, since mapping
the atoms of equal rank onto one another keeps every mark and bond. Symmetry
classes from the ranking with ties left unbroken are not used to merge,
because such invariants can be coarser than the classes of automorphisms.
Correspondences are compared the same way on both endpoints joined by a
zero-order bond for each atom pair, with the mapped atoms marked.

The placements and canonical forms of one review count against the candidate
limit. A review that reaches it ends with the candidate-limit refusal, naming
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
- An asymmetric alternative beside Pd(PPh3)3, beyond the limit of listing
  embeddings, is refused as multiple until it is mapped
  (`test_asymmetric_alternatives_beside_a_symmetric_structure_are_refused`),
  and an anchor no correspondence holds is refused as misaligned
  (`test_anchor_on_a_ligand_that_differs_far_from_it_is_refused_promptly`).
- Mappings that break the symmetry of the shared structure in pieces, one
  ortho carbon in each phenyl ring, end at the candidate limit within five
  seconds (`test_symmetry_review_is_bounded_when_mappings_break_the_symmetry`),
  and the refusal names the mappings on the complete-copy path too
  (`test_fixed_copy_review_at_the_limit_names_the_existing_mappings`).

When this record was written, a differential run against bd6101fd compared
16,000 reviews of steps built from small molecules with random mappings, with
and without the uniqueness requirement: every pair bd6101fd returned was
returned unchanged, and every other suggestion or refusal agreed with a
brute-force count of the classes. That harness is not part of the repository.

Unequal canonical forms keep two classes apart on the assumption that RDKit
ranks isomorphic graphs alike; where it does not, the review refuses a step it
could suggest, and never merges correspondences. The search does not use the
shared structure's own symmetry. Where the mappings break a symmetry of the
endpoints that the shared structure keeps, it meets each correspondence once
per relabelling before the forms merge them, so mappings on scattered atoms of
symmetric ligands can still end at the candidate limit, which bounds the
review to about two and a half seconds on the recording machine.
Stereochemistry is not compared, as in the substructure search itself. The
review does not bound the MCS search, whose five-second timeout RDKit does not
always keep.
