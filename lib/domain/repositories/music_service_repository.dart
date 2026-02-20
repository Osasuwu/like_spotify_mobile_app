import '../entities/spotify_auth_state.dart';

abstract class MusicServiceRepository {
  Future<SpotifyAuthState> getAuthState();
  Future<SpotifyAuthState> connectSpotify();
  Future<void> disconnectSpotify();
  Future<void> likeCurrentTrack();
  Future<void> refreshIfNeeded();
}
