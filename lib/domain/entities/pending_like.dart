class PendingLike {
  final String trackId;
  final String trackName;
  final List<String> artistIds;
  final List<String> artistNames;
  final DateTime queuedAt;

  const PendingLike({
    required this.trackId,
    required this.trackName,
    required this.artistIds,
    required this.artistNames,
    required this.queuedAt,
  });

  String get trackUri => 'spotify:track:$trackId';

  Map<String, dynamic> toJson() => <String, dynamic>{
        'trackId': trackId,
        'trackName': trackName,
        'artistIds': artistIds,
        'artistNames': artistNames,
        'queuedAt': queuedAt.toIso8601String(),
      };

  factory PendingLike.fromJson(Map<String, dynamic> json) => PendingLike(
        trackId: json['trackId'] as String,
        trackName: json['trackName'] as String,
        artistIds: List<String>.from(json['artistIds'] as List<dynamic>),
        artistNames: List<String>.from(json['artistNames'] as List<dynamic>),
        queuedAt: DateTime.parse(json['queuedAt'] as String),
      );
}
