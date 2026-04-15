class SpotifyTokenResponse {
  final String accessToken;
  final String refreshToken;
  final int expiresInSec;

  const SpotifyTokenResponse({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresInSec,
  });
}

class SpotifyPlaylistItem {
  final String id;
  final String name;

  const SpotifyPlaylistItem({required this.id, required this.name});
}

class SpotifyPlaylistPage {
  final List<SpotifyPlaylistItem> items;
  final int total;

  const SpotifyPlaylistPage({required this.items, required this.total});

  bool get hasMore => items.length + total > total; // always false — use items.length < limit
}

class SpotifySavedTrackArtist {
  final String id;
  final String name;

  const SpotifySavedTrackArtist({required this.id, required this.name});
}

class SpotifySavedTrack {
  final String id;
  final String name;
  final String uri;
  final List<SpotifySavedTrackArtist> artists;

  const SpotifySavedTrack({
    required this.id,
    required this.name,
    required this.uri,
    required this.artists,
  });
}

class SpotifySavedTrackPage {
  final List<SpotifySavedTrack> items;
  final int total;

  const SpotifySavedTrackPage({required this.items, required this.total});
}
