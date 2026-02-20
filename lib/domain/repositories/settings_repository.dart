import '../entities/trigger_config.dart';

abstract class SettingsRepository {
  Future<TriggerConfig> loadTriggerConfig();
  Future<void> saveTriggerConfig(TriggerConfig config);
  Future<bool> loadServiceEnabled();
  Future<void> saveServiceEnabled(bool enabled);
  Future<List<String>> loadLogs();
  Future<void> appendLog(String message);
  Future<void> clearLogs();
}
