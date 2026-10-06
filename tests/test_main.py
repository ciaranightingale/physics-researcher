"""The local stdio entry point's database location.

The one rule that matters here: the default must be absolute. The client chooses the working
directory, so a relative default would quietly give a different videos log per directory, and a
missing log reads as "no story is covered yet" rather than as an error.
"""

from pathlib import Path

from science_scout.__main__ import default_db_path


def test_default_is_absolute(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert default_db_path().is_absolute()


def test_default_sits_under_the_home_directory(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert default_db_path() == Path.home() / ".local" / "share" / "science-scout" / "scout.db"


def test_xdg_data_home_is_honoured(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg")
    assert default_db_path() == Path("/tmp/xdg/science-scout/scout.db")
