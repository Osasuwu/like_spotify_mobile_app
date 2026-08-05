import '../../domain/entities/app_log.dart';
import '../../domain/entities/like_result.dart';
import '../../domain/entities/rule_config.dart';
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
  final RuleConfig ruleConfig;
  final List<AppLog> logs;
  final String? lastError;
  final LikeResult? lastLikeResult;
  final bool liking;
  final int pendingLikesCount;

  const AppState({
    required this.serviceEnabled,
    required this.loading,
    required this.isMiui,
    required this.batteryOptimized,
    required this.notificationListenerEnabled,
    required this.spotifyInstalled,
    required this.authState,
    required this.triggerConfig,
    required this.ruleConfig,
    required this.logs,
    required this.lastError,
    this.lastLikeResult,
    this.liking = false,
    this.pendingLikesCount = 0,
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
      ruleConfig: RuleConfig.defaults(),
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
    RuleConfig? ruleConfig,
    List<AppLog>? logs,
    String? lastError,
    bool clearError = false,
    LikeResult? lastLikeResult,
    bool clearLikeResult = false,
    bool? liking,
    int? pendingLikesCount,
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
      ruleConfig: ruleConfig ?? this.ruleConfig,
      logs: logs ?? this.logs,
      lastError: clearError ? null : (lastError ?? this.lastError),
      lastLikeResult: clearLikeResult ? null : (lastLikeResult ?? this.lastLikeResult),
      liking: liking ?? this.liking,
      pendingLikesCount: pendingLikesCount ?? this.pendingLikesCount,
    );
  }
}
