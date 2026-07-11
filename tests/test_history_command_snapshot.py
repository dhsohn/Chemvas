from __future__ import annotations

from dataclasses import dataclass

import pytest
from core.history import HistoryCommand
from ui.history_command_snapshot import HistoryCommandSnapshot


class _HostileList(list):
    def __init__(self, values) -> None:
        super().__init__(values)
        self.callback_reads = 0

    def __iter__(self):
        self.callback_reads += 1
        raise KeyboardInterrupt("history payload iterator callback ran")


@dataclass
class _PayloadCommand(HistoryCommand):
    target: object
    payload: list

    def undo(self, canvas) -> None:
        del canvas

    def redo(self, canvas) -> None:
        del canvas


def test_snapshot_uses_raw_container_ports_and_restores_payload_exactly() -> None:
    target = object()
    payload = _HostileList([{"after": (1.0, 2.0)}])
    command = _PayloadCommand(target=target, payload=payload)

    snapshot = HistoryCommandSnapshot.capture(command)
    assert payload.callback_reads == 0

    dict.__setitem__(list.__getitem__(payload, 0), "after", (9.0, 9.0))
    with pytest.raises(RuntimeError, match="history command field"):
        snapshot.verify()

    snapshot.restore()
    snapshot.verify()
    assert payload.callback_reads == 0
    assert list.__getitem__(payload, 0) == {"after": (1.0, 2.0)}


def test_snapshot_rejects_target_identity_replacement() -> None:
    command = _PayloadCommand(target=object(), payload=[])
    snapshot = HistoryCommandSnapshot.capture(command)

    command.target = object()

    with pytest.raises(RuntimeError, match="target.*changed identity"):
        snapshot.verify()
