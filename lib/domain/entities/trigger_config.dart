class TriggerConfig {
  final String pattern;
  final int windowMs;
  final int debounceMs;

  const TriggerConfig({
    required this.pattern,
    required this.windowMs,
    required this.debounceMs,
  });

  List<String> get events =>
      pattern.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();

  TriggerConfig copyWith({String? pattern, int? windowMs, int? debounceMs}) {
    return TriggerConfig(
      pattern: pattern ?? this.pattern,
      windowMs: windowMs ?? this.windowMs,
      debounceMs: debounceMs ?? this.debounceMs,
    );
  }
}
