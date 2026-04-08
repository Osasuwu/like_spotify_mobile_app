# Like Spotify — Desktop

Standalone script that likes the currently playing Spotify track and removes it from your archive playlist. Bind to a keyboard shortcut for hands-free operation.

## Requirements

- Python 3.9+
- `pip install requests`

## Setup

1. **Get Spotify Client ID** at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
   - Create an app, add redirect URI: `http://127.0.0.1:8793/callback`

2. **Configure** — run once, then edit the generated config:
   ```bash
   python like_spotify.py --config   # shows config file location
   ```
   Edit `~/.like_spotify/config.json`:
   ```json
   {
     "client_id": "your_spotify_client_id",
     "archive_playlist_name": "Discover Weekly Archive",
     "supabase_url": "",
     "supabase_anon_key": ""
   }
   ```
   Supabase fields are optional — for cross-device like counters (shared with the Android app).

3. **Authenticate** — one-time, opens browser:
   ```bash
   python like_spotify.py --auth
   ```

4. **Bind a keyboard shortcut**

   **Windows:** Create a shortcut on Desktop:
   - Target: `pythonw.exe C:\path\to\desktop\like_spotify.py`
   - Right-click shortcut > Properties > Shortcut key > `Ctrl+Alt+L`

   **macOS:** Automator > Quick Action > Run Shell Script > bind in System Settings > Keyboard > Shortcuts

   **Linux:** Add a custom shortcut in your DE settings pointing to `python3 /path/to/like_spotify.py`

## Usage

```bash
python like_spotify.py           # Like current track (+ desktop notification)
python like_spotify.py --auth    # Re-authenticate
python like_spotify.py --config  # Show config/token file paths
```

Tokens auto-refresh. No background process needed.
