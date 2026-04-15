import 'package:app_links/app_links.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import '../../data/likes/shared_prefs_like_count_repository.dart';
import '../../data/likes/supabase_like_count_repository.dart';
import '../../data/platform/android_platform_service_repository.dart';
import '../../data/settings/shared_prefs_settings_repository.dart';
import '../../data/spotify/spotify_client.dart';
import '../../data/spotify/spotify_music_service_repository.dart';
import '../../data/spotify/spotify_token_store.dart';
import '../../domain/repositories/like_count_repository.dart';
import '../../domain/repositories/music_service_repository.dart';
import '../../domain/repositories/platform_service_repository.dart';
import '../../domain/repositories/settings_repository.dart';
import '../../domain/services/signal_pattern_matcher.dart';
import 'app_controller.dart';
import 'app_state.dart';

const _redirectUri = String.fromEnvironment(
  'SPOTIFY_REDIRECT_URI',
  defaultValue: 'likespotify://auth-callback',
);
const _spotifyClientId = String.fromEnvironment('SPOTIFY_CLIENT_ID');
const _supabaseUrl = String.fromEnvironment('SUPABASE_URL');
const _supabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');

final settingsRepositoryProvider = Provider<SettingsRepository>(
  (ref) => SharedPrefsSettingsRepository(),
);

final platformServiceRepositoryProvider = Provider<PlatformServiceRepository>(
  (ref) => AndroidPlatformServiceRepository(),
);

final musicServiceRepositoryProvider = Provider<MusicServiceRepository>((ref) {
  // The repo is created once; SupabaseLikeCountRepository reads cachedUserId
  // lazily at increment time, so null on first call just falls back to local.
  late final SpotifyMusicServiceRepository repo;

  final LikeCountRepository likeCountRepo;
  if (_supabaseUrl.isNotEmpty && _supabaseAnonKey.isNotEmpty) {
    likeCountRepo = SupabaseLikeCountRepository(
      supabaseUrl: _supabaseUrl,
      supabaseAnonKey: _supabaseAnonKey,
      userIdGetter: () => repo.cachedUserId,
    );
  } else {
    likeCountRepo = SharedPrefsLikeCountRepository();
  }

  repo = SpotifyMusicServiceRepository(
    spotifyClient: SpotifyClient(http.Client()),
    tokenStore: SpotifyTokenStore(const FlutterSecureStorage()),
    platformServiceRepository: ref.read(platformServiceRepositoryProvider),
    likeCountRepository: likeCountRepo,
    settingsRepository: ref.read(settingsRepositoryProvider),
    clientId: _spotifyClientId,
    redirectUri: _redirectUri,
  );

  return repo;
});

final appLinksProvider = Provider<AppLinks>((ref) => AppLinks());

final signalPatternMatcherProvider = Provider<SignalPatternMatcher>(
  (ref) => SignalPatternMatcher(),
);

final appControllerProvider =
    StateNotifierProvider<AppController, AppState>((ref) {
  return AppController(
    settingsRepository: ref.read(settingsRepositoryProvider),
    platformServiceRepository: ref.read(platformServiceRepositoryProvider),
    musicServiceRepository: ref.read(musicServiceRepositoryProvider),
    appLinks: ref.read(appLinksProvider),
    supabaseUrl: _supabaseUrl,
    supabaseAnonKey: _supabaseAnonKey,
  );
});
