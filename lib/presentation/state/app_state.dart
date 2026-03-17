import '../../domain/entities/app_log.dart';
import '../../domain/entities/spotify_auth_state.dart';
import '../../domain/entities/trigger_config.dart';

class AppState {
  final bool serviceEnabled;
  final bool loading;
  final bool isMiui;
  final bool batteryOptimized;
  final bool notificationListenerEnabled;
  final bool spotifyInstalled;
  final SpotifyAuthState authState;
  final TriggerConfig triggerConfig;
  final String archivePlaylistName;
  final String bestOfPlaylistName;
  final List<AppLog> logs;
  final String? lastError;

  const AppState({
    required this.serviceEnabled,
    required this.loading,
    required this.isMiui,
    required this.batteryOptimized,
    required this.notificationListenerEnabled,
    required this.spotifyInstalled,
    required this.authState,
    required this.triggerConfig,
    required this.archivePlaylistName,
    required this.bestOfPlaylistName,
    required this.logs,
    required this.lastError,
  });

  factory AppState.initial(TriggerConfig config) {
    return AppState(
      serviceEnabled: false,
      loading: false,
      isMiui: false,
      batteryOptimized: true,
      notificationListenerEnabled: false,
      spotifyInstalled: false,
      authState: const SpotifyAuthState.disconnected(),
      triggerConfig: config,
      archivePlaylistName: 'Discover Weekly Archive',
      bestOfPlaylistName: 'Botbotb(Best of the best of the best)',
      logs: const <AppLog>[],
      lastError: null,
    );
  }

  AppState copyWith({
    bool? serviceEnabled,
    bool? loading,
    bool? isMiui,
    bool? batteryOptimized,
    bool? notificationListenerEnabled,
    bool? spotifyInstalled,
    SpotifyAuthState? authState,
    TriggerConfig? triggerConfig,
    String? archivePlaylistName,
    String? bestOfPlaylistName,
    List<AppLog>? logs,
    String? lastError,
    bool clearError = false,
  }) {
    return AppState(
      serviceEnabled: serviceEnabled ?? this.serviceEnabled,
      loading: loading ?? this.loading,
      isMiui: isMiui ?? this.isMiui,
      batteryOptimized: batteryOptimized ?? this.batteryOptimized,
        notificationListenerEnabled:
          notificationListenerEnabled ?? this.notificationListenerEnabled,
      spotifyInstalled: spotifyInstalled ?? this.spotifyInstalled,
      authState: authState ?? this.authState,
      triggerConfig: triggerConfig ?? this.triggerConfig,
      archivePlaylistName: archivePlaylistName ?? this.archivePlaylistName,
      bestOfPlaylistName: bestOfPlaylistName ?? this.bestOfPlaylistName,
      logs: logs ?? this.logs,
      lastError: clearError ? null : (lastError ?? this.lastError),
    );
  }
}
