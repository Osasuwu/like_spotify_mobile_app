import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../../core/app_constants.dart';
import '../../domain/entities/trigger_config.dart';
import '../../domain/repositories/settings_repository.dart';

class SharedPrefsSettingsRepository implements SettingsRepository {
  static const _keyPattern = 'trigger_pattern';
  static const _keyWindow = 'trigger_window_ms';
  static const _keyDebounce = 'trigger_debounce_ms';
  static const _keyServiceEnabled = 'service_enabled';
  static const _keyLogs = 'logs';

  @override
  Future<TriggerConfig> loadTriggerConfig() async {
    final prefs = await SharedPreferences.getInstance();
    return TriggerConfig(
      pattern: prefs.getString(_keyPattern) ?? AppConstants.defaultPattern,
      windowMs: prefs.getInt(_keyWindow) ?? AppConstants.defaultWindowMs,
      debounceMs: prefs.getInt(_keyDebounce) ?? AppConstants.defaultDebounceMs,
    );
  }

  @override
  Future<void> saveTriggerConfig(TriggerConfig config) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyPattern, config.pattern);
    await prefs.setInt(_keyWindow, config.windowMs);
    await prefs.setInt(_keyDebounce, config.debounceMs);
  }

  @override
  Future<bool> loadServiceEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_keyServiceEnabled) ?? false;
  }

  @override
  Future<void> saveServiceEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyServiceEnabled, enabled);
  }

  @override
  Future<List<String>> loadLogs() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_keyLogs);
    if (raw != null) {
      return raw;
    }
    final json = prefs.getString(_keyLogs);
    if (json == null || json.isEmpty) {
      return <String>[];
    }
    return List<String>.from(jsonDecode(json) as List<dynamic>);
  }

  @override
  Future<void> appendLog(String message) async {
    final prefs = await SharedPreferences.getInstance();
    final logs = await loadLogs();
    logs.insert(0, '[${DateTime.now().toIso8601String()}] $message');
    final clipped = logs.take(300).toList(growable: false);
    await prefs.setStringList(_keyLogs, clipped);
  }

  @override
  Future<void> clearLogs() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_keyLogs, <String>[]);
  }
}
