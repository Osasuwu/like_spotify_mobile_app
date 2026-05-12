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
import sys
import threading
import time
from pathlib import Path

from like_spotify.core.pipeline import Pipeline
from like_spotify.extensions.one_shot_cli_trigger import (
    TRIGGER as make_one_shot_cli_trigger,
)
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

    def __call__(self, success: bool, title: str, message: str) -> None:
        threading.Thread(target=self._beep, args=(success,), daemon=True).start()
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

    def _beep(self, success: bool) -> None:
        import winsound

        if success:
            winsound.Beep(880, 80)
            winsound.Beep(1100, 80)
        else:
            winsound.Beep(300, 200)

    @property
    def default_icon(self):
        return self._icon_default


# ── Autostart ──────────────────────────────────────────────────────────


_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "LikeSpotify"


def _autostart_target() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    return f'"{sys.executable}" -m like_spotify'


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


# ── like-once subcommand (Windows still supports it) ───────────────────


def _run_like_once() -> int:
    cfg = _common.load_config()
    client_id = _common.resolve_client_id(cfg)
    if not client_id:
        _msgbox(
            "Not configured. Run from a terminal:\n\n    like-spotify --setup\n",
            title="Like Spotify — setup required",
        )
        return 2

    provider = _common.make_provider(client_id)
    if not provider.has_tokens:
        _msgbox(
            "Not authenticated. Run from a terminal:\n\n    like-spotify --setup\n",
            title="Like Spotify — auth required",
        )
        return 2

    feedback = CliFeedback()
    storage = _common.build_storage(cfg)
    post_actions = _common.build_post_actions(cfg, storage)
    pipeline = Pipeline(
        provider=provider,
        feedback=feedback,
        storage=storage,
        post_like_actions=post_actions,
    )
    trigger = make_one_shot_cli_trigger()

    async def emit() -> None:
        await pipeline.run_once()

    async def run() -> None:
        try:
            await trigger.start(emit)
        finally:
            await trigger.stop()

    asyncio.run(run())

    if not feedback.calls:
        return 1
    return 0 if feedback.calls[-1][0] else 1


# ── Main ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    args = _common.parse_args(argv if argv is not None else sys.argv[1:])

    if args.config:
        return _common.print_config_paths()
    if args.setup:
        return _common.do_setup()
    if args.command == "like-once":
        return _run_like_once()

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

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()

    async def emit() -> None:
        await pipeline.run_once()

    asyncio.run_coroutine_threadsafe(trigger.start(emit), loop).result()

    # Tray menu (runs on the calling thread — main).
    import pystray  # local import: heavy

    def on_like(_icon, _item):
        asyncio.run_coroutine_threadsafe(pipeline.run_once(), loop)

    def on_toggle_autostart(icon, _item):
        _autostart_set(not _autostart_enabled())
        icon.update_menu()

    def on_quit(icon, _item):
        try:
            asyncio.run_coroutine_threadsafe(trigger.stop(), loop).result(timeout=2)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)
        icon.stop()

    menu_items: list = [
        pystray.MenuItem(
            f"Like current track  [{hotkey.upper()}]", on_like, default=True
        ),
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
        try:
            icon.notify(
                f"Press {hotkey.upper()} to like the current track",
                "Like Spotify",
            )
        except Exception:
            pass

    threading.Thread(target=_startup_notify, daemon=True).start()

    icon.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
