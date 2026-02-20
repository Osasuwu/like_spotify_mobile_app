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
