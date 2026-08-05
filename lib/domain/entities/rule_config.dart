import '../../core/app_constants.dart';

class RuleConfig {
  final bool archiveRemoveEnabled;
  final String archivePlaylistName;
  final bool bestOfEnabled;
  final String bestOfPlaylistName;
  final int bestOfThreshold;
  final bool followArtistEnabled;
  final int followArtistThreshold;

  const RuleConfig({
    required this.archiveRemoveEnabled,
    required this.archivePlaylistName,
    required this.bestOfEnabled,
    required this.bestOfPlaylistName,
    required this.bestOfThreshold,
    required this.followArtistEnabled,
    required this.followArtistThreshold,
  });

  factory RuleConfig.defaults() {
    return const RuleConfig(
      archiveRemoveEnabled: true,
      archivePlaylistName: AppConstants.defaultArchivePlaylistName,
      bestOfEnabled: true,
      bestOfPlaylistName: AppConstants.defaultBestOfPlaylistName,
      bestOfThreshold: 3,
      followArtistEnabled: true,
      followArtistThreshold: 5,
    );
  }

  RuleConfig copyWith({
    bool? archiveRemoveEnabled,
    String? archivePlaylistName,
    bool? bestOfEnabled,
    String? bestOfPlaylistName,
    int? bestOfThreshold,
    bool? followArtistEnabled,
    int? followArtistThreshold,
  }) {
    return RuleConfig(
      archiveRemoveEnabled: archiveRemoveEnabled ?? this.archiveRemoveEnabled,
      archivePlaylistName: archivePlaylistName ?? this.archivePlaylistName,
      bestOfEnabled: bestOfEnabled ?? this.bestOfEnabled,
      bestOfPlaylistName: bestOfPlaylistName ?? this.bestOfPlaylistName,
      bestOfThreshold: bestOfThreshold ?? this.bestOfThreshold,
      followArtistEnabled: followArtistEnabled ?? this.followArtistEnabled,
      followArtistThreshold: followArtistThreshold ?? this.followArtistThreshold,
    );
  }

  /// Returns human-readable validation errors, empty when the config is valid.
  List<String> validate() {
    final errors = <String>[];
    if (archiveRemoveEnabled && archivePlaylistName.trim().isEmpty) {
      errors.add('Archive playlist name is required when archive removal is enabled.');
    }
    if (bestOfEnabled && bestOfPlaylistName.trim().isEmpty) {
      errors.add('Best-of playlist name is required when best-of promotion is enabled.');
    }
    if (bestOfEnabled && bestOfThreshold < 1) {
      errors.add('Best-of threshold must be at least 1.');
    }
    if (followArtistEnabled && followArtistThreshold < 1) {
      errors.add('Follow-artist threshold must be at least 1.');
    }
    return errors;
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'archiveRemoveEnabled': archiveRemoveEnabled,
      'archivePlaylistName': archivePlaylistName,
      'bestOfEnabled': bestOfEnabled,
      'bestOfPlaylistName': bestOfPlaylistName,
      'bestOfThreshold': bestOfThreshold,
      'followArtistEnabled': followArtistEnabled,
      'followArtistThreshold': followArtistThreshold,
    };
  }

  factory RuleConfig.fromJson(Map<String, dynamic> json) {
    final defaults = RuleConfig.defaults();
    return RuleConfig(
      archiveRemoveEnabled: json['archiveRemoveEnabled'] as bool? ?? defaults.archiveRemoveEnabled,
      archivePlaylistName: json['archivePlaylistName'] as String? ?? defaults.archivePlaylistName,
      bestOfEnabled: json['bestOfEnabled'] as bool? ?? defaults.bestOfEnabled,
      bestOfPlaylistName: json['bestOfPlaylistName'] as String? ?? defaults.bestOfPlaylistName,
      bestOfThreshold: json['bestOfThreshold'] as int? ?? defaults.bestOfThreshold,
      followArtistEnabled: json['followArtistEnabled'] as bool? ?? defaults.followArtistEnabled,
      followArtistThreshold: json['followArtistThreshold'] as int? ?? defaults.followArtistThreshold,
    );
  }
}
