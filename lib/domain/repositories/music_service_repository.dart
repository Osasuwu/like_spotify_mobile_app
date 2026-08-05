import '../entities/like_result.dart';
import '../entities/pending_like.dart';
import '../entities/spotify_auth_state.dart';
import '../entities/track_info.dart';

abstract class MusicServiceRepository {
  Future<SpotifyAuthState> getAuthState();
  Future<SpotifyAuthState> connectSpotify();
  Future<void> disconnectSpotify();
  Future<LikeResult> likeCurrentTrack();
  Future<LikeResult> likeTrack(TrackInfo trackInfo);
  Future<void> refreshIfNeeded();
  Future<int> processPendingLikes(List<PendingLike> pending);
  Future<Map<String, Map<String, int>>> loadAllLikeCounts();
}
