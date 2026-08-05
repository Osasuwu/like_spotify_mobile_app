"""Windows host — tray + global hotkey, the default flavor.

Owns the Win32 side effects: tray icon, single-instance mutex, balloon
notifications, synthesized-tone beep feedback, and the `HKCU\\…\\Run`
autostart toggle. Anything cross-platform lives in `hosts/_common.py` so
the `_stub.py` host (mac/linux CLI) can share it.

Slice history:
    #21 — original tray launcher.
    #27 — renamed from `hosts/tray.py`; cross-platform helpers and the
          `like-once` subcommand split out so the same entry point works
          on every OS.
    #53 — swapped `MessageBeep` for a synthesized tone played via
          `PlaySound(..., SND_MEMORY)` (see `_synth_tone` below).
"""

from __future__ import annotations

import asyncio
import ctypes
import math
import os
import struct
import sys
import threading
import time
from array import array
from pathlib import Path

from like_spotify.core.pipeline import Pipeline
from like_spotify.extensions.tray_hotkey_trigger import (
    DEFAULT_HOTKEY,
    TRIGGER as make_tray_hotkey_trigger,
)

from . import _common
from ._stub import CliFeedback

# ── Single-instance guard ──────────────────────────────────────────────


def _ensure_single_instance() -> None:
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, True, "LikeSpotify_SingleInstance")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)


# ── Tray icon + feedback ───────────────────────────────────────────────


def _make_heart_icon(color: tuple[int, int, int]):
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    d.ellipse([s * 0.05, s * 0.10, s * 0.52, s * 0.57], fill=color)
    d.ellipse([s * 0.48, s * 0.10, s * 0.95, s * 0.57], fill=color)
    d.polygon(
        [(s * 0.02, s * 0.38), (s * 0.50, s * 0.95), (s * 0.98, s * 0.38)],
        fill=color,
    )
    return img


_ICON_GREEN = (30, 215, 96)
_ICON_WHITE = (255, 255, 255)
_ICON_RED = (255, 60, 60)


_TONE_SAMPLE_RATE = 44100


def _synth_tone(segments: list[tuple[int, int]], volume: float = 1.0) -> bytes:
    """Render (frequency_hz, duration_ms) segments to an in-memory PCM16
    mono WAV buffer, playable via `winsound.PlaySound(..., SND_MEMORY)`.

    Exists because the two built-in `winsound` options both failed on
    real hardware: `MessageBeep` plays a named system-event sound, which
    Focus Assist / Do Not Disturb suppresses like any notification sound;
    `Beep` drives the legacy PC-speaker/timer tone, which modern audio
    codecs leave unwired to the physical speakers (confirmed silent here —
    only a brief hiccup in whatever else was playing). A synthesized tone
    plays as an ordinary audio-session buffer instead, mirroring the
    phone's `ToneGenerator(AudioManager.STREAM_MUSIC, ...)` feedback
    (`FeedbackPlayer.kt`) rather than routing through any OS notification
    channel.

    `volume` (0.0-1.0, see `_common.resolve_feedback_volume`) scales a
    24000-peak waveform, so 0.5 reproduces the level this shipped at
    before the setting existed.
    """
    peak = 24000 * max(0.0, min(1.0, volume))
    fade = int(_TONE_SAMPLE_RATE * 0.005)  # 5ms fade in/out — avoids clicks
    gap = int(_TONE_SAMPLE_RATE * 0.03)  # 30ms silence between notes
    samples = array("h")
    for freq, duration_ms in segments:
        n = int(_TONE_SAMPLE_RATE * duration_ms / 1000)
        for i in range(n):
            amp = 1.0
            if i < fade:
                amp = i / fade
            elif i > n - fade:
                amp = (n - i) / fade
            value = math.sin(2 * math.pi * freq * i / _TONE_SAMPLE_RATE)
            samples.append(int(value * amp * peak))
        samples.extend([0] * gap)
    data = samples.tobytes()
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        1,  # mono
        _TONE_SAMPLE_RATE,
        _TONE_SAMPLE_RATE * 2,  # byte rate (16-bit mono)
        2,  # block align
        16,  # bits per sample
        b"data",
        len(data),
    )
    return header + data


def _synth_tones(volume: float) -> dict[str, bytes]:
    """Rising two-note chime (like), a single mid tone (remove), a low
    double buzz (error) — distinct enough to tell apart without looking
    at the tray. Rebuilt per `TrayFeedback` instance so `volume` (from
    `trigger.feedback_volume`) takes effect.
    """
    return {
        "like": _synth_tone([(784, 90), (1175, 110)], volume=volume),
        "remove": _synth_tone([(587, 150)], volume=volume),
        "error": _synth_tone([(220, 90), (220, 90)], volume=volume),
    }


class TrayFeedback:
    """Owns the tray icon + flash / beep / balloon feedback."""

    def __init__(
        self, hotkey: str, volume: float = _common.DEFAULT_FEEDBACK_VOLUME
    ) -> None:
        self._hotkey = hotkey
        self._icon_default = _make_heart_icon(_ICON_GREEN)
        self._icon_success = _make_heart_icon(_ICON_WHITE)
        self._icon_error = _make_heart_icon(_ICON_RED)
        self._icon = None  # set in run()
        self._tones = _synth_tones(volume)

    def attach(self, icon) -> None:
        self._icon = icon

    def __call__(
        self, success: bool, title: str, message: str, *, kind: str = "like"
    ) -> None:
        threading.Thread(
            target=self._beep, args=(success, kind), daemon=True
        ).start()
        threading.Thread(target=self._flash, args=(success,), daemon=True).start()
        if self._icon is not None:
            try:
                self._icon.notify(message or title, "Like Spotify")
            except Exception:
                pass

    def _flash(self, success: bool) -> None:
        if self._icon is None:
            return
        self._icon.icon = self._icon_success if success else self._icon_error
        time.sleep(0.4)
        self._icon.icon = self._icon_default

    def _beep(self, success: bool, kind: str) -> None:
        """Audible confirmation through the default sound device.

        Plays a synthesized tone (`_synth_tone`, see module docstring) via
        `PlaySound(..., SND_MEMORY)` rather than `MessageBeep` or `Beep` —
        both proved unreliable/silent on real hardware. Distinct tones per
        outcome so like / remove / error are distinguishable without
        looking at the tray.
        """
        import winsound

        if not success:
            tone = self._tones["error"]
        elif kind == "remove":
            tone = self._tones["remove"]
        else:
            tone = self._tones["like"]
        winsound.PlaySound(tone, winsound.SND_MEMORY | winsound.SND_ASYNC)

    @property
    def default_icon(self):
        return self._icon_default


# ── Autostart ──────────────────────────────────────────────────────────


_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "LikeSpotify"


def _resident_launch_command() -> str:
    """The bare command that starts the resident tray (interpreter + module).

    Prefers `pythonw.exe` so no console attaches in the common case; falls
    back to `python.exe` when the GUI interpreter isn't beside it. The
    autostart path wraps this again to stay hidden even when the venv
    redirector re-execs the console interpreter at login — see
    `_autostart_target`.
    """
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else exe
    return f'"{runner}" -m like_spotify'


def _autostart_vbs_path() -> Path:
    """Where the hidden-launch VBScript lives — next to config/tokens."""
    return _common.CONFIG_FILE.parent / "autostart_hidden.vbs"


def _write_autostart_vbs() -> Path:
    """Write a VBScript that launches the tray with a hidden window.

    Why this exists: at login the pipx / pythoncore venv `pythonw.exe` is a
    redirector that re-execs the *console* `python.exe` (confirmed in
    startup.log — every real login logged `exe=…python.exe`), so a console
    window appears despite Run pointing at `pythonw.exe`. The `pythonw`
    preference alone can't win against the redirector's interpreter choice.

    `WScript.Shell.Run(cmd, 0, False)` starts the process with `SW_HIDE`,
    which the redirector forwards to the real interpreter — no console, no
    flash. Only the autostart path goes through this; running `like-spotify`
    from a terminal is unaffected (it never touches the VBScript).
    """
    cmd = _resident_launch_command()
    # VBScript string literals escape a double-quote by doubling it.
    arg = '"' + cmd.replace('"', '""') + '"'
    vbs = (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f"sh.Run {arg}, 0, False\r\n"
    )
    path = _autostart_vbs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(vbs, encoding="utf-8")
    return path


def _autostart_target() -> str:
    """Registry Run value: launch the tray fully hidden at login.

    A frozen windowed exe has no console, so it's launched directly. For the
    source / pipx install we route through `wscript.exe` + a hidden-launch
    VBScript so the console interpreter the venv redirector picks at login
    never shows a window.
    """
    if getattr(sys, "frozen", False):
        return _resident_launch_command()
    vbs = _write_autostart_vbs()
    return f'wscript.exe //B //Nologo "{vbs}"'


def _autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, _AUTOSTART_NAME)
        return True
    except FileNotFoundError:
        return False


def _autostart_set(enabled: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, _AUTOSTART_NAME, 0, winreg.REG_SZ, _autostart_target())
        else:
            try:
                winreg.DeleteValue(k, _AUTOSTART_NAME)
            except FileNotFoundError:
                pass


# ── Error reporting ────────────────────────────────────────────────────


def _msgbox(text: str, title: str = "Like Spotify", icon: int = 0x10) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, icon)
        return
    except Exception:
        pass
    _common.msgbox(text, title)


# ── one-shot subcommands (Windows still supports them) ─────────────────


def _resolved_provider_or_hint():
    """(provider, None, cfg) when ready, else (None, exit_code, cfg) after a
    hint box. Mirrors the `_stub.py` copy — cfg is returned either way so the
    caller can build the pipeline without reloading config."""
    cfg = _common.load_config()
    client_id = _common.resolve_client_id(cfg)
    if not client_id:
        _msgbox(
            "Not configured. Run from a terminal:\n\n    like-spotify --setup\n",
            title="Like Spotify — setup required",
        )
        return None, 2, cfg
    provider = _common.make_provider(client_id)
    if not provider.has_tokens:
        _msgbox(
            "Not authenticated. Run from a terminal:\n\n    like-spotify --setup\n",
            title="Like Spotify — auth required",
        )
        return None, 2, cfg
    return provider, None, cfg


def _run_like_once() -> int:
    provider, err, cfg = _resolved_provider_or_hint()
    if provider is None:
        return err

    feedback = CliFeedback()
    storage = _common.build_storage(cfg)
    post_actions = _common.build_post_actions(cfg, storage)
    pipeline = Pipeline(
        provider=provider,
        feedback=feedback,
        storage=storage,
        post_like_actions=post_actions,
    )
    return _common.run_one_shot(pipeline, feedback)


def _run_remove_once() -> int:
    provider, err, cfg = _resolved_provider_or_hint()
    if provider is None:
        return err

    feedback = CliFeedback()
    pipeline = _common.build_remove_pipeline(cfg, provider, feedback)
    if pipeline is None:
        _msgbox(
            "No archive playlist configured. Run from a terminal:\n\n"
            "    like-spotify --setup\n",
            title="Like Spotify — setup required",
        )
        return 2
    return _common.run_one_shot(pipeline, feedback)


# ── Startup logging + shell-readiness ──────────────────────────────────
#
# The resident tray is launched at login by the HKCU\…\Run key through
# pythonw.exe — no console, so a crash or a lost tray-icon add leaves no
# trace and the heart silently never appears ("снова не запустилось").
# Two coupled defenses:
#   1. `_log` — append the launch context + any fatal traceback to a file,
#      so the *next* failed boot is diagnosable by fact, not by guess.
#   2. `_wait_for_shell` — at login the Run entry can fire before explorer
#      has created the notification area (`Shell_TrayWnd`); adding the icon
#      then is silently dropped. Block until the taskbar exists so we stop
#      racing the shell. Post-login the window is already up → returns at
#      once. The race is timing-dependent, which is why autostart works on
#      one boot and not the next.


def _log(msg: str) -> None:
    """Append one timestamped line to `<config-dir>/startup.log` (best effort).

    Path is derived from `_common.CONFIG_FILE` so tests that redirect the
    config dir capture the log too, and so it sits next to config/tokens.
    Never raises — logging must not be the thing that kills startup.
    """
    try:
        log_file = _common.CONFIG_FILE.parent / "startup.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"{ts} [pid {os.getpid()}] {msg}\n")
    except Exception:
        pass


def _taskbar_present() -> bool:
    """True when the shell notification area window exists.

    Injectable seam: `_wait_for_shell` is the loop worth testing, and it
    polls through here so tests can drive readiness without a real desktop.
    """
    return bool(ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None))


def _console_state() -> str:
    """Describe this process's console window for the launch log.

    The autostart fix hinges on *not* getting a visible console at login
    (the pipx/pythoncore venv redirector re-execs the console interpreter —
    see `_write_autostart_vbs`). Recording the console HWND and its
    visibility makes the fix self-verifying: `hwnd=0` means a windowed
    interpreter (ideal), `visible=False` means a console exists but is
    hidden (the VBScript did its job). Best effort — never raises.
    """
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        visible = bool(hwnd) and bool(ctypes.windll.user32.IsWindowVisible(hwnd))
        return f"console_hwnd={hwnd} console_visible={visible}"
    except Exception:
        return "console_hwnd=? console_visible=?"


def _wait_for_shell(timeout: float = 60.0, interval: float = 0.5) -> bool:
    """Block until the taskbar exists, or `timeout` seconds pass.

    Returns True if the shell came up in time, False on timeout (or if the
    shell API is unavailable — then we don't block, just proceed). Polls
    every `interval` seconds. Returns immediately when the taskbar is
    already present (the normal post-login case).
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            if _taskbar_present():
                return True
        except Exception:
            # No Win32 shell API (non-Windows / unusual host) — don't hang.
            return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


# ── Main ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    args = _common.parse_args(argv if argv is not None else sys.argv[1:])

    if args.config:
        return _common.print_config_paths()
    if args.setup:
        return _common.do_setup(reauth=args.reauth)
    if args.command == "like-once":
        return _run_like_once()
    if args.command == "remove-once":
        return _run_remove_once()

    # Resident tray host — the login-launched path. Log the launch context
    # and funnel any startup crash to the log before pythonw lets it die
    # silently (the whole reason "снова не запустилось" left no trace).
    _log(
        f"launch — cwd={os.getcwd()} exe={sys.executable!r} "
        f"frozen={getattr(sys, 'frozen', False)} argv={sys.argv[1:]} "
        f"{_console_state()}"
    )
    try:
        return _run_resident_host()
    except SystemExit:
        raise  # single-instance guard / normal exit — not a fault
    except BaseException:
        import traceback

        _log("FATAL during resident host startup:\n" + traceback.format_exc())
        raise


def _run_resident_host() -> int:
    cfg = _common.load_config()
    client_id = _common.resolve_client_id(cfg)
    if not client_id:
        _msgbox(
            "Not configured. Run from a terminal:\n\n    like-spotify --setup\n",
            title="Like Spotify — setup required",
        )
        return 2

    _ensure_single_instance()
    hotkey = cfg.get("trigger", {}).get("hotkey", DEFAULT_HOTKEY)

    provider = _common.make_provider(client_id)
    if not provider.has_tokens:
        _msgbox(
            "Not authenticated. Run from a terminal:\n\n    like-spotify --setup\n",
            title="Like Spotify — auth required",
        )
        return 2

    feedback = TrayFeedback(
        hotkey=hotkey, volume=_common.resolve_feedback_volume(cfg)
    )
    storage = _common.build_storage(cfg)
    post_actions = _common.build_post_actions(cfg, storage)
    pipeline = Pipeline(
        provider=provider,
        feedback=feedback,
        storage=storage,
        post_like_actions=post_actions,
    )
    trigger = make_tray_hotkey_trigger(hotkey=hotkey)

    # ── Second hotkey: remove-without-like (only when an archive is set) ──
    # Skip when no archive playlist is configured (nothing to remove from)
    # or when the remove hotkey collides with the like hotkey — registering
    # two handlers on one combo would fire both pipelines per press.
    remove_hotkey = _common.resolve_remove_hotkey(cfg)
    remove_pipeline = _common.build_remove_pipeline(cfg, provider, feedback)
    remove_enabled = remove_pipeline is not None and remove_hotkey != hotkey
    remove_trigger = (
        make_tray_hotkey_trigger(hotkey=remove_hotkey) if remove_enabled else None
    )

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()

    async def emit() -> None:
        await pipeline.run_once()

    async def emit_remove() -> None:
        await remove_pipeline.run_once()

    asyncio.run_coroutine_threadsafe(trigger.start(emit), loop).result()
    if remove_trigger is not None:
        asyncio.run_coroutine_threadsafe(
            remove_trigger.start(emit_remove), loop
        ).result()

    # Tray menu (runs on the calling thread — main).
    import pystray  # local import: heavy

    def on_like(_icon, _item):
        asyncio.run_coroutine_threadsafe(pipeline.run_once(), loop)

    def on_remove(_icon, _item):
        asyncio.run_coroutine_threadsafe(remove_pipeline.run_once(), loop)

    def on_toggle_autostart(icon, _item):
        _autostart_set(not _autostart_enabled())
        icon.update_menu()

    def on_quit(icon, _item):
        for t in (trigger, remove_trigger):
            if t is None:
                continue
            try:
                asyncio.run_coroutine_threadsafe(t.stop(), loop).result(timeout=2)
            except Exception:
                pass
        loop.call_soon_threadsafe(loop.stop)
        icon.stop()

    menu_items: list = [
        pystray.MenuItem(
            f"Like current track  [{hotkey.upper()}]", on_like, default=True
        ),
    ]
    if remove_enabled:
        menu_items.append(
            pystray.MenuItem(
                f"Remove from archive  [{remove_hotkey.upper()}]", on_remove
            )
        )
    menu_items += [
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Start with Windows",
            on_toggle_autostart,
            checked=lambda _item: _autostart_enabled(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    ]

    icon = pystray.Icon(
        name="LikeSpotify",
        icon=feedback.default_icon,
        title=f"Like Spotify  [{hotkey.upper()}]",
        menu=pystray.Menu(*menu_items),
    )
    feedback.attach(icon)

    def _startup_notify():
        time.sleep(0.5)
        msg = f"Press {hotkey.upper()} to like the current track"
        if remove_enabled:
            msg += f"\n{remove_hotkey.upper()} removes it from the archive"
        try:
            icon.notify(msg, "Like Spotify")
        except Exception:
            pass

    # Don't race the shell: at login the Run entry can fire before explorer
    # has built the notification area, and the icon add is then silently
    # dropped — process alive, no heart. Wait for the taskbar first.
    if _wait_for_shell():
        _log("shell ready — entering tray loop")
    else:
        _log("Shell_TrayWnd absent after 60s — adding tray icon anyway, proceeding")

    # Welcome balloon: its 0.5s delay is meant to land just after the icon
    # appears, so start it only now. On a cold boot the shell wait above can
    # run for seconds; firing earlier would call notify() before icon.run()
    # exists, and the balloon would be silently dropped.
    threading.Thread(target=_startup_notify, daemon=True).start()
    icon.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
