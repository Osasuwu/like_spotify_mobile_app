import 'dart:convert';

enum LogResult {
  success,
  failure,
  info;

  static LogResult fromName(String? name) {
    return LogResult.values.firstWhere(
      (value) => value.name == name,
      orElse: () => LogResult.info,
    );
  }
}

class AppLog {
  final DateTime at;
  final String actionType;
  final String? targetId;
  final LogResult result;
  final int? httpCode;
  final String message;

  const AppLog({
    required this.at,
    this.actionType = 'legacy',
    this.targetId,
    this.result = LogResult.info,
    this.httpCode,
    required this.message,
  });

  Map<String, dynamic> toJson() {
    return {
      'at': at.toIso8601String(),
      'actionType': actionType,
      if (targetId != null) 'targetId': targetId,
      'result': result.name,
      if (httpCode != null) 'httpCode': httpCode,
      'message': message,
    };
  }

  factory AppLog.fromJson(Map<String, dynamic> json) {
    return AppLog(
      at: DateTime.parse(json['at'] as String),
      actionType: json['actionType'] as String? ?? 'legacy',
      targetId: json['targetId'] as String?,
      result: LogResult.fromName(json['result'] as String?),
      httpCode: json['httpCode'] as int?,
      message: json['message'] as String? ?? '',
    );
  }

  String toLine() => jsonEncode(toJson());

  factory AppLog.fromLine(String line) {
    try {
      final decoded = jsonDecode(line);
      if (decoded is Map<String, dynamic>) {
        return AppLog.fromJson(decoded);
      }
    } catch (_) {
      // Not JSON — fall through to legacy plain-text handling below.
    }
    return AppLog(at: DateTime.now().toUtc(), actionType: 'legacy', message: line);
  }
}
