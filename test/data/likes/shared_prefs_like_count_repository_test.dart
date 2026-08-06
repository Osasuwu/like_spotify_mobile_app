import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:like_spotify_mobile_app/data/likes/shared_prefs_like_count_repository.dart';

void main() {
  late SharedPrefsLikeCountRepository repo;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    repo = SharedPrefsLikeCountRepository();
  });

  group('track like counts', () {
    test('starts at zero for unknown track', () async {
      expect(await repo.getTrackLikeCount('unknown'), 0);
    });

    test('increments from zero to one', () async {
      final count = await repo.incrementTrackLikeCount('track-1');
      expect(count, 1);
    });

    test('increments cumulatively', () async {
      await repo.incrementTrackLikeCount('track-1');
      await repo.incrementTrackLikeCount('track-1');
      final count = await repo.incrementTrackLikeCount('track-1');
      expect(count, 3);
    });

    test('tracks different track IDs independently', () async {
      await repo.incrementTrackLikeCount('track-a');
      await repo.incrementTrackLikeCount('track-a');
      await repo.incrementTrackLikeCount('track-b');

      expect(await repo.getTrackLikeCount('track-a'), 2);
      expect(await repo.getTrackLikeCount('track-b'), 1);
    });

    test('persists across repository instances', () async {
      await repo.incrementTrackLikeCount('track-p');
      await repo.incrementTrackLikeCount('track-p');

      final newRepo = SharedPrefsLikeCountRepository();
      expect(await newRepo.getTrackLikeCount('track-p'), 2);
    });
  });

  group('artist like counts', () {
    test('starts at zero for unknown artist', () async {
      expect(await repo.getArtistLikeCount('unknown'), 0);
    });

    test('increments from zero to one', () async {
      final count = await repo.incrementArtistLikeCount('artist-1');
      expect(count, 1);
    });

    test('increments cumulatively', () async {
      for (var i = 0; i < 5; i++) {
        await repo.incrementArtistLikeCount('artist-x');
      }
      expect(await repo.getArtistLikeCount('artist-x'), 5);
    });

    test('track and artist counts are independent', () async {
      await repo.incrementTrackLikeCount('same-id');
      await repo.incrementArtistLikeCount('same-id');

      expect(await repo.getTrackLikeCount('same-id'), 1);
      expect(await repo.getArtistLikeCount('same-id'), 1);
    });
  });

  group('bulk enumeration', () {
    test('loadAllTrackLikeCounts returns empty map when nothing stored', () async {
      expect(await repo.loadAllTrackLikeCounts(), <String, int>{});
    });

    test('loadAllTrackLikeCounts returns every stored track count', () async {
      await repo.incrementTrackLikeCount('track-a');
      await repo.incrementTrackLikeCount('track-a');
      await repo.incrementTrackLikeCount('track-b');

      expect(await repo.loadAllTrackLikeCounts(), <String, int>{
        'track-a': 2,
        'track-b': 1,
      });
    });

    test('loadAllArtistLikeCounts returns every stored artist count', () async {
      await repo.incrementArtistLikeCount('artist-a');
      await repo.incrementArtistLikeCount('artist-b');
      await repo.incrementArtistLikeCount('artist-b');
      await repo.incrementArtistLikeCount('artist-b');

      expect(await repo.loadAllArtistLikeCounts(), <String, int>{
        'artist-a': 1,
        'artist-b': 3,
      });
    });
  });

  group('last liked at', () {
    test('returns null for a track that was never liked', () async {
      expect(await repo.getLastLikedAt('unknown'), isNull);
    });

    test('records and returns the last-liked timestamp', () async {
      final at = DateTime.utc(2026, 1, 1, 12, 0, 0);
      await repo.recordLikedAt('track-1', at);

      expect(await repo.getLastLikedAt('track-1'), at);
    });

    test('overwrites the previous timestamp for the same track', () async {
      final first = DateTime.utc(2026, 1, 1, 12, 0, 0);
      final second = DateTime.utc(2026, 1, 1, 12, 30, 0);
      await repo.recordLikedAt('track-1', first);
      await repo.recordLikedAt('track-1', second);

      expect(await repo.getLastLikedAt('track-1'), second);
    });

    test('tracks last-liked timestamps independently per track', () async {
      final at1 = DateTime.utc(2026, 1, 1, 12, 0, 0);
      final at2 = DateTime.utc(2026, 1, 2, 8, 0, 0);
      await repo.recordLikedAt('track-a', at1);
      await repo.recordLikedAt('track-b', at2);

      expect(await repo.getLastLikedAt('track-a'), at1);
      expect(await repo.getLastLikedAt('track-b'), at2);
    });

    test('persists across repository instances', () async {
      final at = DateTime.utc(2026, 1, 1, 12, 0, 0);
      await repo.recordLikedAt('track-p', at);

      final newRepo = SharedPrefsLikeCountRepository();
      expect(await newRepo.getLastLikedAt('track-p'), at);
    });
  });
}
