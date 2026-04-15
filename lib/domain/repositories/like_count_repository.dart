abstract class LikeCountRepository {
  Future<int> incrementTrackLikeCount(String trackId);
  Future<int> getTrackLikeCount(String trackId);
  Future<int> incrementArtistLikeCount(String artistId);
  Future<int> getArtistLikeCount(String artistId);
}
