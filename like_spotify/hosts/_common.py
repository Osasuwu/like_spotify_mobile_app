"""Cross-platform host helpers shared by every host implementation.

Hosts (windows / _stub / future macos+linux) compose the same pipeline:
config + provider + storage + post-action chain. The differences are the
runtime shell (tray vs CLI vs systemd) and the OS-bound side effects
(autostart, single-instance, native beep). Everything else lives here so
the host modules stay thin and platform-pure.

Slice history:
    #21 — extracted from the original tray launcher.
    #27 — split out of `hosts/tray.py` so `_stub.py` (mac/linux CLI)
          can share the same setup / config code without dragging in
          winreg / winsound / pystray.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from like_spotify.core.actions import PostLikeAction
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
from like_spotify.extensions.tray_hotkey_trigger import DEFAULT_HOTKEY

# ── Paths ──────────────────────────────────────────────────────────────


def _config_dir() -> Path:
    return Path.home() / ".like_spotify"


CONFIG_FILE = _config_dir() / "config.json"
SPOTIFY_TOKEN_FILE = _config_dir() / "spotify_token.json"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ── Storage / provider builders ────────────────────────────────────────


def build_storage(cfg: dict) -> Storage | None:
    """Return a Storage impl iff Supabase is configured; else None.

    Acceptance criterion (#22): like still succeeds when storage is
    unconfigured. Pipeline treats `None` as 'counter silently unavailable'.
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


def build_post_actions(
    cfg: dict, storage: Storage | None
) -> list[PostLikeAction]:
    """Compose the default-flavor post-like chain.

    Each action is independently togglable: omit / blank the relevant
    config key OR set `actions.<name>.enabled = false` to skip it.
    """
    actions: list[PostLikeAction] = []
    nested = cfg.get("actions") if isinstance(cfg.get("actions"), dict) else {}

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

    # FollowArtistAction requires Storage (uses record_artist_track).
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


def resolve_client_id(cfg: dict) -> str:
    return cfg.get("spotify", {}).get("client_id", "") or os.environ.get(
        "SPOTIFY_CLIENT_ID", ""
    )


def make_provider(client_id: str):
    return make_spotify_provider(client_id=client_id, token_path=SPOTIFY_TOKEN_FILE)


# ── Interactive setup ──────────────────────────────────────────────────


def do_setup() -> int:
    """Interactive Client ID + browser OAuth.

    Shared between hosts so `like-spotify --setup` behaves identically on
    every platform.
    """
    print("Like Spotify — interactive setup")
    print("--------------------------------")
    cfg = load_config()
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
    save_config(cfg)
    print(f"Config saved: {CONFIG_FILE}")

    print("Opening browser for Spotify authorization (PKCE)…")
    provider = make_provider(client_id)
    provider.authorize()
    print(f"Tokens saved: {SPOTIFY_TOKEN_FILE}")
    print("Done. Launch with: like-spotify")
    return 0


# ── CLI ────────────────────────────────────────────────────────────────


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the shared CLI surface.

    Subcommands:
        (none)     — run the platform's default host (tray on Windows,
                     CLI-only stub elsewhere).
        like-once  — perform a single like and exit (uses OneShotCliTrigger,
                     works on every platform).

    Flags (back-compat with the original tray launcher):
        --setup    — interactive Client ID + browser OAuth.
        --config   — print config / token paths and exit.
    """
    p = argparse.ArgumentParser(prog="like-spotify")
    p.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "like-once"],
        help=(
            "run (default) — start the long-lived host (tray on Windows). "
            "like-once — perform a single like and exit."
        ),
    )
    p.add_argument("--setup", action="store_true", help="Interactive Client ID + browser OAuth.")
    p.add_argument("--config", action="store_true", help="Print config / token paths.")
    return p.parse_args(argv)


def print_config_paths() -> int:
    print(f"Config:        {CONFIG_FILE}")
    print(f"Spotify token: {SPOTIFY_TOKEN_FILE}")
    return 0


# ── Error reporting (cross-platform fallback) ──────────────────────────


def msgbox(text: str, title: str = "Like Spotify") -> None:
    """Surface a user-visible error.

    Windows host overrides with a real MessageBoxW; here we just print so
    the stub host (mac/linux CLI) and any test environment still get the
    message on stderr.
    """
    print(f"{title}: {text}", file=sys.stderr)
