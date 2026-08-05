import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../../domain/repositories/like_count_repository.dart';

class SharedPrefsLikeCountRepository implements LikeCountRepository {
  static const _keyTrackCounts = 'track_like_counts';
  static const _keyArtistCounts = 'artist_like_counts';

  @override
  Future<int> incrementTrackLikeCount(String trackId) =>
      _increment(_keyTrackCounts, trackId);

  @override
  Future<int> getTrackLikeCount(String trackId) =>
      _getCount(_keyTrackCounts, trackId);

  @override
  Future<int> incrementArtistLikeCount(String artistId) =>
      _increment(_keyArtistCounts, artistId);

  @override
  Future<int> getArtistLikeCount(String artistId) =>
      _getCount(_keyArtistCounts, artistId);

  @override
  Future<Map<String, int>> loadAllTrackLikeCounts() => _loadMap(_keyTrackCounts);

  @override
  Future<Map<String, int>> loadAllArtistLikeCounts() => _loadMap(_keyArtistCounts);

  Future<int> _increment(String key, String itemId) async {
    final map = await _loadMap(key);
    final next = (map[itemId] ?? 0) + 1;
    map[itemId] = next;
    await _saveMap(key, map);
    return next;
  }

  Future<int> _getCount(String key, String itemId) async {
    final map = await _loadMap(key);
    return map[itemId] ?? 0;
  }

  Future<Map<String, int>> _loadMap(String key) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(key);
    if (raw == null || raw.isEmpty) return <String, int>{};
    try {
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      return decoded.map((k, v) => MapEntry(k, v as int));
    } catch (_) {
      return <String, int>{};
    }
  }

  Future<void> _saveMap(String key, Map<String, int> map) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(key, jsonEncode(map));
  }
}
