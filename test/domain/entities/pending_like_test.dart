import 'package:flutter_test/flutter_test.dart';
import 'package:like_spotify_mobile_app/domain/entities/pending_like.dart';

void main() {
  group('PendingLike', () {
    test('toJson and fromJson roundtrip', () {
      final original = PendingLike(
        trackId: 'track-1',
        trackName: 'My Song',
        artistIds: ['a1', 'a2'],
        artistNames: ['Artist 1', 'Artist 2'],
        queuedAt: DateTime.utc(2025, 1, 15, 10, 30),
      );

      final json = original.toJson();
      final restored = PendingLike.fromJson(json);

      expect(restored.trackId, original.trackId);
      expect(restored.trackName, original.trackName);
      expect(restored.artistIds, original.artistIds);
      expect(restored.artistNames, original.artistNames);
      expect(restored.queuedAt, original.queuedAt);
    });

    test('trackUri returns correct Spotify URI', () {
      final like = PendingLike(
        trackId: 'abc123',
        trackName: 'Test',
        artistIds: const [],
        artistNames: const [],
        queuedAt: DateTime.utc(2025, 1, 1),
      );
      expect(like.trackUri, 'spotify:track:abc123');
    });
  });
}
