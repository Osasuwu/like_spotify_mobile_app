# CLAUDE.md — Like Spotify Mobile App

## What this is

Android app (Flutter + Kotlin) that listens for media button patterns (e.g. pause-play) and triggers Spotify actions: like current track, manage playlists, follow artists.

Repo: `Osasuwu/like_spotify_mobile_app`

## Tech stack

- **Framework**: Flutter (Dart) — Android-only, other platforms are stubs
- **State management**: Riverpod (`StateNotifier<AppState>`)
- **Architecture**: Clean Architecture — domain / data / presentation layers
- **Native**: Kotlin — foreground service, MediaSession, broadcast receivers
- **Auth**: Spotify OAuth 2.0 (PKCE flow)
- **Storage**: SharedPreferences + FlutterSecureStorage (tokens)

## Architecture

```
lib/
├── core/              # Constants, shared utilities
├── domain/            # Business logic (pure, no deps)
│   ├── entities/      # TriggerConfig, SpotifyAuthState, AppLog
│   ├── services/      # SignalPatternMatcher
│   └── repositories/  # Interface contracts
├── data/              # Implementations
│   ├── spotify/       # SpotifyClient, token store, music service repo
│   ├── settings/      # SharedPrefs settings repo
│   └── platform/      # Android MethodChannel bridge
└── presentation/
    ├── state/         # AppController (StateNotifier), providers
    ├── screens/       # 7 screens (main, trigger config, logs, etc.)
    └── widgets/       # Reusable UI components

android/app/src/main/kotlin/.../
├── MediaButtonForegroundService.kt  # Background service
├── MediaEventPatternDetector.kt     # Pattern matching (Kotlin mirror)
├── SpotifyLikeWorker.kt             # WorkManager job
├── PlaybackNotificationListenerService.kt
├── MediaButtonReceiver.kt
├── BootCompletedReceiver.kt
├── MainActivity.kt
└── AppConstants.kt
```

## Commands

```bash
flutter pub get           # Install dependencies
flutter analyze           # Lint check
flutter test              # Run all tests
flutter test --coverage   # Run tests with coverage
flutter build apk --release --dart-define-from-file=.env            # Build APK (reads .env)
```

## Key files

| What | Where |
|------|-------|
| Entry point | `lib/main.dart` |
| State machine | `lib/presentation/state/app_controller.dart` |
| Core algorithm | `lib/domain/services/signal_pattern_matcher.dart` |
| Spotify OAuth | `lib/data/spotify/spotify_client.dart` |
| Repository interfaces | `lib/domain/repositories/` |
| Android service | `android/.../MediaButtonForegroundService.kt` |
| Constants | `lib/core/app_constants.dart` |

## Testing

- Framework: `flutter_test` + `mocktail`
- Tests mirror source structure: `test/domain/`, `test/data/`, `test/presentation/`
- Domain layer tests are pure (no mocks needed)
- Data/state layer tests mock repository interfaces with `mocktail`
- Run: `flutter test`

## Spotify setup

Requires a Spotify Developer App:
1. Create app at https://developer.spotify.com/dashboard
2. Set redirect URI: `likespotify://auth-callback`
3. Copy `.env.example` to `.env` and fill in values
4. Build with `--dart-define-from-file=.env`
