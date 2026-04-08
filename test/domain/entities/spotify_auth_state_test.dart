import 'package:flutter_test/flutter_test.dart';
import 'package:like_spotify_mobile_app/domain/entities/spotify_auth_state.dart';

void main() {
  group('SpotifyAuthState', () {
    group('disconnected factory', () {
      test('creates state with all fields null', () {
        final state = const SpotifyAuthState.disconnected();

        expect(state.accessToken, isNull);
        expect(state.refreshToken, isNull);
        expect(state.expiresAt, isNull);
      });

      test('sets connected to false', () {
        final state = const SpotifyAuthState.disconnected();

        expect(state.connected, equals(false));
      });

      test('isExpired returns false when all fields are null', () {
        final state = const SpotifyAuthState.disconnected();

        expect(state.isExpired, equals(false));
      });
    });

    group('isExpired getter', () {
      test('returns true when expiresAt is in the past', () {
        final expiresAt = DateTime.now().toUtc().subtract(Duration(hours: 1));
        final state = SpotifyAuthState(
          accessToken: 'token',
          refreshToken: 'refresh',
          expiresAt: expiresAt,
          connected: true,
        );

        expect(state.isExpired, equals(true));
      });

      test('returns false when expiresAt is in the future', () {
        final expiresAt = DateTime.now().toUtc().add(Duration(hours: 1));
        final state = SpotifyAuthState(
          accessToken: 'token',
          refreshToken: 'refresh',
          expiresAt: expiresAt,
          connected: true,
        );

        expect(state.isExpired, equals(false));
      });

      test('returns false when expiresAt is null', () {
        final state = SpotifyAuthState(
          accessToken: 'token',
          refreshToken: 'refresh',
          expiresAt: null,
          connected: true,
        );

        expect(state.isExpired, equals(false));
      });

      test('returns false when expiresAt is slightly in the future', () {
        final state = SpotifyAuthState(
          accessToken: 'token',
          refreshToken: 'refresh',
          expiresAt: DateTime.now().toUtc().add(Duration(seconds: 10)),
          connected: true,
        );

        expect(state.isExpired, equals(false));
      });
    });

    group('constructor', () {
      test('creates connected state with tokens', () {
        final expiresAt = DateTime.now().toUtc().add(Duration(hours: 1));
        final state = SpotifyAuthState(
          accessToken: 'access_token_value',
          refreshToken: 'refresh_token_value',
          expiresAt: expiresAt,
          connected: true,
        );

        expect(state.accessToken, equals('access_token_value'));
        expect(state.refreshToken, equals('refresh_token_value'));
        expect(state.expiresAt, equals(expiresAt));
        expect(state.connected, equals(true));
      });

      test('creates state with null tokens', () {
        final state = SpotifyAuthState(
          accessToken: null,
          refreshToken: null,
          expiresAt: null,
          connected: false,
        );

        expect(state.accessToken, isNull);
        expect(state.refreshToken, isNull);
        expect(state.expiresAt, isNull);
        expect(state.connected, equals(false));
      });

      test('creates state with accessToken but null refreshToken', () {
        final state = SpotifyAuthState(
          accessToken: 'access_token',
          refreshToken: null,
          expiresAt: null,
          connected: false,
        );

        expect(state.accessToken, equals('access_token'));
        expect(state.refreshToken, isNull);
      });
    });

    group('connected state scenarios', () {
      test('valid connected state with future expiry', () {
        final expiresAt = DateTime.now().toUtc().add(Duration(hours: 1));
        final state = SpotifyAuthState(
          accessToken: 'valid_token',
          refreshToken: 'valid_refresh',
          expiresAt: expiresAt,
          connected: true,
        );

        expect(state.connected, equals(true));
        expect(state.isExpired, equals(false));
        expect(state.accessToken, isNotNull);
      });

      test('expired connected state', () {
        final expiresAt = DateTime.now().toUtc().subtract(Duration(minutes: 5));
        final state = SpotifyAuthState(
          accessToken: 'expired_token',
          refreshToken: 'refresh_token',
          expiresAt: expiresAt,
          connected: true,
        );

        expect(state.connected, equals(true));
        expect(state.isExpired, equals(true));
      });
    });
  });
}
