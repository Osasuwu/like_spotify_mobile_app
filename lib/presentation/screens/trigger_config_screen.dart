import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/app_constants.dart';
import '../../domain/entities/rule_config.dart';
import '../../domain/entities/trigger_config.dart';
import '../state/app_providers.dart';

class TriggerConfigScreen extends ConsumerStatefulWidget {
  const TriggerConfigScreen({super.key});

  @override
  ConsumerState<TriggerConfigScreen> createState() => _TriggerConfigScreenState();
}

class _TriggerConfigScreenState extends ConsumerState<TriggerConfigScreen> {
  late TextEditingController _pattern;
  late TextEditingController _window;
  late TextEditingController _debounce;
  late TextEditingController _archivePlaylistName;
  late TextEditingController _bestOfPlaylistName;
  late TextEditingController _bestOfThreshold;
  late TextEditingController _followArtistThreshold;
  late TextEditingController _likeCooldownMinutes;

  late bool _archiveRemoveEnabled;
  late bool _bestOfEnabled;
  late bool _followArtistEnabled;
  late bool _likeCooldownEnabled;
  late int _feedbackVolume;

  @override
  void initState() {
    super.initState();
    final state = ref.read(appControllerProvider);
    final config = state.triggerConfig;
    final ruleConfig = state.ruleConfig;
    _pattern = TextEditingController(text: config.pattern);
    _window = TextEditingController(text: config.windowMs.toString());
    _debounce = TextEditingController(text: config.debounceMs.toString());
    _feedbackVolume = config.feedbackVolume;
    _archivePlaylistName = TextEditingController(text: ruleConfig.archivePlaylistName);
    _bestOfPlaylistName = TextEditingController(text: ruleConfig.bestOfPlaylistName);
    _bestOfThreshold = TextEditingController(text: ruleConfig.bestOfThreshold.toString());
    _followArtistThreshold =
        TextEditingController(text: ruleConfig.followArtistThreshold.toString());
    _likeCooldownMinutes = TextEditingController(text: ruleConfig.likeCooldownMinutes.toString());
    _archiveRemoveEnabled = ruleConfig.archiveRemoveEnabled;
    _bestOfEnabled = ruleConfig.bestOfEnabled;
    _followArtistEnabled = ruleConfig.followArtistEnabled;
    _likeCooldownEnabled = ruleConfig.likeCooldownEnabled;
  }

  @override
  void dispose() {
    _pattern.dispose();
    _window.dispose();
    _debounce.dispose();
    _archivePlaylistName.dispose();
    _bestOfPlaylistName.dispose();
    _bestOfThreshold.dispose();
    _followArtistThreshold.dispose();
    _likeCooldownMinutes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = ref.read(appControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: const Text('Trigger configuration')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: <Widget>[
            const Text(
              'Pattern format: comma separated events using play/pause.\nDefault: pause,play in 1000ms.',
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _pattern,
              decoration: const InputDecoration(labelText: 'Pattern'),
            ),
            TextField(
              controller: _window,
              decoration: const InputDecoration(labelText: 'Window (ms)'),
              keyboardType: TextInputType.number,
            ),
            TextField(
              controller: _debounce,
              decoration: const InputDecoration(labelText: 'Debounce (ms)'),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 12),
            Text('Feedback sound volume: $_feedbackVolume%'),
            Slider(
              value: _feedbackVolume.toDouble(),
              min: 0,
              max: 100,
              divisions: 20,
              label: '$_feedbackVolume%',
              onChanged: (value) => setState(() => _feedbackVolume = value.round()),
            ),
            const SizedBox(height: 20),
            const Divider(),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Remove from archive playlist'),
              value: _archiveRemoveEnabled,
              onChanged: (value) => setState(() => _archiveRemoveEnabled = value),
            ),
            TextField(
              controller: _archivePlaylistName,
              enabled: _archiveRemoveEnabled,
              decoration: const InputDecoration(
                labelText: 'Archive playlist name',
                hintText: 'Discover Weekly Archive',
              ),
            ),
            const SizedBox(height: 12),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Promote to best-of playlist'),
              value: _bestOfEnabled,
              onChanged: (value) => setState(() => _bestOfEnabled = value),
            ),
            TextField(
              controller: _bestOfPlaylistName,
              enabled: _bestOfEnabled,
              decoration: const InputDecoration(
                labelText: 'Best-of playlist name',
                hintText: 'Botbotb(Best of the best of the best)',
              ),
            ),
            TextField(
              controller: _bestOfThreshold,
              enabled: _bestOfEnabled,
              decoration: const InputDecoration(labelText: 'Best-of threshold (likes)'),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 12),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Auto-follow artist'),
              value: _followArtistEnabled,
              onChanged: (value) => setState(() => _followArtistEnabled = value),
            ),
            TextField(
              controller: _followArtistThreshold,
              enabled: _followArtistEnabled,
              decoration: const InputDecoration(labelText: 'Follow-artist threshold (likes)'),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 12),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Like cooldown'),
              subtitle: const Text('Ignore accidental repeat-likes of the same track'),
              value: _likeCooldownEnabled,
              onChanged: (value) => setState(() => _likeCooldownEnabled = value),
            ),
            TextField(
              controller: _likeCooldownMinutes,
              enabled: _likeCooldownEnabled,
              decoration: const InputDecoration(labelText: 'Cooldown (minutes)'),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: () async {
                final config = TriggerConfig(
                  pattern: _pattern.text.trim(),
                  windowMs: int.tryParse(_window.text.trim()) ?? 1000,
                  debounceMs: int.tryParse(_debounce.text.trim()) ?? 650,
                  feedbackVolume: _feedbackVolume,
                );
                final ruleConfig = RuleConfig(
                  archiveRemoveEnabled: _archiveRemoveEnabled,
                  archivePlaylistName: _archivePlaylistName.text.trim(),
                  bestOfEnabled: _bestOfEnabled,
                  bestOfPlaylistName: _bestOfPlaylistName.text.trim(),
                  bestOfThreshold: int.tryParse(_bestOfThreshold.text.trim()) ?? 3,
                  followArtistEnabled: _followArtistEnabled,
                  followArtistThreshold:
                      int.tryParse(_followArtistThreshold.text.trim()) ?? 5,
                  likeCooldownEnabled: _likeCooldownEnabled,
                  likeCooldownMinutes:
                      int.tryParse(_likeCooldownMinutes.text.trim()) ??
                          AppConstants.defaultLikeCooldownMinutes,
                );
                await controller.saveTriggerConfig(config);
                await controller.saveRuleConfig(ruleConfig);
                if (!context.mounted) return;
                final error = ref.read(appControllerProvider).lastError;
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(error ?? 'Trigger configuration saved'),
                  ),
                );
              },
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }
}
