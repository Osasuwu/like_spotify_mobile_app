import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../../domain/repositories/like_count_repository.dart';
import 'shared_prefs_like_count_repository.dart';

/// Tries Supabase RPC first, falls back to local SharedPreferences.
class SupabaseLikeCountRepository implements LikeCountRepository {
  final String supabaseUrl;
  final String supabaseAnonKey;
  final String? Function() userIdGetter;
  final SharedPrefsLikeCountRepository _local = SharedPrefsLikeCountRepository();

  SupabaseLikeCountRepository({
    required this.supabaseUrl,
    required this.supabaseAnonKey,
    required this.userIdGetter,
  });

  bool get _supabaseConfigured =>
      supabaseUrl.isNotEmpty && supabaseAnonKey.isNotEmpty;

  @override
  Future<int> incrementTrackLikeCount(String trackId) async {
    if (_supabaseConfigured) {
      final userId = userIdGetter();
      if (userId != null) {
        final count = await _supabaseIncrement(userId, trackId);
        if (count != null) return count;
      }
    }
    return _local.incrementTrackLikeCount(trackId);
  }

  @override
  Future<int> getTrackLikeCount(String trackId) =>
      _local.getTrackLikeCount(trackId);

  @override
  Future<int> incrementArtistLikeCount(String artistId) =>
      _local.incrementArtistLikeCount(artistId);

  @override
  Future<int> getArtistLikeCount(String artistId) =>
      _local.getArtistLikeCount(artistId);

  @override
  Future<Map<String, int>> loadAllTrackLikeCounts() =>
      _local.loadAllTrackLikeCounts();

  @override
  Future<Map<String, int>> loadAllArtistLikeCounts() =>
      _local.loadAllArtistLikeCounts();

  @override
  Future<DateTime?> getLastLikedAt(String trackId) =>
      _local.getLastLikedAt(trackId);

  @override
  Future<void> recordLikedAt(String trackId, DateTime at) =>
      _local.recordLikedAt(trackId, at);

  Future<int?> _supabaseIncrement(String userId, String trackId) async {
    try {
      final response = await http.post(
        Uri.parse('$supabaseUrl/rest/v1/rpc/increment_track_like'),
        headers: <String, String>{
          'Content-Type': 'application/json',
          'apikey': supabaseAnonKey,
          'Authorization': 'Bearer $supabaseAnonKey',
        },
        body: jsonEncode(<String, String>{
          'p_user_id': userId,
          'p_track_id': trackId,
        }),
      ).timeout(const Duration(seconds: 5));

      if (response.statusCode >= 200 && response.statusCode <= 299) {
        return int.tryParse(response.body.trim());
      }
      debugPrint('Supabase increment failed (${response.statusCode})');
      return null;
    } catch (e) {
      debugPrint('Supabase increment error: $e');
      return null;
    }
  }
}
