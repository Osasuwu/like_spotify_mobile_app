import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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

  @override
  void initState() {
    super.initState();
    final config = ref.read(appControllerProvider).triggerConfig;
    final state = ref.read(appControllerProvider);
    _pattern = TextEditingController(text: config.pattern);
    _window = TextEditingController(text: config.windowMs.toString());
    _debounce = TextEditingController(text: config.debounceMs.toString());
    _archivePlaylistName = TextEditingController(text: state.archivePlaylistName);
    _bestOfPlaylistName = TextEditingController(text: state.bestOfPlaylistName);
  }

  @override
  void dispose() {
    _pattern.dispose();
    _window.dispose();
    _debounce.dispose();
    _archivePlaylistName.dispose();
    _bestOfPlaylistName.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = ref.read(appControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: const Text('Trigger configuration')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
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
            TextField(
              controller: _archivePlaylistName,
              decoration: const InputDecoration(
                labelText: 'Archive playlist name',
                hintText: 'Discover Weekly Archive',
              ),
            ),
            TextField(
              controller: _bestOfPlaylistName,
              decoration: const InputDecoration(
                labelText: 'Best-of playlist name',
                hintText: 'Botbotb(Best of the best of the best)',
              ),
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: () async {
                final config = TriggerConfig(
                  pattern: _pattern.text.trim(),
                  windowMs: int.tryParse(_window.text.trim()) ?? 1000,
                  debounceMs: int.tryParse(_debounce.text.trim()) ?? 650,
                );
                await controller.saveTriggerConfig(config);
                await controller.savePlaylistRules(
                  archivePlaylistName: _archivePlaylistName.text.trim(),
                  bestOfPlaylistName: _bestOfPlaylistName.text.trim(),
                );
                if (!context.mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Trigger configuration saved')),
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
