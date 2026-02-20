import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/app_providers.dart';

class ConnectedServicesScreen extends ConsumerWidget {
  const ConnectedServicesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(appControllerProvider);
    final controller = ref.read(appControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: const Text('Connected services')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Spotify installed: ${state.spotifyInstalled ? 'Yes' : 'No'}'),
            const SizedBox(height: 8),
            Text('Spotify connected: ${state.authState.connected ? 'Yes' : 'No'}'),
            const SizedBox(height: 20),
            Row(
              children: <Widget>[
                FilledButton(
                  onPressed: controller.connectSpotify,
                  child: const Text('Connect Spotify'),
                ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: controller.disconnectSpotify,
                  child: const Text('Disconnect'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: () => ref
                  .read(appControllerProvider.notifier)
                  .refreshBatteryOptimizationStatus(),
              child: const Text('Refresh status'),
            ),
            const SizedBox(height: 20),
            const Text(
              'OAuth note: provide SPOTIFY_CLIENT_ID at build/run time using --dart-define.',
            ),
          ],
        ),
      ),
    );
  }
}
