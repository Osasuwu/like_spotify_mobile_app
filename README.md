# Like Spotify

Like the currently playing Spotify track with a headset button pattern (Android) or keyboard shortcut (desktop). Manages a Discover Weekly archive playlist — liked tracks are removed so you never re-listen to them.

## How it works

1. **Trigger** — pause-play your headset (Android) or press a hotkey (desktop)
2. **Like** — the current track is added to your Spotify Liked Songs
3. **Archive cleanup** — if the track is in your archive playlist, it gets removed
4. **Best-of promotion** — like a track 3 times across devices and it's added to your best-of playlist
5. **Artist follow** — like 5+ tracks from an artist and they get auto-followed

## Quick start

### 1. Spotify Developer App

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Create an app
3. Add redirect URIs:
   - `likespotify://auth-callback` (Android)
   - `http://127.0.0.1:8793/callback` (Desktop)
4. Copy your Client ID

### 2. Android

```bash
# Clone and setup
git clone https://github.com/Osasuwu/like_spotify_mobile_app.git
cd like_spotify_mobile_app

# Configure
cp .env.example .env
# Edit .env — set SPOTIFY_CLIENT_ID (and optionally SUPABASE_URL/KEY)

# Build
flutter pub get
flutter build apk --release --dart-define-from-file=.env
```

Install the APK, connect Spotify in the app, enable the listener service.

### 3. Desktop

The desktop side ships as a pluggable Python package (`like_spotify/`) —
a tray host + global hotkey on Windows, a CLI fallback (`like-once`) on
macOS / Linux, and a multi-backend counter Storage (Supabase or Google
Sheets).

**One-liner installs.** Run from a fresh clone:

```powershell
# Windows (PowerShell)
git clone https://github.com/Osasuwu/like_spotify_mobile_app.git
cd like_spotify_mobile_app
.\install.ps1
```

```bash
# macOS / Linux
git clone https://github.com/Osasuwu/like_spotify_mobile_app.git
cd like_spotify_mobile_app
./install.sh
```

The installer checks for Python 3.11+, installs `pipx` if missing,
installs the `like-spotify` package, then walks you through the
interactive setup wizard:

1. **Spotify** — paste a Client ID from
   [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
   (redirect URI: `http://127.0.0.1:8793/callback`); a browser opens
   for PKCE OAuth.
2. **Storage** — pick `supabase`, `sheets`, or `none` (likes work
   without a counter; you'd just lose cross-device aggregation).
3. **Autostart** — Windows: toggle the `HKCU\…\Run` entry. macOS /
   Linux: instructions for a Launch Agent / `.desktop` file are
   printed (no auto-config — too platform-fragmented).

The wizard is re-runnable; existing tokens are kept unless you pass
`--reauth` (or `-Reauth` on PowerShell).

**After install:**

```bash
like-spotify            # Windows: tray host with the hotkey (default Ctrl+Shift+Alt+W)
like-spotify like-once  # any OS: like the currently-playing track and exit
like-spotify --config   # print config + token paths
```

**Single-file `.exe`** (for users without Python): build via
`tools\build.bat` → `dist\LikeSpotify.exe`.

### 4. Cross-device counters (optional)

Pick a backend during `--setup`:

#### Option A — Supabase (default; one SQL block)

Counters live in Supabase Postgres (free tier).

1. Create a Supabase project
2. Run the setup SQL:
   ```sql
   CREATE TABLE public.track_likes (
       user_id TEXT NOT NULL,
       track_id TEXT NOT NULL,
       count INTEGER NOT NULL DEFAULT 1,
       updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       PRIMARY KEY (user_id, track_id)
   );

   CREATE OR REPLACE FUNCTION increment_track_like(p_user_id TEXT, p_track_id TEXT)
   RETURNS INTEGER LANGUAGE plpgsql SECURITY DEFINER AS $$
   DECLARE new_count INTEGER;
   BEGIN
       INSERT INTO public.track_likes (user_id, track_id, count, updated_at)
       VALUES (p_user_id, p_track_id, 1, now())
       ON CONFLICT (user_id, track_id)
       DO UPDATE SET count = track_likes.count + 1, updated_at = now()
       RETURNING count INTO new_count;
       RETURN new_count;
   END; $$;

   ALTER TABLE public.track_likes ENABLE ROW LEVEL SECURITY;
   CREATE POLICY "anon_full_access" ON public.track_likes FOR ALL USING (true) WITH CHECK (true);
   ```
3. Android: add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to `.env`. Desktop: paste both into the wizard when prompted for the `supabase` backend.

#### Option B — Google Sheets

If you'd rather see counts in a spreadsheet you control:

1. Create a Google Sheet with header row `user_id | track_id | count | backfilled | updated_at` on a tab named `Likes`. Optionally add an `ArtistTracks` tab for the follow-artist rule.
2. Create a Google Cloud OAuth client (type: **Desktop app**) at [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials). Enable the Google Sheets API for the project. Note the Client ID + secret.
3. Run `like-spotify --setup`, pick `sheets`, paste the spreadsheet ID (from the URL), Client ID, and secret. A browser opens for Google authorization — tokens are refreshed automatically afterwards.

Without a backend, counters are silently skipped — likes still write to your Spotify Liked Songs.

## Architecture

```
Android (Flutter + Kotlin)          Desktop (Python framework)
┌──────────────────────┐           ┌──────────────────────────┐
│  MediaSession        │           │  Trigger (hotkey/tray)   │
│  pause-play pattern  │           │       ↓                  │
│       ↓              │           │  MusicProvider (Spotify) │
│  SpotifyLikeWorker   │           │  • like track            │
│  • like track        │           │  Storage  → #22          │
│  • remove from       │           │  PostLikeAction → #23/26 │
│    archive           │           │    · archive remove      │
│  • Supabase counter  │           │    · best-of promote     │
│  • best-of / follow  │           │    · artist follow       │
└──────┬───────────────┘           └──────┬───────────────────┘
       │                                  │
       └──────────┬───────────────────────┘
                  ↓
          Spotify Web API (shared state)
          Supabase (shared counters)
```

- `lib/` — Flutter app (Dart): UI, state management (Riverpod), Spotify OAuth
- `android/.../kotlin/` — Native Android: foreground service, MediaSession, background worker
- `like_spotify/` — Python desktop package: `core/` (ABCs), `hosts/` (tray runtime), `extensions/` (default Spotify provider + tray-hotkey trigger), `samples/` (alt-flavor examples)

## Configuration

| Setting | Android | Desktop |
|---------|---------|---------|
| Trigger pattern / hotkey | In-app UI | `~/.like_spotify/config.json` → `trigger.hotkey` (default `Ctrl+Shift+Alt+W`) |
| Spotify client_id | `.env` (`SPOTIFY_CLIENT_ID`) | `like-spotify --setup` → `~/.like_spotify/config.json` |
| Spotify tokens | `FlutterSecureStorage` | `~/.like_spotify/spotify_token.json` |
| Storage backend | (Supabase only) | `~/.like_spotify/config.json` → `storage.backend` (`supabase` / `sheets` / `none`) |
| Google Sheets tokens | n/a | `~/.like_spotify/google_token.json` (refreshed automatically) |
| Archive / best-of / follow | In-app UI | `~/.like_spotify/config.json` → `actions.{archive_remove,promote_to_best_of,follow_artist}` |

## License

[MIT](LICENSE)
