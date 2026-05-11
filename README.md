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

### 3. Desktop (Windows)

The desktop side ships as a pluggable Python package (`like_spotify/`) — tray
host + default flavor (`tray_hotkey_trigger` + `spotify` provider). The
broader plugin framework lands across [#19](https://github.com/Osasuwu/like_spotify_mobile_app/issues/19); Phase 1
tracer is [#21](https://github.com/Osasuwu/like_spotify_mobile_app/issues/21).

```bash
git clone https://github.com/Osasuwu/like_spotify_mobile_app.git
cd like_spotify_mobile_app
pipx install -e .           # or: pip install -e .

like-spotify --setup        # interactive Client ID + browser OAuth
like-spotify                # tray host; default hotkey Ctrl+Shift+Alt+W
```

Or build a single-file Windows EXE: `tools\build.bat` →
`dist\LikeSpotify.exe`.

Storage (Supabase counter), best-of promotion, archive-remove, and
artist-follow land in follow-up issues
([#22](https://github.com/Osasuwu/like_spotify_mobile_app/issues/22),
[#23](https://github.com/Osasuwu/like_spotify_mobile_app/issues/23),
[#26](https://github.com/Osasuwu/like_spotify_mobile_app/issues/26))
— the tracer bullet does likes only.

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
3. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to `.env` (Android). Desktop wiring lands in [#22](https://github.com/Osasuwu/like_spotify_mobile_app/issues/22) (`SupabaseStorage`).

Without Supabase, counters are stored locally per device.

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
| Archive / best-of / follow | In-app UI | (lands in #22 / #23 / #26) |

## License

[MIT](LICENSE)
