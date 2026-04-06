import 'package:mocktail/mocktail.dart';
import 'package:like_spotify_mobile_app/domain/repositories/settings_repository.dart';
import 'package:like_spotify_mobile_app/domain/repositories/music_service_repository.dart';
import 'package:like_spotify_mobile_app/domain/repositories/platform_service_repository.dart';
import 'package:http/http.dart' as http;

class MockSettingsRepository extends Mock implements SettingsRepository {}

class MockMusicServiceRepository extends Mock
    implements MusicServiceRepository {}

class MockPlatformServiceRepository extends Mock
    implements PlatformServiceRepository {}

class MockHttpClient extends Mock implements http.Client {}
