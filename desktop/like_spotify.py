#!/usr/bin/env python3
"""Like current Spotify track and remove it from archive playlist.

Usage:
    python like_spotify.py --auth          # One-time: authenticate via browser
    python like_spotify.py                 # Like current track
    python like_spotify.py --config        # Show config location
    pythonw like_spotify.py                # Silent run (Windows, no console)

Bind to a keyboard shortcut for hands-free operation.
"""

import argparse
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from base64 import urlsafe_b64encode
from pathlib import Path

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests")
    sys.exit(1)

# --- Config -------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".like_spotify"
TOKEN_FILE = CONFIG_DIR / "tokens.json"
CONFIG_FILE = CONFIG_DIR / "config.json"

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API = "https://api.spotify.com/v1"

SCOPES = (
    "user-library-modify "
    "user-library-read "
    "user-read-playback-state "
    "user-follow-modify "
    "playlist-read-private "
    "playlist-read-collaborative "
    "playlist-modify-private "
    "playlist-modify-public"
)

REDIRECT_PORT = 8793
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"

DEFAULT_CONFIG = {
    "client_id": "",
    "archive_playlist_name": "Discover Weekly Archive",
    "best_of_playlist_name": "Botbotb(Best of the best of the best)",
    "best_of_like_threshold": 3,
    "artist_follow_threshold": 5,
    "supabase_url": "",
    "supabase_anon_key": "",
}


def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def load_tokens():
    if not TOKEN_FILE.exists():
        return None
    with open(TOKEN_FILE) as f:
        return json.load(f)


def save_tokens(tokens):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


# --- OAuth PKCE ---------------------------------------------------------------

def auth_flow(client_id):
    verifier = secrets.token_urlsafe(64)[:64]
    challenge = urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_hex(16)

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
        "scope": SCOPES,
    }
    auth_url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"

    result = {}
    event = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result["code"] = qs.get("code", [None])[0]
            result["state"] = qs.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Done! You can close this tab.</h2>")
            event.set()

        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"Opening browser for Spotify auth...")
    webbrowser.open(auth_url)

    event.wait(timeout=120)
    server.server_close()

    if not result.get("code"):
        print("Auth failed: no code received.")
        sys.exit(1)
    if result.get("state") != state:
        print("Auth failed: state mismatch.")
        sys.exit(1)

    resp = requests.post(SPOTIFY_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": result["code"],
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
    })
    resp.raise_for_status()
    data = resp.json()

    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": int(time.time()) + data.get("expires_in", 3600),
    }
    save_tokens(tokens)
    print("Authenticated successfully. Tokens saved.")
    return tokens


# --- Token management ---------------------------------------------------------

def ensure_token(config, tokens):
    if not tokens:
        print("Not authenticated. Run: python like_spotify.py --auth")
        sys.exit(1)

    if time.time() < tokens.get("expires_at", 0) - 300:
        return tokens

    resp = requests.post(SPOTIFY_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": config["client_id"],
    })

    if resp.status_code not in range(200, 300):
        print(f"Token refresh failed ({resp.status_code}): {resp.text}")
        sys.exit(1)

    data = resp.json()
    tokens["access_token"] = data["access_token"]
    if data.get("refresh_token"):
        tokens["refresh_token"] = data["refresh_token"]
    tokens["expires_at"] = int(time.time()) + data.get("expires_in", 3600)
    save_tokens(tokens)
    return tokens


# --- Spotify API calls --------------------------------------------------------

def api_get(endpoint, token):
    r = requests.get(f"{SPOTIFY_API}{endpoint}", headers={"Authorization": f"Bearer {token}"})
    return r


def api_put(endpoint, token, json_body=None):
    return requests.put(
        f"{SPOTIFY_API}{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        json=json_body,
    )


def api_delete(endpoint, token, json_body=None):
    return requests.delete(
        f"{SPOTIFY_API}{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        json=json_body,
    )


def api_post(endpoint, token, json_body=None):
    return requests.post(
        f"{SPOTIFY_API}{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        json=json_body,
    )


def get_current_track(token):
    r = api_get("/me/player/currently-playing", token)
    if r.status_code == 204:
        return None, []
    if r.status_code not in range(200, 300):
        return None, []
    data = r.json()
    item = data.get("item")
    if not item:
        return None, []
    track_id = item.get("id")
    artist_ids = [a["id"] for a in item.get("artists", []) if a.get("id")]
    return track_id, artist_ids


def like_track(track_id, token):
    r = api_put(f"/me/tracks?ids={track_id}", token)
    return r.status_code in range(200, 300)


def find_playlist_by_name(name, token):
    offset = 0
    needle = name.strip()
    while True:
        r = api_get(f"/me/playlists?limit=50&offset={offset}", token)
        if r.status_code not in range(200, 300):
            return None
        data = r.json()
        items = data.get("items", [])
        for p in items:
            if p.get("name", "").strip().lower() == needle.lower():
                return p["id"]
        if len(items) < 50:
            return None
        offset += 50


def remove_track_from_playlist(track_id, playlist_id, token):
    r = api_delete(
        f"/playlists/{playlist_id}/tracks",
        token,
        json_body={"tracks": [{"uri": f"spotify:track:{track_id}"}]},
    )
    return r.status_code in range(200, 300)


def get_spotify_user_id(token):
    r = api_get("/me", token)
    if r.status_code in range(200, 300):
        return r.json().get("id")
    return None


def add_track_to_playlist(track_id, playlist_id, token):
    r = api_post(
        f"/playlists/{playlist_id}/tracks",
        token,
        json_body={"uris": [f"spotify:track:{track_id}"]},
    )
    return r.status_code in range(200, 300)


def follow_artist(artist_id, token):
    r = api_put(f"/me/following?type=artist&ids={artist_id}", token)
    return r.status_code in range(200, 300)


def ensure_playlist(name, token):
    pid = find_playlist_by_name(name, token)
    if pid:
        return pid
    user_id = get_spotify_user_id(token)
    if not user_id:
        return None
    r = api_post(
        f"/users/{user_id}/playlists",
        token,
        json_body={"name": name, "public": False, "description": "Managed by Like Spotify"},
    )
    if r.status_code in range(200, 300):
        return r.json().get("id")
    return None


# --- Supabase -----------------------------------------------------------------

def supabase_increment(config, user_id, track_id):
    """Increment like count in Supabase, return new count. Returns None if not configured."""
    url = config.get("supabase_url", "")
    key = config.get("supabase_anon_key", "")
    if not url or not key:
        return None
    try:
        r = requests.post(
            f"{url}/rest/v1/rpc/increment_track_like",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"p_user_id": user_id, "p_track_id": track_id},
            timeout=5,
        )
        if r.status_code in range(200, 300):
            return r.json()
    except Exception:
        pass
    return None


# --- Notifications ------------------------------------------------------------

def notify(title, message):
    """Best-effort desktop notification. Silent fail if not available."""
    try:
        if sys.platform == "win32":
            # PowerShell toast — no dependencies
            import subprocess
            ps = (
                f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, '
                f'ContentType = WindowsRuntime] | Out-Null; '
                f'$t = [Windows.UI.Notifications.ToastNotification]::new('
                f'[Windows.UI.Notifications.ToastNotificationManager]::'
                f'GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)); '
                f'$t.GetElementsByTagName("text")[0].AppendChild($t.CreateTextNode("{title}")) | Out-Null; '
                f'$t.GetElementsByTagName("text")[1].AppendChild($t.CreateTextNode("{message}")) | Out-Null; '
                f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Like Spotify").Show($t)'
            )
            subprocess.Popen(
                ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen([
                "osascript", "-e",
                f'display notification "{message}" with title "{title}"'
            ])
        else:
            import subprocess
            subprocess.Popen(["notify-send", title, message])
    except Exception:
        pass


# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Like current Spotify track")
    parser.add_argument("--auth", action="store_true", help="Authenticate via browser")
    parser.add_argument("--config", action="store_true", help="Show config location")
    args = parser.parse_args()

    config = load_config()

    if args.config:
        print(f"Config: {CONFIG_FILE}")
        print(f"Tokens: {TOKEN_FILE}")
        return

    if not config.get("client_id"):
        print(f"Set client_id in {CONFIG_FILE}")
        print("Get one at https://developer.spotify.com/dashboard")
        sys.exit(1)

    if args.auth:
        auth_flow(config["client_id"])
        return

    tokens = load_tokens()
    tokens = ensure_token(config, tokens)
    token = tokens["access_token"]

    track_id, artist_ids = get_current_track(token)
    if not track_id:
        notify("Like Spotify", "No track playing")
        return

    if like_track(track_id, token):
        # Remove from archive if present
        archive_name = config.get("archive_playlist_name", "")
        if archive_name:
            playlist_id = find_playlist_by_name(archive_name, token)
            if playlist_id:
                remove_track_from_playlist(track_id, playlist_id, token)

        # Increment cross-device counter in Supabase
        user_id = get_spotify_user_id(token)
        like_count = None
        if user_id:
            like_count = supabase_increment(config, user_id, track_id)

        # Best-of promotion
        threshold = config.get("best_of_like_threshold", 3)
        if like_count is not None and like_count == threshold:
            best_of = config.get("best_of_playlist_name", "")
            if best_of:
                pid = ensure_playlist(best_of, token)
                if pid:
                    add_track_to_playlist(track_id, pid, token)

        notify("Like Spotify", "Liked!")
    else:
        notify("Like Spotify", "Like failed")


if __name__ == "__main__":
    main()
