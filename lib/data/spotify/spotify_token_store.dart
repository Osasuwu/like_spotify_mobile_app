import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SpotifyTokenStore {
  static const _keyAccess = 'spotify_access';
  static const _keyRefresh = 'spotify_refresh';
  static const _keyExpiryEpoch = 'spotify_expiry_epoch';

  final FlutterSecureStorage _storage;

  SpotifyTokenStore(this._storage);

  Future<void> save({
    required String accessToken,
    required String refreshToken,
    required int expiresAtEpochSec,
  }) async {
    await _storage.write(key: _keyAccess, value: accessToken);
    await _storage.write(key: _keyRefresh, value: refreshToken);
    await _storage.write(key: _keyExpiryEpoch, value: expiresAtEpochSec.toString());
  }

  Future<String?> readAccessToken() => _storage.read(key: _keyAccess);

  Future<String?> readRefreshToken() => _storage.read(key: _keyRefresh);

  Future<int?> readExpiryEpochSec() async {
    final raw = await _storage.read(key: _keyExpiryEpoch);
    return int.tryParse(raw ?? '');
  }

  Future<void> clear() async {
    await _storage.delete(key: _keyAccess);
    await _storage.delete(key: _keyRefresh);
    await _storage.delete(key: _keyExpiryEpoch);
  }
}
