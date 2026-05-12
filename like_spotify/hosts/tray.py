"""Tray host — default runtime.

Wires `TrayHotkeyTrigger` + `SpotifyMusicProvider` + `Pipeline` and shows
a system-tray icon with feedback (icon flash + beep + balloon).

CLI:
    like-spotify              # run tray host
    like-spotify --setup      # interactive Client ID + browser OAuth
    like-spotify --config     # show config / token paths
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import sys
import threading
import time
from pathlib import Path

from like_spotify.core.actions import PostLikeAction
from like_spotify.core.pipeline import Pipeline
from like_spotify.core.storage import Storage
from like_spotify.extensions.archive_remove import (
    POST_LIKE_ACTION as make_archive_remove_action,
)
from like_spotify.extensions.follow_artist import (
    POST_LIKE_ACTION as make_follow_artist_action,
)
from like_spotify.extensions.promote_to_best_of import (
    POST_LIKE_ACTION as make_promote_to_best_of_action,
)
from like_spotify.extensions.spotify import MUSIC_PROVIDER as make_spotify_provider
from like_spotify.extensions.supabase_storage import STORAGE as make_supabase_storage
from like_spotify.extensions.tray_hotkey_trigger import (
    DEFAULT_HOTKEY,
    TRIGGER as make_tray_hotkey_trigger,
)

# ── Paths ────────────────────────────────────────────────────────────


def _config_dir() -> Path:
    return Path.home() / ".like_spotify"


CONFIG_FILE = _config_dir() / "config.json"
SPOTIFY_TOKEN_FILE = _config_dir() / "spotify_token.json"


def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(cfg: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ── Single-instance guard (Windows) ──────────────────────────────────


def _ensure_single_instance() -> None:
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, True, "LikeSpotify_SingleInstance")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)


# ── Tray icon + feedback ────────────────────────────────────────────


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
        if sys.platform != "win32":
            return
        import winsound

        if success:
            winsound.Beep(880, 80)
            winsound.Beep(1100, 80)
        else:
            winsound.Beep(300, 200)

    @property
    def default_icon(self):
        return self._icon_default


# ── Storage (optional, soft-fail) ───────────────────────────────────


def _build_storage(cfg: dict) -> Storage | None:
    """Return a Storage impl iff Supabase is configured; else None.

    Acceptance criterion: like still succeeds when storage is unconfigured.
    Pipeline treats `None` as 'counter silently unavailable'.
    """
    supabase = cfg.get("supabase", {}) if isinstance(cfg.get("supabase"), dict) else {}
    url = supabase.get("url") or os.environ.get("SUPABASE_URL", "")
    key = supabase.get("anon_key") or os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None
    try:
        return make_supabase_storage(url=url, anon_key=key)
    except Exception:
        return None


# ── Post-like actions ───────────────────────────────────────────────


def _build_post_actions(
    cfg: dict, storage: Storage | None
) -> list[PostLikeAction]:
    """Compose the default-flavor post-like chain.

    Each action is independently togglable: omit / blank the relevant
    config key OR set `actions.<name>.enabled = false` to skip it.
    """
    actions: list[PostLikeAction] = []
    nested = cfg.get("actions") if isinstance(cfg.get("actions"), dict) else {}

    # ── ArchiveRemoveAction ──────────────────────────────────────────
    archive_cfg = nested.get("archive_remove") if isinstance(nested.get("archive_remove"), dict) else {}
    archive_name = (
        archive_cfg.get("playlist_name")
        or nested.get("archive_playlist_name")
        or cfg.get("archive_playlist_name")  # legacy flat key
        or ""
    )
    if archive_name and archive_cfg.get("enabled", True):
        try:
            actions.append(make_archive_remove_action(playlist_name=archive_name))
        except Exception:
            pass

    # ── PromoteToBestOfAction ────────────────────────────────────────
    best_of_cfg = nested.get("promote_to_best_of") if isinstance(nested.get("promote_to_best_of"), dict) else {}
    best_of_name = (
        best_of_cfg.get("playlist_name")
        or nested.get("best_of_playlist_name")
        or cfg.get("best_of_playlist_name")  # legacy flat
        or ""
    )
    if best_of_name and best_of_cfg.get("enabled", True):
        try:
            actions.append(
                make_promote_to_best_of_action(
                    playlist_name=best_of_name,
                    threshold=int(best_of_cfg.get("threshold", 3)),
                )
            )
        except Exception:
            pass

    # ── FollowArtistAction ───────────────────────────────────────────
    # Requires Storage (uses record_artist_track).
    follow_cfg = nested.get("follow_artist") if isinstance(nested.get("follow_artist"), dict) else {}
    follow_enabled = follow_cfg.get("enabled", True) and storage is not None
    if follow_enabled:
        try:
            actions.append(
                make_follow_artist_action(
                    storage=storage,
                    threshold=int(follow_cfg.get("threshold", 5)),
                )
            )
        except Exception:
            pass

    return actions


# ── Autostart (Windows) ─────────────────────────────────────────────


_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "LikeSpotify"


def _autostart_target() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    return f'"{sys.executable}" -m like_spotify'


def _autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, _AUTOSTART_NAME)
        return True
    except FileNotFoundError:
        return False


def _autostart_set(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, _AUTOSTART_NAME, 0, winreg.REG_SZ, _autostart_target())
        else:
            try:
                winreg.DeleteValue(k, _AUTOSTART_NAME)
            except FileNotFoundError:
                pass


# ── Setup (interactive) ─────────────────────────────────────────────


def _do_setup() -> int:
    print("Like Spotify — interactive setup")
    print("--------------------------------")
    cfg = _load_config()
    current = cfg.get("spotify", {}).get("client_id", "")
    prompt = f"Spotify Client ID [{current[:6] + '…' if current else 'required'}]: "
    entered = input(prompt).strip()
    client_id = entered or current
    if not client_id:
        print("Aborted: client_id is required.", file=sys.stderr)
        print(
            "Get one at https://developer.spotify.com/dashboard and add the redirect URI "
            "http://127.0.0.1:8793/callback to the app.",
            file=sys.stderr,
        )
        return 2

    cfg.setdefault("spotify", {})["client_id"] = client_id
    cfg.setdefault("trigger", {}).setdefault("hotkey", DEFAULT_HOTKEY)
    _save_config(cfg)
    print(f"Config saved: {CONFIG_FILE}")

    print("Opening browser for Spotify authorization (PKCE)…")
    provider = make_spotify_provider(client_id=client_id, token_path=SPOTIFY_TOKEN_FILE)
    provider.authorize()
    print(f"Tokens saved: {SPOTIFY_TOKEN_FILE}")
    print("Done. Launch with: like-spotify")
    return 0


# ── Main ────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="like-spotify")
    p.add_argument("--setup", action="store_true", help="Interactive Client ID + browser OAuth.")
    p.add_argument("--config", action="store_true", help="Print config / token paths.")
    return p.parse_args(argv)


def _msgbox(text: str, title: str = "Like Spotify", icon: int = 0x10) -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(0, text, title, icon)
            return
        except Exception:
            pass
    print(f"{title}: {text}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.config:
        print(f"Config:        {CONFIG_FILE}")
        print(f"Spotify token: {SPOTIFY_TOKEN_FILE}")
        return 0

    if args.setup:
        return _do_setup()

    cfg = _load_config()
    client_id = cfg.get("spotify", {}).get("client_id", "") or os.environ.get(
        "SPOTIFY_CLIENT_ID", ""
    )
    if not client_id:
        _msgbox(
            "Not configured. Run from a terminal:\n\n    like-spotify --setup\n",
            title="Like Spotify — setup required",
        )
        return 2

    _ensure_single_instance()
    hotkey = cfg.get("trigger", {}).get("hotkey", DEFAULT_HOTKEY)

    provider = make_spotify_provider(client_id=client_id, token_path=SPOTIFY_TOKEN_FILE)
    if not provider.has_tokens:
        _msgbox(
            "Not authenticated. Run from a terminal:\n\n    like-spotify --setup\n",
            title="Like Spotify — auth required",
        )
        return 2

    feedback = TrayFeedback(hotkey=hotkey)
    storage = _build_storage(cfg)
    post_actions = _build_post_actions(cfg, storage)
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
    ]
    if sys.platform == "win32":
        menu_items += [
            pystray.MenuItem(
                "Start with Windows",
                on_toggle_autostart,
                checked=lambda _item: _autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
        ]
    menu_items.append(pystray.MenuItem("Quit", on_quit))

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
