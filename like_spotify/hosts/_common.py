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
import asyncio
import json
import os
import sys
from pathlib import Path

from like_spotify.auth import google as google_auth
from like_spotify.core.actions import PostLikeAction
from like_spotify.core.pipeline import FeedbackFn, RemoveFromPlaylistPipeline
from like_spotify.core.storage import Storage
from like_spotify.extensions.one_shot_cli_trigger import (
    TRIGGER as make_one_shot_cli_trigger,
)
from like_spotify.extensions.archive_remove import (
    POST_LIKE_ACTION as make_archive_remove_action,
)
from like_spotify.extensions.follow_artist import (
    POST_LIKE_ACTION as make_follow_artist_action,
)
from like_spotify.extensions.google_sheets_storage import (
    STORAGE as make_google_sheets_storage,
)
from like_spotify.extensions.promote_to_best_of import (
    POST_LIKE_ACTION as make_promote_to_best_of_action,
)
from like_spotify.extensions.spotify import MUSIC_PROVIDER as make_spotify_provider
from like_spotify.extensions.supabase_storage import STORAGE as make_supabase_storage
from like_spotify.extensions.tray_hotkey_trigger import DEFAULT_HOTKEY

# Second hotkey: remove the current track from the archive playlist WITHOUT
# liking it. Distinct from DEFAULT_HOTKEY (the like trigger). The desktop can
# bind arbitrarily many triggers; headphones are limited to one media-button
# pattern, so this is desktop-only by design.
DEFAULT_REMOVE_HOTKEY = "ctrl+shift+alt+q"

# Beep loudness (0.0-1.0) for the synthesized tray tone (#53). Tuned down
# from the tone's initial full-scale level, which was audible but jarring
# for a hotkey confirmation played over whatever's already in the speakers.
DEFAULT_FEEDBACK_VOLUME = 0.25

# ── Paths ──────────────────────────────────────────────────────────────


def _config_dir() -> Path:
    return Path.home() / ".like_spotify"


CONFIG_FILE = _config_dir() / "config.json"
SPOTIFY_TOKEN_FILE = _config_dir() / "spotify_token.json"
GOOGLE_TOKEN_FILE = _config_dir() / "google_token.json"


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
    """Return the configured Storage impl, or None when none is wired.

    Selection (set in `cfg["storage"]["backend"]`):
        - "supabase" → SupabaseStorage (default; back-compat: also picked
          when `cfg["supabase"]` is populated and no explicit backend).
        - "sheets"   → GoogleSheetsStorage, backed by tokens persisted
          in `GOOGLE_TOKEN_FILE` (refreshed automatically).
        - "none" / missing → None. Pipeline treats `None` as "counter
          silently unavailable" — AC #22 says like still succeeds.
    """
    backend = (cfg.get("storage", {}) or {}).get("backend", "")

    # Back-compat for configs written before #28:
    #   - a populated `supabase` block implies Supabase
    #   - OR SUPABASE_URL + SUPABASE_ANON_KEY env vars alone (the pre-#28
    #     Android / CI path) — keep this working so existing deployments
    #     don't regress when they upgrade.
    if not backend:
        sb = cfg.get("supabase", {}) if isinstance(cfg.get("supabase"), dict) else {}
        if sb.get("url") and sb.get("anon_key"):
            backend = "supabase"
        elif os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_ANON_KEY"):
            backend = "supabase"

    if backend == "supabase":
        sb = cfg.get("supabase", {}) if isinstance(cfg.get("supabase"), dict) else {}
        url = sb.get("url") or os.environ.get("SUPABASE_URL", "")
        key = sb.get("anon_key") or os.environ.get("SUPABASE_ANON_KEY", "")
        if not url or not key:
            return None
        try:
            return make_supabase_storage(url=url, anon_key=key)
        except Exception:
            return None

    if backend == "sheets":
        sheets = cfg.get("sheets", {}) if isinstance(cfg.get("sheets"), dict) else {}
        sid = sheets.get("spreadsheet_id") or os.environ.get(
            "GOOGLE_SHEETS_SPREADSHEET_ID", ""
        )
        if not sid:
            return None
        try:
            token_provider = google_auth.make_token_provider(GOOGLE_TOKEN_FILE)
            return make_google_sheets_storage(
                spreadsheet_id=sid,
                token_provider=token_provider,
            )
        except Exception:
            return None

    return None


def resolve_archive_playlist_name(cfg: dict) -> str:
    """The configured Discover Weekly archive playlist name, or "".

    Single source of truth for both the like-flow `ArchiveRemoveAction`
    and the remove-without-like `RemoveFromPlaylistPipeline` — they curate
    the *same* playlist, so they must read the same key. Honors the
    `actions.archive_remove.enabled = false` opt-out (returns "" when off).
    """
    nested = cfg.get("actions") if isinstance(cfg.get("actions"), dict) else {}
    archive_cfg = (
        nested.get("archive_remove")
        if isinstance(nested.get("archive_remove"), dict)
        else {}
    )
    if not archive_cfg.get("enabled", True):
        return ""
    return (
        archive_cfg.get("playlist_name")
        or nested.get("archive_playlist_name")
        or cfg.get("archive_playlist_name")  # legacy flat key
        or ""
    )


def build_post_actions(
    cfg: dict, storage: Storage | None
) -> list[PostLikeAction]:
    """Compose the default-flavor post-like chain.

    Each action is independently togglable: omit / blank the relevant
    config key OR set `actions.<name>.enabled = false` to skip it.
    """
    actions: list[PostLikeAction] = []
    nested = cfg.get("actions") if isinstance(cfg.get("actions"), dict) else {}

    archive_name = resolve_archive_playlist_name(cfg)
    if archive_name:
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


def resolve_remove_hotkey(cfg: dict) -> str:
    return cfg.get("trigger", {}).get("remove_hotkey", DEFAULT_REMOVE_HOTKEY)


def resolve_feedback_volume(cfg: dict) -> float:
    """Clamp `trigger.feedback_volume` to [0.0, 1.0]; bad/missing → default."""
    raw = cfg.get("trigger", {}).get("feedback_volume", DEFAULT_FEEDBACK_VOLUME)
    try:
        volume = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_FEEDBACK_VOLUME
    return max(0.0, min(1.0, volume))


def run_one_shot(pipeline, feedback) -> int:
    """Drive a single pipeline pass via OneShotCliTrigger; return an exit code.

    Shared by every host's `like-once` / `remove-once` subcommand: the
    only thing that varies between them is which pipeline is built and how
    config errors are surfaced (handled by the caller). Exit code follows
    the pipeline's last feedback outcome — 0 on success, 1 on failure or
    if nothing was emitted — so the command is scriptable.
    """
    trigger = make_one_shot_cli_trigger()

    async def emit() -> None:
        await pipeline.run_once()

    async def run() -> None:
        try:
            await trigger.start(emit)
        finally:
            await trigger.stop()

    asyncio.run(run())

    if not getattr(feedback, "calls", None):
        return 1
    return 0 if feedback.calls[-1][0] else 1


def build_remove_pipeline(
    cfg: dict, provider, feedback: FeedbackFn
) -> RemoveFromPlaylistPipeline | None:
    """Build the remove-without-like pipeline, or None when not configured.

    Wired only when an archive playlist name is set — without a target
    playlist there's nothing to remove from, so the second hotkey stays
    dark rather than failing on every press. Targets the same playlist as
    the like-flow archive action (see `resolve_archive_playlist_name`).
    """
    archive_name = resolve_archive_playlist_name(cfg)
    if not archive_name:
        return None
    try:
        return RemoveFromPlaylistPipeline(
            provider=provider, feedback=feedback, playlist_name=archive_name
        )
    except ValueError:
        return None


# ── Interactive setup ──────────────────────────────────────────────────


def _prompt(label: str, *, default: str = "", required: bool = False) -> str:
    hint = f" [{default}]" if default else (" [required]" if required else "")
    entered = input(f"{label}{hint}: ").strip()
    value = entered or default
    if required and not value:
        raise _SetupAbort(f"{label} is required")
    return value


def _prompt_secret(label: str, *, current: str = "") -> str:
    """Prompt with a masked preview of the current value (if any).

    `getpass`-style hiding isn't worth it here — `--setup` runs in a
    terminal the user controls, and the value is then written to a
    plaintext config file anyway. The mask is just to keep shoulder-
    surfing-friendly diffs out of `--config` output.
    """
    preview = (current[:4] + "…") if current else "required"
    entered = input(f"{label} [{preview}]: ").strip()
    return entered or current


def _prompt_choice(
    label: str, choices: list[str], default: str
) -> str:
    options = "/".join(c if c != default else f"{c}*" for c in choices)
    while True:
        entered = input(f"{label} [{options}]: ").strip().lower()
        value = entered or default
        if value in choices:
            return value
        print(f"  pick one of {', '.join(choices)}", file=sys.stderr)


def _prompt_yes_no(label: str, *, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    entered = input(f"{label} {suffix}: ").strip().lower()
    if not entered:
        return default
    return entered.startswith("y")


class _SetupAbort(Exception):
    """User-facing setup failure — caught by `do_setup`."""


def do_setup(reauth: bool = False) -> int:
    """Interactive wizard: Spotify OAuth → storage choice → autostart.

    Re-runnable. Existing OAuth tokens (Spotify, Google) are kept unless
    `reauth=True` is passed — switching storage backend does NOT
    invalidate the other backend's tokens, so a user can flip
    supabase ↔ sheets without redoing OAuth.
    """
    print("Like Spotify — interactive setup")
    print("--------------------------------")
    cfg = load_config()
    try:
        _setup_spotify(cfg, reauth=reauth)
        _setup_storage(cfg, reauth=reauth)
        _setup_archive(cfg)
        _setup_autostart()
    except _SetupAbort as e:
        print(f"Aborted: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        return 130

    save_config(cfg)
    print(f"\nConfig saved: {CONFIG_FILE}")
    print("Done. Launch with: like-spotify")
    return 0


# ── Wizard steps ───────────────────────────────────────────────────────


def _setup_spotify(cfg: dict, *, reauth: bool) -> None:
    print("\n[1/4] Spotify")
    current_id = cfg.get("spotify", {}).get("client_id", "")
    client_id = _prompt_secret("  Client ID", current=current_id)
    if not client_id:
        raise _SetupAbort(
            "Spotify Client ID is required. Get one at "
            "https://developer.spotify.com/dashboard "
            "(redirect URI: http://127.0.0.1:8793/callback)."
        )
    cfg.setdefault("spotify", {})["client_id"] = client_id
    cfg.setdefault("trigger", {}).setdefault("hotkey", DEFAULT_HOTKEY)
    # Persist now so a later step's failure doesn't lose the client id.
    save_config(cfg)

    provider = make_provider(client_id)
    if provider.has_tokens and not reauth:
        print("  ✓ Spotify tokens already saved — skipping browser auth")
        print("    (use --reauth to force a re-login)")
        return
    print("  Opening browser for Spotify authorization (PKCE)…")
    provider.authorize()
    print(f"  ✓ Tokens saved: {SPOTIFY_TOKEN_FILE}")


def _setup_storage(cfg: dict, *, reauth: bool) -> None:
    print("\n[2/4] Storage (counts likes across devices)")
    current_backend = (cfg.get("storage", {}) or {}).get("backend", "")
    default = current_backend or "none"
    backend = _prompt_choice(
        "  Backend", choices=["supabase", "sheets", "none"], default=default
    )
    cfg.setdefault("storage", {})["backend"] = backend

    if backend == "supabase":
        sb = cfg.setdefault("supabase", {})
        print("    (project URL, e.g. https://<ref>.supabase.co — not the /rest/v1 endpoint)")
        sb["url"] = _prompt_secret("  Supabase URL", current=sb.get("url", ""))
        sb["anon_key"] = _prompt_secret(
            "  Supabase anon key", current=sb.get("anon_key", "")
        )
        if not sb["url"] or not sb["anon_key"]:
            raise _SetupAbort("supabase URL + anon key are both required")
        print("  ✓ Supabase configured")
    elif backend == "sheets":
        sheets = cfg.setdefault("sheets", {})
        sheets["spreadsheet_id"] = _prompt_secret(
            "  Spreadsheet ID (from the sheet URL)",
            current=sheets.get("spreadsheet_id", ""),
        )
        if not sheets["spreadsheet_id"]:
            raise _SetupAbort("spreadsheet ID is required for sheets backend")

        tokens = google_auth.load_tokens(GOOGLE_TOKEN_FILE)
        if tokens.get("refresh_token") and not reauth:
            print("  ✓ Google tokens already saved — skipping browser auth")
            print("    (use --reauth to force a re-login)")
        else:
            client_id = _prompt_secret(
                "  Google OAuth Client ID (Desktop app)",
                current=tokens.get("client_id", ""),
            )
            client_secret = _prompt_secret(
                "  Google OAuth Client Secret",
                current=tokens.get("client_secret", ""),
            )
            if not client_id or not client_secret:
                raise _SetupAbort(
                    "google client id + secret are both required "
                    "(create a Desktop OAuth client at "
                    "https://console.cloud.google.com/apis/credentials)"
                )
            print("  Opening browser for Google authorization…")
            google_auth.authorize(
                client_id=client_id,
                client_secret=client_secret,
                token_path=GOOGLE_TOKEN_FILE,
            )
            print(f"  ✓ Google tokens saved: {GOOGLE_TOKEN_FILE}")
    else:
        print("  ✓ Counter disabled — likes still work, no count tracking.")


def _setup_archive(cfg: dict) -> None:
    """Discover Weekly clean-up: archive playlist + remove-without-like hotkey.

    Two coupled settings, one playlist:
      - `actions.archive_remove.playlist_name` — when you like a track, it's
        auto-removed from this "save-for-later" playlist (the like flow's
        PostLikeAction).
      - `trigger.remove_hotkey` — a second hotkey that removes the current
        track from the *same* playlist WITHOUT liking it, for tracks you
        want gone but not saved. Only meaningful when a playlist is set.

    Empty input keeps the current value (the wizard's keep-on-blank idiom),
    so re-running setup for an unrelated step won't clobber the archive.
    Type `-` to turn the feature off; blank with nothing set = skip.
    """
    print("\n[3/4] Discover Weekly clean-up (optional)")
    print(
        "  Name a playlist (e.g. an archived copy of Discover Weekly) to "
        "curate.\n"
        "  Liking a track removes it from this playlist; a second hotkey "
        "removes\n"
        "  the current track WITHOUT liking it. Blank = skip, '-' = turn off."
    )
    current_name = resolve_archive_playlist_name(cfg)
    if current_name:
        print(f"  (currently: {current_name})")
    playlist_name = _prompt("  Archive playlist name", default=current_name)
    archive_cfg = cfg.setdefault("actions", {}).setdefault("archive_remove", {})

    if playlist_name == "-":
        # Explicit off switch — idempotent: works whether or not a name was
        # set. The message reflects which it was so '-' never looks like a
        # no-op when the user clearly asked to turn it off.
        archive_cfg["enabled"] = False
        print("  ✓ Clean-up disabled." if current_name else "  ✓ Already disabled.")
        return
    if not playlist_name:
        # Bare Enter is only empty when nothing was configured (keep-on-blank
        # would otherwise have returned current_name) — so this is a skip.
        print("  ✓ Skipped.")
        return

    archive_cfg["playlist_name"] = playlist_name
    archive_cfg["enabled"] = True

    current_hotkey = resolve_remove_hotkey(cfg)
    remove_hotkey = _prompt(
        "  Remove-without-like hotkey", default=current_hotkey or DEFAULT_REMOVE_HOTKEY
    )
    cfg.setdefault("trigger", {})["remove_hotkey"] = remove_hotkey
    print(f"  ✓ Archive playlist: {playlist_name}")
    print(f"  ✓ Remove hotkey: {remove_hotkey.upper()}")


def _setup_autostart() -> None:
    print("\n[4/4] Autostart")
    if sys.platform != "win32":
        # Print instructions only — issue AC: no auto-config on mac/linux.
        if sys.platform == "darwin":
            print(
                "  macOS: add a Launch Agent to start at login. Example "
                "(write to ~/Library/LaunchAgents/com.osasuwu.like-spotify.plist):"
            )
            print(
                '    <plist version="1.0"><dict>'
                '<key>Label</key><string>com.osasuwu.like-spotify</string>'
                '<key>ProgramArguments</key><array>'
                '<string>like-spotify</string><string>like-once</string>'
                '</array>'
                '<key>RunAtLoad</key><true/></dict></plist>'
            )
            print("    then: launchctl load ~/Library/LaunchAgents/com.osasuwu.like-spotify.plist")
        else:
            print(
                "  Linux: drop a .desktop entry into ~/.config/autostart/, e.g.\n"
                "    [Desktop Entry]\n"
                "    Type=Application\n"
                "    Exec=like-spotify like-once\n"
                "    Hidden=false\n"
                "    NoDisplay=false\n"
                "    Name=Like Spotify"
            )
        print("  (See CONTRIBUTING.md for the full hosts/macos.py / linux.py story.)")
        return

    # Windows: prompt to toggle the registry Run key.
    try:
        from like_spotify.hosts import windows as _win

        already = _win._autostart_enabled()
    except Exception:
        print("  (could not query autostart — skip)", file=sys.stderr)
        return

    label = (
        "  Autostart is currently ENABLED — keep it on?"
        if already
        else "  Start Like Spotify when you log in to Windows?"
    )
    if _prompt_yes_no(label, default=True):
        _win._autostart_set(True)
        print("  ✓ Autostart enabled (HKCU\\…\\Run)")
    else:
        _win._autostart_set(False)
        print("  ✓ Autostart disabled")


# ── CLI ────────────────────────────────────────────────────────────────


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the shared CLI surface.

    Subcommands:
        (none)      — run the platform's default host (tray on Windows,
                      CLI-only stub elsewhere).
        like-once   — perform a single like and exit (uses OneShotCliTrigger,
                      works on every platform).
        remove-once — remove the currently-playing track from the archive
                      playlist WITHOUT liking it, then exit.

    Flags (back-compat with the original tray launcher):
        --setup    — interactive Client ID + browser OAuth.
        --config   — print config / token paths and exit.
    """
    p = argparse.ArgumentParser(prog="like-spotify")
    p.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "like-once", "remove-once"],
        help=(
            "run (default) — start the long-lived host (tray on Windows). "
            "like-once — perform a single like and exit. "
            "remove-once — remove the current track from the archive "
            "playlist without liking it."
        ),
    )
    p.add_argument("--setup", action="store_true", help="Interactive setup wizard.")
    p.add_argument(
        "--reauth",
        action="store_true",
        help=(
            "With --setup: re-run OAuth even if valid tokens are present "
            "(use after revoking access or switching accounts)."
        ),
    )
    p.add_argument("--config", action="store_true", help="Print config / token paths.")
    return p.parse_args(argv)


def print_config_paths() -> int:
    print(f"Config:        {CONFIG_FILE}")
    print(f"Spotify token: {SPOTIFY_TOKEN_FILE}")
    print(f"Google token:  {GOOGLE_TOKEN_FILE}")
    return 0


# ── Error reporting (cross-platform fallback) ──────────────────────────


def msgbox(text: str, title: str = "Like Spotify") -> None:
    """Surface a user-visible error.

    Windows host overrides with a real MessageBoxW; here we just print so
    the stub host (mac/linux CLI) and any test environment still get the
    message on stderr.
    """
    print(f"{title}: {text}", file=sys.stderr)
