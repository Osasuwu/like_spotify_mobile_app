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

### 3. Desktop (Windows / macOS / Linux)

```bash
pip install requests
cd desktop
python like_spotify.py --config   # creates config file
# Edit ~/.like_spotify/config.json — set client_id
python like_spotify.py --auth     # one-time browser auth
```

Bind `pythonw like_spotify.py` to a keyboard shortcut. See [desktop/README.md](desktop/README.md) for details.

### 4. Cross-device counters (optional)

Like counters are shared across devices via [Supabase](https://supabase.com) (free tier).

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
3. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to `.env` (Android) and `~/.like_spotify/config.json` (desktop)

Without Supabase, counters are stored locally per device.

## Architecture

```
Android (Flutter + Kotlin)          Desktop (Python)
┌──────────────────────┐           ┌──────────────────┐
│  MediaSession        │           │  OS hotkey        │
│  pause-play pattern  │           │  like_spotify.py  │
│       ↓              │           │       ↓           │
│  SpotifyLikeWorker   │           │  Spotify API      │
│  • like track        │           │  • like track     │
│  • remove from       │           │  • remove from    │
│    archive           │           │    archive        │
│  • Supabase counter  │           │  • Supabase       │
│  • best-of / follow  │           │    counter        │
└──────┬───────────────┘           └──────┬───────────┘
       │                                  │
       └──────────┬───────────────────────┘
                  ↓
          Spotify Web API (shared state)
          Supabase (shared counters)
```

- `lib/` — Flutter app (Dart): UI, state management (Riverpod), Spotify OAuth
- `android/.../kotlin/` — Native Android: foreground service, MediaSession, background worker
- `desktop/` — Python script: OAuth PKCE, Spotify API, desktop notifications

## Configuration

| Setting | Android | Desktop |
|---------|---------|---------|
| Trigger pattern | In-app UI | N/A (hotkey) |
| Archive playlist name | In-app UI | `~/.like_spotify/config.json` |
| Best-of playlist name | In-app UI | `~/.like_spotify/config.json` |
| Like threshold for best-of | 3 (default) | 3 (default) |

## License

[MIT](LICENSE)
