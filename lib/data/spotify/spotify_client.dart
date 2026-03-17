import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

import '../../core/app_constants.dart';
import 'spotify_models.dart';

class SpotifyClient {
  final http.Client _http;

  SpotifyClient(this._http);

  String createCodeVerifier({int length = 64}) {
    const chars =
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
    final random = Random.secure();
    return List<String>.generate(
      length,
      (_) => chars[random.nextInt(chars.length)],
      growable: false,
    ).join();
  }

  String codeChallenge(String verifier) {
    final digest = sha256.convert(utf8.encode(verifier));
    return base64Url.encode(digest.bytes).replaceAll('=', '');
  }

  Uri buildAuthorizeUri({
    required String clientId,
    required String redirectUri,
    required String codeChallenge,
    required String state,
  }) {
    return Uri.parse(AppConstants.spotifyAuthorizeUrl).replace(
      queryParameters: <String, String>{
        'client_id': clientId,
        'response_type': 'code',
        'redirect_uri': redirectUri,
        'code_challenge_method': 'S256',
        'code_challenge': codeChallenge,
        'state': state,
        'scope':
            'user-library-modify user-library-read user-read-playback-state user-follow-modify playlist-read-private playlist-read-collaborative playlist-modify-private playlist-modify-public',
      },
    );
  }

  Future<void> launchAuthPage(Uri uri) async {
    final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!launched) {
      throw Exception('Failed to open Spotify authentication page');
    }
  }

  Future<SpotifyTokenResponse> exchangeCode({
    required String code,
    required String clientId,
    required String redirectUri,
    required String codeVerifier,
  }) async {
    final response = await _http.post(
      Uri.parse(AppConstants.spotifyTokenUrl),
      headers: <String, String>{
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: <String, String>{
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirectUri,
        'client_id': clientId,
        'code_verifier': codeVerifier,
      },
    );

    if (response.statusCode < 200 || response.statusCode > 299) {
      throw Exception('Spotify token exchange failed (${response.statusCode})');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return SpotifyTokenResponse(
      accessToken: json['access_token'] as String,
      refreshToken: json['refresh_token'] as String? ?? '',
      expiresInSec: json['expires_in'] as int,
    );
  }

  Future<SpotifyTokenResponse> refreshToken({
    required String refreshToken,
    required String clientId,
  }) async {
    final response = await _http.post(
      Uri.parse(AppConstants.spotifyTokenUrl),
      headers: <String, String>{
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: <String, String>{
        'grant_type': 'refresh_token',
        'refresh_token': refreshToken,
        'client_id': clientId,
      },
    );

    if (response.statusCode < 200 || response.statusCode > 299) {
      throw Exception('Spotify token refresh failed (${response.statusCode})');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return SpotifyTokenResponse(
      accessToken: json['access_token'] as String,
      refreshToken: json['refresh_token'] as String? ?? refreshToken,
      expiresInSec: json['expires_in'] as int,
    );
  }

  Future<String?> currentTrackId(String accessToken) async {
    final response = await _http.get(
      Uri.parse('${AppConstants.spotifyApiBase}/me/player/currently-playing'),
      headers: <String, String>{'Authorization': 'Bearer $accessToken'},
    );

    if (response.statusCode == 204) {
      return null;
    }

    if (response.statusCode < 200 || response.statusCode > 299) {
      throw Exception(
        'Spotify current track failed (${response.statusCode}): ${response.body}',
      );
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final item = json['item'] as Map<String, dynamic>?;
    return item?['id'] as String?;
  }

  Future<void> likeTrack({
    required String trackId,
    required String accessToken,
  }) async {
    final response = await _http.put(
      Uri.parse('${AppConstants.spotifyApiBase}/me/tracks?ids=$trackId'),
      headers: <String, String>{'Authorization': 'Bearer $accessToken'},
    );

    if (response.statusCode < 200 || response.statusCode > 299) {
      throw Exception('Spotify like track failed (${response.statusCode})');
    }
  }
}
