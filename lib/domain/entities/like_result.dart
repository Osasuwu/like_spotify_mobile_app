class LikeResult {
  final String trackId;
  final String trackName;
  final bool trackLiked;
  final bool removedFromArchive;
  final bool addedToBestOf;
  final List<String> followedArtistNames;
  final int trackLikeCount;
  final String? errorMessage;

  const LikeResult({
    required this.trackId,
    required this.trackName,
    required this.trackLiked,
    this.removedFromArchive = false,
    this.addedToBestOf = false,
    this.followedArtistNames = const <String>[],
    this.trackLikeCount = 0,
    this.errorMessage,
  });

  bool get success => trackLiked && errorMessage == null;
}
