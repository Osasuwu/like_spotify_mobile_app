"""Windows host — tray + global hotkey, the default flavor.

Owns the Win32 side effects: tray icon, single-instance mutex, balloon
notifications, `winsound` beep feedback, and the `HKCU\\…\\Run` autostart
toggle. Anything cross-platform lives in `hosts/_common.py` so the
`_stub.py` host (mac/linux CLI) can share it.

Slice history:
    #21 — original tray launcher.
    #27 — renamed from `hosts/tray.py`; cross-platform helpers and the
          `like-once` subcommand split out so the same entry point works
          on every OS.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import threading
import time
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


class TrayFeedback:
    """Owns the tray icon + flash / beep / balloon feedback."""

    def __init__(self, hotkey: str) -> None:
        self._hotkey = hotkey
        self._icon_default = _make_heart_icon(_ICON_GREEN)
        self._icon_success = _make_heart_icon(_ICON_WHITE)
        self._icon_error = _make_heart_icon(_ICON_RED)
        self._icon = None  # set in run()

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

        Uses `MessageBeep` (plays a system event sound via the default
        output) rather than `Beep` (a PC-speaker / system-timer tone that
        is silent on most modern laptops — the root cause of "no sound").
        Distinct tones per outcome so like / remove / error are
        distinguishable without looking at the tray:

            like   → MB_ICONASTERISK   (0x40)
            remove → MB_ICONEXCLAMATION (0x30)
            error  → MB_ICONHAND        (0x10)
        """
        import winsound

        if not success:
            winsound.MessageBeep(0x10)
        elif kind == "remove":
            winsound.MessageBeep(0x30)
        else:
            winsound.MessageBeep(0x40)

    @property
    def default_icon(self):
        return self._icon_default


# ── Autostart ──────────────────────────────────────────────────────────


_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "LikeSpotify"


def _autostart_target() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    # Source / pipx install: launch through the interpreter that's running
    # us (the pipx venv when installed that way). Prefer pythonw.exe so the
    # tray app starts at login without a console window flashing on screen;
    # fall back to python.exe if the GUI interpreter isn't present.
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else exe
    return f'"{runner}" -m like_spotify'


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
        f"frozen={getattr(sys, 'frozen', False)} argv={sys.argv[1:]}"
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

    feedback = TrayFeedback(hotkey=hotkey)
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
