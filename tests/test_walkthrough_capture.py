"""Documentation captures cannot read or write a user's recovery profile."""

import os
from unittest.mock import Mock

import pytest
from scripts import walkthrough_capture

from chemvas.ui.session import app_data_paths


@pytest.mark.parametrize("fail", [False, True])
def test_capture_profile_isolated_and_restored_on_failure(tmp_path, monkeypatch, fail):
    outside = tmp_path / "existing-profile"
    outside.mkdir()
    recent = outside / "recent.json"
    recent.write_text('{"paths": ["keep.cdxml"]}')
    monkeypatch.setattr(app_data_paths, "_candidate_dirs", lambda: [outside])
    monkeypatch.setenv("XDG_DATA_HOME", str(outside))
    monkeypatch.setattr(walkthrough_capture, "QApplication", Mock())
    used = []

    def capture(_app):
        isolated = app_data_paths.app_data_dir()
        used.append(isolated)
        assert isolated != outside
        assert not app_data_paths.existing_session_roots()
        app_data_paths.recent_documents_file().write_text("capture-only")
        app_data_paths.sessions_dir().joinpath("capture.json").write_text("temporary")
        assert app_data_paths.existing_session_roots() == (
            (isolated / "sessions").resolve(),
        )
        if fail:
            raise RuntimeError("capture failed")

    if fail:
        with pytest.raises(RuntimeError, match="capture failed"):
            walkthrough_capture.run_with_profile(tmp_path, capture, command="test")
    else:
        assert (
            walkthrough_capture.run_with_profile(tmp_path, capture, command="test") == 0
        )

    assert used and not used[0].exists()
    assert app_data_paths.app_data_dir() == outside
    assert os.environ["XDG_DATA_HOME"] == str(outside)
    assert recent.read_text() == '{"paths": ["keep.cdxml"]}'
    assert sorted(p.name for p in outside.iterdir()) == ["recent.json"]
