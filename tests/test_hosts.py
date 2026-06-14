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

from like_spotify.hosts import _stub, select_host, windows


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


# ── Windows resident-host startup: shell-readiness + logging ───────────
#
# The tray path itself needs a Win32 desktop (manual boundary), but the
# two startup defenses added to fix login-time autostart races are pure
# logic behind injectable seams, so they unit-test on any OS.


def test_wait_for_shell_returns_at_once_when_taskbar_present(monkeypatch) -> None:
    monkeypatch.setattr(windows, "_taskbar_present", lambda: True)
    slept: list[float] = []
    monkeypatch.setattr(windows.time, "sleep", lambda s: slept.append(s))

    assert windows._wait_for_shell() is True
    assert slept == []  # the common post-login case must not block


def test_wait_for_shell_polls_until_taskbar_appears(monkeypatch) -> None:
    states = iter([False, False, True])
    monkeypatch.setattr(windows, "_taskbar_present", lambda: next(states))
    slept: list[float] = []
    monkeypatch.setattr(windows.time, "sleep", lambda s: slept.append(s))

    assert windows._wait_for_shell(interval=0.01) is True
    assert len(slept) == 2  # polled twice before the taskbar came up


def test_wait_for_shell_times_out(monkeypatch) -> None:
    monkeypatch.setattr(windows, "_taskbar_present", lambda: False)
    monkeypatch.setattr(windows.time, "sleep", lambda s: None)

    assert windows._wait_for_shell(timeout=0.0) is False


def test_wait_for_shell_does_not_hang_when_probe_raises(monkeypatch) -> None:
    def boom() -> bool:
        raise OSError("no shell API")

    monkeypatch.setattr(windows, "_taskbar_present", boom)
    assert windows._wait_for_shell() is False


def test_log_appends_line_to_config_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "like_spotify.hosts._common.CONFIG_FILE", tmp_path / "config.json"
    )
    windows._log("hello world")

    log = tmp_path / "startup.log"
    assert log.exists()
    contents = log.read_text(encoding="utf-8")
    assert "hello world" in contents
    assert f"[pid {windows.os.getpid()}]" in contents


def test_log_never_raises_on_bad_path(monkeypatch) -> None:
    # A config dir that can't be created must not take the process down.
    monkeypatch.setattr(
        "like_spotify.hosts._common.CONFIG_FILE", windows.Path("\x00bad") / "c.json"
    )
    windows._log("should be swallowed")  # must not raise


# ── Autostart hidden-launch wrapper ────────────────────────────────────
#
# At login the pipx/pythoncore venv `pythonw.exe` redirector re-execs the
# *console* `python.exe`, so a console window appears despite Run pointing
# at pythonw. The fix routes autostart through `wscript.exe` + a hidden
# VBScript (`SW_HIDE`). The wrapper + quote escaping are pure logic.


def test_write_autostart_vbs_emits_hidden_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "like_spotify.hosts._common.CONFIG_FILE", tmp_path / "config.json"
    )
    monkeypatch.setattr(
        windows, "_resident_launch_command", lambda: '"C:\\py\\pythonw.exe" -m like_spotify'
    )

    path = windows._write_autostart_vbs()

    assert path == tmp_path / "autostart_hidden.vbs"
    vbs = path.read_text(encoding="utf-8")
    assert "WScript.Shell" in vbs
    # SW_HIDE (window style 0), non-blocking — this is what kills the console.
    assert ", 0, False" in vbs
    # Inner double-quotes must be VBScript-escaped (doubled) so the path
    # with spaces survives.
    assert '"""C:\\py\\pythonw.exe"" -m like_spotify"' in vbs


def test_autostart_target_routes_through_wscript(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "like_spotify.hosts._common.CONFIG_FILE", tmp_path / "config.json"
    )
    monkeypatch.setattr(windows.sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        windows, "_resident_launch_command", lambda: '"py.exe" -m like_spotify'
    )

    target = windows._autostart_target()

    assert target.startswith("wscript.exe //B //Nologo ")
    assert "autostart_hidden.vbs" in target
    # The VBScript is written as a side effect so the Run value points at a
    # real file.
    assert (tmp_path / "autostart_hidden.vbs").exists()


def test_autostart_target_frozen_launches_exe_directly(monkeypatch) -> None:
    # A frozen windowed exe has no console — no VBScript indirection needed.
    monkeypatch.setattr(windows.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        windows.sys, "executable", "C:\\app\\LikeSpotify.exe", raising=False
    )

    target = windows._autostart_target()

    assert "wscript" not in target
    assert "LikeSpotify.exe" in target


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


def test_cli_feedback_accepts_kind_keyword(capsys) -> None:
    """The remove pipeline calls feedback with kind="remove"; CLI has no
    audio but must accept (and record) the keyword for parity."""
    fb = _stub.CliFeedback()
    fb(True, "Removed from Archive", "Song — Artist", kind="remove")
    out = capsys.readouterr().out
    assert "[ok] Removed from Archive — Song — Artist" in out
    assert fb.calls == [(True, "Removed from Archive", "Song — Artist")]
    assert fb.kinds == ["remove"]
