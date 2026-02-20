import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../core/app_constants.dart';
import '../../data/spotify/spotify_music_service_repository.dart';
import '../../domain/entities/app_log.dart';
import '../../domain/entities/spotify_auth_state.dart';
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

  StreamSubscription<Map<String, dynamic>>? _nativeEventsSub;
  StreamSubscription<Uri>? _linkSub;

  Future<void> _initialize() async {
    state = state.copyWith(loading: true, clearError: true);
    try {
      final config = await _settingsRepository.loadTriggerConfig();
      final serviceEnabled = await _platformServiceRepository.isServiceEnabled();
      final auth = await _musicServiceRepository.getAuthState();
      final batteryIgnored =
          await _platformServiceRepository.isIgnoringBatteryOptimizations();
        final notificationListenerEnabled =
          await _platformServiceRepository.isNotificationListenerEnabled();
      final isMiui = await _platformServiceRepository.isMiuiDevice();
      final spotifyInstalled = await _platformServiceRepository.isSpotifyInstalled();
      final logLines = await _settingsRepository.loadLogs();

      await _platformServiceRepository.updateTriggerConfig(config);

      state = state.copyWith(
        loading: false,
        triggerConfig: config,
        serviceEnabled: serviceEnabled,
        authState: auth,
        batteryOptimized: !batteryIgnored,
        notificationListenerEnabled: notificationListenerEnabled,
        isMiui: isMiui,
        spotifyInstalled: spotifyInstalled,
        logs: logLines
            .map((line) => AppLog(at: DateTime.now().toUtc(), message: line))
            .toList(growable: false),
      );

      _nativeEventsSub ??=
          _platformServiceRepository.events().listen(_onNativeEvent);
      _linkSub ??= _appLinks.uriLinkStream.listen(_onIncomingLink);
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
    final connection = await Connectivity().checkConnectivity();
    if (connection.contains(ConnectivityResult.none)) {
      state = state.copyWith(lastError: 'Network unavailable');
      await addLog('Like command skipped: offline');
      return;
    }

    try {
      await _musicServiceRepository.likeCurrentTrack();
      await addLog('Like command sent successfully');
    } catch (error) {
      state = state.copyWith(lastError: error.toString());
      await addLog('Like command failed: $error');
    }
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
  }

  @override
  void dispose() {
    _nativeEventsSub?.cancel();
    _linkSub?.cancel();
    super.dispose();
  }
}
