import '../entities/rule_config.dart';
import '../entities/trigger_config.dart';

abstract class PlatformServiceRepository {
  Future<void> startForegroundListener();
  Future<void> stopForegroundListener();
  Future<bool> isServiceEnabled();
  Future<void> updateTriggerConfig(TriggerConfig config);
  Future<bool> isIgnoringBatteryOptimizations();
  Future<void> openIgnoreBatteryOptimizationSettings();
  Future<void> openBatteryOptimizationSettings();
  Future<void> openNotificationSettings();
  Future<bool> isNotificationListenerEnabled();
  Future<void> openNotificationListenerSettings();
  Future<bool> isMiuiDevice();
  Future<void> openMiuiAutostartSettings();
  Future<bool> isSpotifyInstalled();
  Future<bool> openSpotify();
  Future<void> updateRuleConfig(RuleConfig config);
  Stream<Map<String, dynamic>> events();
  Future<void> syncSpotifyTokens({
    required String accessToken,
    required String refreshToken,
    required int expiresAtEpochSec,
    required String clientId,
  });
  Future<void> syncSupabaseConfig({
    required String supabaseUrl,
    required String supabaseAnonKey,
  });
  Future<void> playFeedbackTone({required bool success});
}
