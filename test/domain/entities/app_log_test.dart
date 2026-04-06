import 'package:flutter_test/flutter_test.dart';
import 'package:like_spotify_mobile_app/domain/entities/app_log.dart';

void main() {
  group('AppLog', () {
    group('constructor', () {
      test('stores at field correctly', () {
        final now = DateTime.now();
        final log = AppLog(at: now, message: 'Test message');

        expect(log.at, equals(now));
      });

      test('stores message field correctly', () {
        final log = AppLog(
          at: DateTime.now(),
          message: 'This is a test message',
        );

        expect(log.message, equals('This is a test message'));
      });

      test('creates instance with both fields', () {
        final now = DateTime.now();
        final message = 'Application started';
        final log = AppLog(at: now, message: message);

        expect(log.at, equals(now));
        expect(log.message, equals(message));
      });

      test('handles empty message string', () {
        final log = AppLog(at: DateTime.now(), message: '');

        expect(log.message, equals(''));
      });

      test('handles multiline message', () {
        final message = 'Line 1\nLine 2\nLine 3';
        final log = AppLog(at: DateTime.now(), message: message);

        expect(log.message, equals(message));
      });

      test('preserves different timestamps', () {
        final time1 = DateTime(2026, 4, 6, 10, 0, 0);
        final time2 = DateTime(2026, 4, 6, 10, 0, 1);

        final log1 = AppLog(at: time1, message: 'First log');
        final log2 = AppLog(at: time2, message: 'Second log');

        expect(log1.at, equals(time1));
        expect(log2.at, equals(time2));
        expect(log1.at, isNot(equals(log2.at)));
      });
    });

    group('field access', () {
      test('can access at field multiple times', () {
        final now = DateTime.now();
        final log = AppLog(at: now, message: 'Test');

        expect(log.at, equals(now));
        expect(log.at, equals(now));
      });

      test('can access message field multiple times', () {
        const message = 'Test message';
        final log = AppLog(at: DateTime.now(), message: message);

        expect(log.message, equals(message));
        expect(log.message, equals(message));
      });
    });
  });
}
