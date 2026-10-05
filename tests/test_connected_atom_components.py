from chemvas.domain.document import connected_atom_components


def test_shared_components_preserve_sparse_ids_and_ignore_nonlive_edges():
    atoms = [19, 2, 7, 31, 45]
    bonds = [(19, 2), (2, 19), (7, 7), (31, 999), (999, 45)]
    assert connected_atom_components(iter(atoms), iter(bonds)) == (
        (2, 19),
        (7,),
        (31,),
        (45,),
    )
    assert connected_atom_components([], []) == ()


def test_disconnected_seed_traversal_does_not_rescan_remaining_atoms_quadratically():
    class CountedId(int):
        comparisons = 0

        def __lt__(self, other):
            type(self).comparisons += 1
            return super().__lt__(other)

    count = 512
    atoms = [CountedId(index) for index in range(count)]
    assert connected_atom_components(atoms, []) == tuple(
        (index,) for index in range(count)
    )
    # A sorted seed pass is well within this bound; repeated min(remaining)
    # needs count*(count-1)/2 comparisons. No wall-clock timing in the gate.
    assert CountedId.comparisons < count * 16
