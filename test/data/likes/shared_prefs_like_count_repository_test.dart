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
}
