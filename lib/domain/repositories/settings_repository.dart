import '../entities/pending_like.dart';
import '../entities/rule_config.dart';
import '../entities/trigger_config.dart';

abstract class SettingsRepository {
  Future<TriggerConfig> loadTriggerConfig();
  Future<void> saveTriggerConfig(TriggerConfig config);
  Future<RuleConfig> loadRuleConfig();
  Future<void> saveRuleConfig(RuleConfig config);
  Future<bool> loadServiceEnabled();
  Future<void> saveServiceEnabled(bool enabled);
  Future<List<String>> loadLogs();
  Future<void> appendLog(String message);
  Future<void> clearLogs();
  Future<List<PendingLike>> loadPendingLikes();
  Future<void> savePendingLikes(List<PendingLike> likes);
  Future<void> addPendingLike(PendingLike like);
  Future<void> removePendingLike(String trackId);
}
