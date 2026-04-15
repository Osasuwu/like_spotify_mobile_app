import '../entities/pending_like.dart';
import '../entities/trigger_config.dart';

abstract class SettingsRepository {
  Future<TriggerConfig> loadTriggerConfig();
  Future<void> saveTriggerConfig(TriggerConfig config);
  Future<String> loadArchivePlaylistName();
  Future<void> saveArchivePlaylistName(String name);
  Future<String> loadBestOfPlaylistName();
  Future<void> saveBestOfPlaylistName(String name);
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
