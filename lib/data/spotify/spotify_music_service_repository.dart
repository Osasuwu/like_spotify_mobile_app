import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../domain/entities/spotify_auth_state.dart';
import '../../domain/repositories/music_service_repository.dart';
import '../../domain/repositories/platform_service_repository.dart';
import 'spotify_client.dart';
import 'spotify_token_store.dart';

class SpotifyMusicServiceRepository implements MusicServiceRepository {
  SpotifyMusicServiceRepository({
    required SpotifyClient spotifyClient,
    required SpotifyTokenStore tokenStore,
    required PlatformServiceRepository platformServiceRepository,
    required String clientId,
    required String redirectUri,
  })  : _spotifyClient = spotifyClient,
        _tokenStore = tokenStore,
        _platformServiceRepository = platformServiceRepository,
        _clientId = clientId,
        _redirectUri = redirectUri;

  final SpotifyClient _spotifyClient;
  final SpotifyTokenStore _tokenStore;
  final PlatformServiceRepository _platformServiceRepository;
  final String _clientId;
  final String _redirectUri;

  String? _pendingVerifier;
  String? _pendingState;

  @override
  Future<SpotifyAuthState> getAuthState() async {
    final state = await _readStoredAuthState();
    if (!_shouldRefresh(state)) {
      return state;
    }

    try {
      return await _refreshAuthState(state);
    } catch (error, stackTrace) {
      // Keep existing state available when refresh fails (for example offline startup).
      debugPrint('Spotify token refresh skipped in getAuthState: $error\n$stackTrace');
      return state;
    }
  }

  Future<SpotifyAuthState> _readStoredAuthState() async {
    final access = await _tokenStore.readAccessToken();
    final refresh = await _tokenStore.readRefreshToken();
    final expiry = await _tokenStore.readExpiryEpochSec();

    if (refresh == null || refresh.isEmpty || expiry == null) {
      return const SpotifyAuthState.disconnected();
    }

    return SpotifyAuthState(
      accessToken: access,
      refreshToken: refresh,
      expiresAt: DateTime.fromMillisecondsSinceEpoch(expiry * 1000, isUtc: true),
      connected: true,
    );
  }

  bool _shouldRefresh(SpotifyAuthState state) {
    if (!state.connected) {
      return false;
    }
    final access = state.accessToken;
    return state.isExpired || access == null || access.isEmpty;
  }

  Future<SpotifyAuthState> _refreshAuthState(SpotifyAuthState state) async {
    final refresh = state.refreshToken;
    if (refresh == null || refresh.isEmpty) {
      throw Exception('Missing refresh token');
    }

    final refreshed = await _spotifyClient.refreshToken(
      refreshToken: refresh,
      clientId: _clientId,
    );
    final expiresAt = DateTime.now().toUtc().add(Duration(seconds: refreshed.expiresInSec));
    final expiresAtEpochSec = expiresAt.millisecondsSinceEpoch ~/ 1000;

    await _tokenStore.save(
      accessToken: refreshed.accessToken,
      refreshToken: refreshed.refreshToken,
      expiresAtEpochSec: expiresAtEpochSec,
    );

    await _platformServiceRepository.syncSpotifyTokens(
      accessToken: refreshed.accessToken,
      refreshToken: refreshed.refreshToken,
      expiresAtEpochSec: expiresAtEpochSec,
      clientId: _clientId,
    );

    return SpotifyAuthState(
      accessToken: refreshed.accessToken,
      refreshToken: refreshed.refreshToken,
      expiresAt: expiresAt,
      connected: true,
    );
  }

  Future<Uri> beginSpotifyAuthorization() async {
    if (_clientId.isEmpty) {
      throw Exception(
        'Missing SPOTIFY_CLIENT_ID. Pass --dart-define=SPOTIFY_CLIENT_ID=<id>.',
      );
    }
    final verifier = _spotifyClient.createCodeVerifier();
    final challenge = _spotifyClient.codeChallenge(verifier);
    final state = DateTime.now().millisecondsSinceEpoch.toString();
    _pendingVerifier = verifier;
    _pendingState = state;

    return _spotifyClient.buildAuthorizeUri(
      clientId: _clientId,
      redirectUri: _redirectUri,
      codeChallenge: challenge,
      state: state,
    );
  }

  Future<SpotifyAuthState> completeAuthorization(Uri uri) async {
    final state = uri.queryParameters['state'];
    final code = uri.queryParameters['code'];

    if (state == null || code == null) {
      throw Exception('Spotify callback is missing state/code');
    }
    if (_pendingState == null || _pendingVerifier == null || state != _pendingState) {
      throw Exception('Spotify callback state mismatch');
    }

    final token = await _spotifyClient.exchangeCode(
      code: code,
      clientId: _clientId,
      redirectUri: _redirectUri,
      codeVerifier: _pendingVerifier!,
    );

    final expiresAt = DateTime.now().toUtc().add(Duration(seconds: token.expiresInSec));
    await _tokenStore.save(
      accessToken: token.accessToken,
      refreshToken: token.refreshToken,
      expiresAtEpochSec: expiresAt.millisecondsSinceEpoch ~/ 1000,
    );

    await _platformServiceRepository.syncSpotifyTokens(
      accessToken: token.accessToken,
      refreshToken: token.refreshToken,
      expiresAtEpochSec: expiresAt.millisecondsSinceEpoch ~/ 1000,
      clientId: _clientId,
    );

    _pendingState = null;
    _pendingVerifier = null;

    return SpotifyAuthState(
      accessToken: token.accessToken,
      refreshToken: token.refreshToken,
      expiresAt: expiresAt,
      connected: true,
    );
  }

  @override
  Future<SpotifyAuthState> connectSpotify() async {
    final authorizeUri = await beginSpotifyAuthorization();
    await _spotifyClient.launchAuthPage(authorizeUri);
    return getAuthState();
  }

  @override
  Future<void> disconnectSpotify() async {
    await _tokenStore.clear();
  }

  @override
  Future<void> likeCurrentTrack() async {
    await refreshIfNeeded();
    final state = await _readStoredAuthState();
    final accessToken = state.accessToken;
    if (accessToken == null) {
      throw Exception('Service is disconnected');
    }

    final trackId = await _spotifyClient.currentTrackId(accessToken);
    if (trackId == null || trackId.isEmpty) {
      throw Exception('No track is currently playing');
    }

    await _spotifyClient.likeTrack(trackId: trackId, accessToken: accessToken);
  }

  @override
  Future<void> refreshIfNeeded() async {
    final state = await _readStoredAuthState();
    if (!_shouldRefresh(state)) {
      return;
    }
    await _refreshAuthState(state);
  }

  Future<bool> tryHandleIncomingUri(Uri uri) async {
    if (!uri.toString().startsWith(_redirectUri)) {
      return false;
    }
    try {
      await completeAuthorization(uri);
      return true;
    } catch (error, stackTrace) {
      debugPrint('Spotify callback failed: $error\n$stackTrace');
      rethrow;
    }
  }
}
