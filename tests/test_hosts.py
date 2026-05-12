"""Host-selection + stub-host behaviour.

Slice: #27 (host split + cross-platform `like-once`).

We only smoke the platform-dispatch logic and the CLI failure paths of
the stub host — the resident tray path needs a Win32 desktop and lives
behind an integration / manual-test boundary.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest

from like_spotify.hosts import _stub, select_host


# ── select_host() dispatch ─────────────────────────────────────────────


def test_select_host_picks_windows_on_win32() -> None:
    with patch("like_spotify.hosts.sys.platform", "win32"):
        host = select_host()
    assert host.__module__ == "like_spotify.hosts.windows"


@pytest.mark.parametrize("platform", ["darwin", "linux", "freebsd"])
def test_select_host_picks_stub_off_win32(platform: str) -> None:
    with patch("like_spotify.hosts.sys.platform", platform):
        host = select_host()
    assert host.__module__ == "like_spotify.hosts._stub"


# ── Stub host: surface CLI failures cleanly ────────────────────────────


@pytest.fixture
def empty_config(tmp_path, monkeypatch) -> Iterator[None]:
    """Point the shared config helpers at a writable tmp dir so the test
    runs hermetically (no `~/.like_spotify` reads/writes)."""
    cfg_file = tmp_path / "config.json"
    token_file = tmp_path / "spotify_token.json"
    monkeypatch.setattr("like_spotify.hosts._common.CONFIG_FILE", cfg_file)
    monkeypatch.setattr("like_spotify.hosts._common.SPOTIFY_TOKEN_FILE", token_file)
    yield


def test_stub_run_without_client_id_prints_hint_and_exits(
    empty_config, capsys, monkeypatch
) -> None:
    """No `--setup` yet: the default `run` should explain itself, not crash."""
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.setattr("like_spotify.hosts._stub.sys.platform", "darwin")

    rc = _stub.main([])

    assert rc == 2
    err = capsys.readouterr().err
    # macOS hint mentions like-once and the macos.py file.
    assert "like-once" in err
    assert "macos.py" in err


def test_stub_like_once_without_client_id_exits_with_setup_hint(
    empty_config, capsys, monkeypatch
) -> None:
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    rc = _stub.main(["like-once"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--setup" in err


def test_stub_config_subcommand_prints_paths(empty_config, capsys) -> None:
    rc = _stub.main(["--config"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Config:" in out
    assert "Spotify token:" in out


# ── CliFeedback formatting ─────────────────────────────────────────────


def test_cli_feedback_success_goes_to_stdout(capsys) -> None:
    fb = _stub.CliFeedback()
    fb(True, "Liked", "Song — Artist")
    out, err = capsys.readouterr()
    assert "[ok] Liked — Song — Artist" in out
    assert err == ""
    assert fb.calls == [(True, "Liked", "Song — Artist")]


def test_cli_feedback_failure_goes_to_stderr(capsys) -> None:
    fb = _stub.CliFeedback()
    fb(False, "Like failed", "boom")
    out, err = capsys.readouterr()
    assert "[err] Like failed — boom" in err
    assert out == ""


def test_cli_feedback_omits_dash_when_message_empty(capsys) -> None:
    fb = _stub.CliFeedback()
    fb(False, "Nothing playing", "")
    err = capsys.readouterr().err.strip()
    assert err == "[err] Nothing playing"
