class TrackInfo {
  final String trackId;
  final String trackName;
  final List<String> artistIds;
  final List<String> artistNames;

  const TrackInfo({
    required this.trackId,
    required this.trackName,
    required this.artistIds,
    required this.artistNames,
  });

  String get trackUri => 'spotify:track:$trackId';
}
