class SpotifyAuthState {
  final String? accessToken;
  final String? refreshToken;
  final DateTime? expiresAt;
  final bool connected;

  const SpotifyAuthState({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresAt,
    required this.connected,
  });

  const SpotifyAuthState.disconnected()
      : accessToken = null,
        refreshToken = null,
        expiresAt = null,
        connected = false;

  bool get isExpired =>
      expiresAt != null && DateTime.now().isAfter(expiresAt!.toUtc());
}
