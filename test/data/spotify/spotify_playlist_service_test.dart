import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:like_spotify_mobile_app/data/spotify/spotify_client.dart';
import 'package:like_spotify_mobile_app/data/spotify/spotify_models.dart';
import 'package:like_spotify_mobile_app/data/spotify/spotify_playlist_service.dart';

class MockSpotifyClient extends Mock implements SpotifyClient {}

void main() {
  late MockSpotifyClient mockClient;
  late SpotifyPlaylistService service;
  const token = 'test-token';

  setUp(() {
    mockClient = MockSpotifyClient();
    service = SpotifyPlaylistService(mockClient);
  });

  group('findPlaylistByName', () {
    test('returns playlist ID when found on first page', () async {
      when(() => mockClient.getUserPlaylists(token, offset: 0)).thenAnswer(
        (_) async => const SpotifyPlaylistPage(
          items: [
            SpotifyPlaylistItem(id: 'pl-1', name: 'My Playlist'),
            SpotifyPlaylistItem(id: 'pl-2', name: 'Best of the Best'),
          ],
          total: 2,
        ),
      );

      final id = await service.findPlaylistByName(token, 'Best of the Best');
      expect(id, 'pl-2');
    });

    test('returns null when playlist not found', () async {
      when(() => mockClient.getUserPlaylists(token, offset: 0)).thenAnswer(
        (_) async => const SpotifyPlaylistPage(items: [], total: 0),
      );

      final id = await service.findPlaylistByName(token, 'Nonexistent');
      expect(id, isNull);
    });

    test('paginates through all pages', () async {
      final page1 = SpotifyPlaylistPage(
        items: List<SpotifyPlaylistItem>.generate(
          50,
          (i) => SpotifyPlaylistItem(id: 'pl-$i', name: 'Playlist $i'),
        ),
        total: 51,
      );
      const page2 = SpotifyPlaylistPage(
        items: [SpotifyPlaylistItem(id: 'target', name: 'Target Playlist')],
        total: 51,
      );

      when(() => mockClient.getUserPlaylists(token, offset: 0))
          .thenAnswer((_) async => page1);
      when(() => mockClient.getUserPlaylists(token, offset: 50))
          .thenAnswer((_) async => page2);

      final id = await service.findPlaylistByName(token, 'Target Playlist');
      expect(id, 'target');
    });

    test('is case-insensitive', () async {
      when(() => mockClient.getUserPlaylists(token, offset: 0)).thenAnswer(
        (_) async => const SpotifyPlaylistPage(
          items: [SpotifyPlaylistItem(id: 'pl-1', name: 'MY PLAYLIST')],
          total: 1,
        ),
      );

      final id = await service.findPlaylistByName(token, 'my playlist');
      expect(id, 'pl-1');
    });

    test('caches results and avoids duplicate API calls', () async {
      when(() => mockClient.getUserPlaylists(token, offset: 0)).thenAnswer(
        (_) async => const SpotifyPlaylistPage(
          items: [SpotifyPlaylistItem(id: 'cached-id', name: 'Cached')],
          total: 1,
        ),
      );

      // First call — hits API
      await service.findPlaylistByName(token, 'Cached');
      // Second call — should use cache
      final id = await service.findPlaylistByName(token, 'Cached');

      expect(id, 'cached-id');
      verify(() => mockClient.getUserPlaylists(token, offset: 0)).called(1);
    });
  });

  group('ensurePlaylist', () {
    test('returns existing playlist without creating', () async {
      when(() => mockClient.getUserPlaylists(token, offset: 0)).thenAnswer(
        (_) async => const SpotifyPlaylistPage(
          items: [SpotifyPlaylistItem(id: 'exists', name: 'Existing')],
          total: 1,
        ),
      );

      final id = await service.ensurePlaylist(token, 'Existing');
      expect(id, 'exists');
      verifyNever(() => mockClient.createPlaylist(
            token,
            userId: any(named: 'userId'),
            name: any(named: 'name'),
          ));
    });

    test('creates playlist when not found and createIfMissing=true', () async {
      when(() => mockClient.getUserPlaylists(token, offset: 0)).thenAnswer(
        (_) async => const SpotifyPlaylistPage(items: [], total: 0),
      );
      when(() => mockClient.getCurrentUserId(token))
          .thenAnswer((_) async => 'user-123');
      when(() => mockClient.createPlaylist(
            token,
            userId: 'user-123',
            name: 'New Playlist',
          )).thenAnswer((_) async => 'new-pl-id');

      final id = await service.ensurePlaylist(token, 'New Playlist');
      expect(id, 'new-pl-id');
    });

    test('returns null when not found and createIfMissing=false', () async {
      when(() => mockClient.getUserPlaylists(token, offset: 0)).thenAnswer(
        (_) async => const SpotifyPlaylistPage(items: [], total: 0),
      );

      final id = await service.ensurePlaylist(
        token,
        'Nonexistent',
        createIfMissing: false,
      );
      expect(id, isNull);
    });
  });

  group('cache invalidation', () {
    test('invalidateCache forces re-fetch on next call', () async {
      when(() => mockClient.getUserPlaylists(token, offset: 0)).thenAnswer(
        (_) async => const SpotifyPlaylistPage(
          items: [SpotifyPlaylistItem(id: 'pl-1', name: 'Test')],
          total: 1,
        ),
      );

      await service.findPlaylistByName(token, 'Test');
      service.invalidateCache();
      await service.findPlaylistByName(token, 'Test');

      verify(() => mockClient.getUserPlaylists(token, offset: 0)).called(2);
    });
  });
}
