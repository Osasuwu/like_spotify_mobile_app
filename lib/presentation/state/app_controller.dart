import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../core/app_constants.dart';
import '../../data/spotify/spotify_music_service_repository.dart';
import '../../domain/entities/app_log.dart';
import '../../domain/entities/pending_like.dart';
import '../../domain/entities/rule_config.dart';
import '../../domain/entities/spotify_auth_state.dart';
import '../../domain/entities/track_info.dart';
import '../../domain/entities/trigger_config.dart';
import '../../domain/repositories/music_service_repository.dart';
import '../../domain/repositories/platform_service_repository.dart';
import '../../domain/repositories/settings_repository.dart';
import 'app_state.dart';

class AppController extends StateNotifier<AppState> {
  AppController({
    required SettingsRepository settingsRepository,
    required PlatformServiceRepository platformServiceRepository,
    required MusicServiceRepository musicServiceRepository,
    required AppLinks appLinks,
    this.supabaseUrl = '',
    this.supabaseAnonKey = '',
  })  : _settingsRepository = settingsRepository,
        _platformServiceRepository = platformServiceRepository,
        _musicServiceRepository = musicServiceRepository,
        _appLinks = appLinks,
        super(
          AppState.initial(
            const TriggerConfig(
              pattern: AppConstants.defaultPattern,
              windowMs: AppConstants.defaultWindowMs,
              debounceMs: AppConstants.defaultDebounceMs,
            ),
          ),
        ) {
    _initialize();
  }

  final SettingsRepository _settingsRepository;
  final PlatformServiceRepository _platformServiceRepository;
  final MusicServiceRepository _musicServiceRepository;
  final AppLinks _appLinks;
  final String supabaseUrl;
  final String supabaseAnonKey;

  StreamSubscription<Map<String, dynamic>>? _nativeEventsSub;
  StreamSubscription<Uri>? _linkSub;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;

  Future<void> _initialize() async {
    state = state.copyWith(loading: true, clearError: true);
    try {
      final config = await _settingsRepository.loadTriggerConfig();
      final serviceEnabled = await _platformServiceRepository.isServiceEnabled();
      final auth = await _musicServiceRepository.getAuthState();
      final ruleConfig = await _settingsRepository.loadRuleConfig();
      final batteryIgnored =
          await _platformServiceRepository.isIgnoringBatteryOptimizations();
        final notificationListenerEnabled =
          await _platformServiceRepository.isNotificationListenerEnabled();
      final isMiui = await _platformServiceRepository.isMiuiDevice();
      final spotifyInstalled = await _platformServiceRepository.isSpotifyInstalled();
      final logLines = await _settingsRepository.loadLogs();

      await _platformServiceRepository.updateTriggerConfig(config);
      await _platformServiceRepository.updateRuleConfig(ruleConfig);
      await _platformServiceRepository.syncSupabaseConfig(
        supabaseUrl: supabaseUrl,
        supabaseAnonKey: supabaseAnonKey,
      );

      state = state.copyWith(
        loading: false,
        triggerConfig: config,
        serviceEnabled: serviceEnabled,
        authState: auth,
        batteryOptimized: !batteryIgnored,
        notificationListenerEnabled: notificationListenerEnabled,
        isMiui: isMiui,
        spotifyInstalled: spotifyInstalled,
        ruleConfig: ruleConfig,
        logs: logLines
            .map((line) => AppLog(at: DateTime.now().toUtc(), message: line))
            .toList(growable: false),
      );

      // Load pending likes count
      final pendingLikes = await _settingsRepository.loadPendingLikes();
      if (pendingLikes.isNotEmpty) {
        state = state.copyWith(pendingLikesCount: pendingLikes.length);
      }

      _nativeEventsSub ??=
          _platformServiceRepository.events().listen(_onNativeEvent);
      _linkSub ??= _appLinks.uriLinkStream.listen(_onIncomingLink);
      _connectivitySub ??= Connectivity()
          .onConnectivityChanged
          .listen(_onConnectivityChanged);
    } catch (error) {
      state = state.copyWith(
        loading: false,
        lastError: error.toString(),
      );
    }
  }

  Future<void> toggleService(bool enabled) async {
    try {
      await ensureRuntimePermissions();
      if (enabled) {
        await _platformServiceRepository.startForegroundListener();
      } else {
        await _platformServiceRepository.stopForegroundListener();
      }
      await _settingsRepository.saveServiceEnabled(enabled);
      state = state.copyWith(serviceEnabled: enabled, clearError: true);
      await addLog('Service ${enabled ? 'enabled' : 'disabled'}');
    } catch (error) {
      state = state.copyWith(lastError: error.toString());
    }
  }

  Future<void> ensureRuntimePermissions() async {
    final notificationStatus = await Permission.notification.status;
    if (notificationStatus.isGranted) {
      await addLog('Notification permission already granted');
      return;
    }

    final requested = await Permission.notification.request();
    if (requested.isGranted) {
      await addLog('Notification permission granted');
    } else if (requested.isPermanentlyDenied) {
      await addLog('Notification permission permanently denied; opening app settings');
      await _platformServiceRepository.openNotificationSettings();
    } else {
      await addLog('Notification permission denied');
    }
  }

  Future<void> connectSpotify() async {
    try {
      if (!state.spotifyInstalled) {
        await addLog('Spotify app is not installed.');
      }
      await _musicServiceRepository.connectSpotify();
      await addLog('Waiting for Spotify OAuth callback...');
    } catch (error) {
      state = state.copyWith(lastError: error.toString());
    }
  }

  Future<void> disconnectSpotify() async {
    await _musicServiceRepository.disconnectSpotify();
    state = state.copyWith(
      authState: const SpotifyAuthState.disconnected(),
      clearError: true,
    );
    await addLog('Spotify disconnected');
  }

  Future<void> saveTriggerConfig(TriggerConfig config) async {
    await _settingsRepository.saveTriggerConfig(config);
    await _platformServiceRepository.updateTriggerConfig(config);
    state = state.copyWith(triggerConfig: config, clearError: true);
    await addLog('Trigger config updated to ${config.pattern} (${config.windowMs}ms)');
  }

  Future<void> saveRuleConfig(RuleConfig config) async {
    final normalized = config.copyWith(
      archivePlaylistName: config.archivePlaylistName.trim(),
      bestOfPlaylistName: config.bestOfPlaylistName.trim(),
    );
    final errors = normalized.validate();
    if (errors.isNotEmpty) {
      state = state.copyWith(lastError: errors.join(' '));
      return;
    }
    await _settingsRepository.saveRuleConfig(normalized);
    await _platformServiceRepository.updateRuleConfig(normalized);
    state = state.copyWith(ruleConfig: normalized, clearError: true);
    await addLog('Rule config updated');
  }

  Future<void> requestBatteryOptimizationExemption() async {
    await _platformServiceRepository.openIgnoreBatteryOptimizationSettings();
    await refreshBatteryOptimizationStatus();
  }

  Future<void> openBatteryOptimizationSettings() async {
    await _platformServiceRepository.openBatteryOptimizationSettings();
  }

  Future<void> openMiuiAutostartSettings() async {
    await _platformServiceRepository.openMiuiAutostartSettings();
  }

  Future<void> openNotificationSettings() async {
    await _platformServiceRepository.openNotificationSettings();
  }

  Future<void> openNotificationListenerSettings() async {
    await _platformServiceRepository.openNotificationListenerSettings();
    await addLog('Opened notification access settings; enable access and tap refresh');
  }

  Future<void> refreshNotificationListenerStatus() async {
    final enabled = await _platformServiceRepository.isNotificationListenerEnabled();
    state = state.copyWith(notificationListenerEnabled: enabled);
    if (!enabled) {
      await addLog('Notification access is disabled; playback-state fallback is unavailable');
    }
  }

  Future<void> refreshBatteryOptimizationStatus() async {
    final ignored = await _platformServiceRepository.isIgnoringBatteryOptimizations();
    state = state.copyWith(batteryOptimized: !ignored);
  }

  Future<void> likeCurrentTrackNow() async {
    try {
      state = state.copyWith(clearError: true, clearLikeResult: true, liking: true);
      final result = await _musicServiceRepository.likeCurrentTrack();
      state = state.copyWith(lastLikeResult: result, liking: false);
      await addLog('Liked: ${result.trackName} (x${result.trackLikeCount})');
      if (result.removedFromArchive) {
        await addLog('Removed from archive playlist');
      }
      if (result.addedToBestOf) {
        await addLog('Added to best-of playlist');
      }
      if (result.followedArtistNames.isNotEmpty) {
        await addLog('Auto-followed: ${result.followedArtistNames.join(", ")}');
      }
    } catch (error) {
      state = state.copyWith(lastError: error.toString(), liking: false);
      await addLog('Like command failed: $error');
      // Try to queue for offline retry — we need the track info.
      // If we can still reach Spotify to get current track, queue it.
      await _tryQueueCurrentTrack();
    }
  }

  Future<void> _tryQueueCurrentTrack() async {
    try {
      // Attempt to get current track info for queuing — may also fail if fully offline
      final repository = _musicServiceRepository;
      if (repository is! SpotifyMusicServiceRepository) return;

      final auth = await repository.getAuthState();
      if (!auth.connected || auth.accessToken == null) return;

      // If we can't even get track info, nothing to queue
    } catch (_) {
      // Fully offline — can't queue without track info
    }
  }

  Future<void> _onConnectivityChanged(List<ConnectivityResult> result) async {
    if (result.contains(ConnectivityResult.none)) return;

    final pending = await _settingsRepository.loadPendingLikes();
    if (pending.isEmpty) return;

    await addLog('Online — processing ${pending.length} queued like(s)...');
    final processed = await _musicServiceRepository.processPendingLikes(pending);
    if (processed > 0) {
      await addLog('Processed $processed queued like(s)');
      final remaining = await _settingsRepository.loadPendingLikes();
      state = state.copyWith(pendingLikesCount: remaining.length);
    }
  }

  /// Queue a track for offline retry.
  Future<void> queueTrackForLater(TrackInfo trackInfo) async {
    final pending = PendingLike(
      trackId: trackInfo.trackId,
      trackName: trackInfo.trackName,
      artistIds: trackInfo.artistIds,
      artistNames: trackInfo.artistNames,
      queuedAt: DateTime.now().toUtc(),
    );
    await _settingsRepository.addPendingLike(pending);
    final count = (await _settingsRepository.loadPendingLikes()).length;
    state = state.copyWith(pendingLikesCount: count);
    await addLog('Queued for later: ${trackInfo.trackName}');
  }

  Future<void> clearLogs() async {
    await _settingsRepository.clearLogs();
    state = state.copyWith(logs: <AppLog>[]);
  }

  Future<void> addLog(String message) async {
    await _settingsRepository.appendLog(message);
    final logs = await _settingsRepository.loadLogs();
    state = state.copyWith(
      logs: logs
          .map((line) => AppLog(at: DateTime.now().toUtc(), message: line))
          .toList(growable: false),
    );
  }

  Future<void> _onIncomingLink(Uri uri) async {
    try {
      final repository = _musicServiceRepository;
      if (repository is SpotifyMusicServiceRepository) {
        final handled = await repository.tryHandleIncomingUri(uri);
        if (handled) {
          final auth = await repository.getAuthState();
          state = state.copyWith(authState: auth, clearError: true);
          await addLog('Spotify connected successfully');
        }
      }
    } catch (error) {
      state = state.copyWith(lastError: 'OAuth callback failed: $error');
    }
  }

  void _onNativeEvent(Map<String, dynamic> event) {
    final type = event['type'] as String?;
    final value = event['value'];

    if (type == 'state' && value is bool) {
      state = state.copyWith(serviceEnabled: value);
      return;
    }

    if (type == 'log' && value is String) {
      unawaited(addLog('[native] $value'));
      return;
    }

    if (type == 'media' && value is String) {
      unawaited(addLog('Media event: $value'));
      return;
    }

    if (type == 'trigger_like') {
      unawaited(_handleNativeTriggerLike());
      return;
    }
  }

  Future<void> _handleNativeTriggerLike() async {
    try {
      state = state.copyWith(clearError: true, clearLikeResult: true, liking: true);
      final result = await _musicServiceRepository.likeCurrentTrack();
      state = state.copyWith(lastLikeResult: result, liking: false);

      await _platformServiceRepository.playFeedbackTone(success: result.success);

      await addLog('Liked: ${result.trackName} (x${result.trackLikeCount})');
      if (result.removedFromArchive) {
        await addLog('Removed from archive playlist');
      }
      if (result.addedToBestOf) {
        await addLog('Added to best-of playlist');
      }
      if (result.followedArtistNames.isNotEmpty) {
        await addLog('Auto-followed: ${result.followedArtistNames.join(", ")}');
      }
    } catch (error) {
      state = state.copyWith(lastError: error.toString(), liking: false);
      await _platformServiceRepository.playFeedbackTone(success: false);
      await addLog('Like from trigger failed: $error');
      await _tryQueueCurrentTrack();
    }
  }

  @override
  void dispose() {
    _nativeEventsSub?.cancel();
    _linkSub?.cancel();
    _connectivitySub?.cancel();
    super.dispose();
  }
}
