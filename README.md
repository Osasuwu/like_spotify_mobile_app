# Like Spotify Mobile App (Android-only)

Flutter Android application that listens for headset/media button signals in a foreground service and sends a Spotify “Like current track” action when the configured signal pattern is detected.

## Implemented scope

- Android-only implementation (no iOS code path).
- Foreground service with persistent notification for background/locked-screen operation.
- Media signal handling via `MediaSessionCompat` callback plus `BroadcastReceiver` for media button intents.
- Configurable trigger pattern and timing window (default `pause,play` within `1000ms`).
- Debounce logic to reduce false positives and rapid spam.
- Spotify OAuth (PKCE), secure token storage, token refresh, and like-current-track API calls.
- MIUI-focused onboarding/help actions for battery optimization and autostart.
- Minimal Material 3 UI with drawer-based settings/debug screens.

## Architecture (Clean Architecture)

- `lib/presentation`: screens, drawer, and `Riverpod` state controller.
- `lib/domain`: entities, repository contracts, and testable signal matcher logic.
- `lib/data`: repository implementations, platform channel bridge, Spotify API/OAuth, local settings/token stores.
- `android/app/src/main/kotlin/...`: native Android foreground service, media receiver, boot restart receiver, and worker.

### State management choice

`Riverpod` was selected because it keeps business logic out of widgets, supports explicit dependency injection, and makes controller logic unit-testable.

## Key files

- Flutter entry/app shell: `lib/main.dart`, `lib/app.dart`
- App state/business logic: `lib/presentation/state/app_controller.dart`
- Trigger config UI: `lib/presentation/screens/trigger_config_screen.dart`
- Service bridge (MethodChannel/EventChannel): `lib/data/platform/android_platform_service_repository.dart`
- Spotify auth/API: `lib/data/spotify/spotify_music_service_repository.dart`, `lib/data/spotify/spotify_client.dart`
- Android service: `android/app/src/main/kotlin/com/example/like_spotify_mobile_app/MediaButtonForegroundService.kt`
- Android media button receiver: `android/app/src/main/kotlin/com/example/like_spotify_mobile_app/MediaButtonReceiver.kt`
- Android boot recovery receiver: `android/app/src/main/kotlin/com/example/like_spotify_mobile_app/BootCompletedReceiver.kt`
- Android background like worker: `android/app/src/main/kotlin/com/example/like_spotify_mobile_app/SpotifyLikeWorker.kt`

## Build and run

1. Configure a Spotify app in Spotify Developer Dashboard.
2. Add redirect URI: `likespotify://auth-callback`.
3. Run:

```bash
flutter pub get
flutter build apk --release --dart-define=SPOTIFY_CLIENT_ID=your_client_id --dart-define=SPOTIFY_REDIRECT_URI=likespotify://auth-callback
```

## Permissions and Android integration

- Manifest permissions include:
	- `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MEDIA_PLAYBACK`
	- `POST_NOTIFICATIONS` (Android 13+ runtime prompt is handled)
	- `INTERNET`, `WAKE_LOCK`, `RECEIVE_BOOT_COMPLETED`
	- `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`
- Foreground notification persists while listener is active.
- Boot receiver restarts listener if user previously enabled it.

## MIUI handling

- Detects Xiaomi/Redmi/Poco manufacturer.
- Provides guided steps in UI for:
	- disabling battery restrictions,
	- enabling autostart,
	- keeping app locked in recents.
- Opens settings intents where MIUI exposes them.

## Trigger configuration behavior

- Pattern is stored as comma-separated sequence (e.g., `pause,play`, `pause,play,pause`).
- Window and debounce are configurable from UI.
- Default: `pause,play` in `1000ms` with debounce `650ms`.

## Error handling covered

- No track playing (Spotify returns 204): action skipped and logged.
- Service disconnected / token missing: logged and fails gracefully.
- Token expired: refresh token flow attempted.
- Offline: command skipped and logged.
- Rapid signal spam: debounce guard.

## Android policy limits and best workaround

Some requirements are constrained by Android OEM/system behavior:

1. **Aggressive OEM process killing (especially MIUI)**
	 - Limitation: foreground services can still be killed by OEM policies/user battery modes.
	 - Workaround: battery optimization exemption + MIUI autostart + user education flows (implemented).

2. **Media button dispatch ownership**
	 - Limitation: only active media sessions and system routing receive all media button events consistently.
	 - Workaround: use `MediaSession` callback + `MEDIA_BUTTON` receiver fallback; keep listener active in foreground service (implemented).

3. **Notification permission on Android 13+**
	 - Limitation: without permission, foreground service UX can degrade and user may miss status controls.
	 - Workaround: explicit permission flow + settings deep link (implemented).

## Non-goals

- No iOS support.
- No iOS-specific abstractions.
- No hidden third-party background "magic" runtime.
