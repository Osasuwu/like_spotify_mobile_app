import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/app_providers.dart';

class LogsScreen extends ConsumerWidget {
  const LogsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final logs = ref.watch(appControllerProvider.select((s) => s.logs));
    final controller = ref.read(appControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Logs / debug'),
        actions: <Widget>[
          IconButton(
            onPressed: controller.clearLogs,
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
      body: logs.isEmpty
          ? const Center(child: Text('No logs yet'))
          : ListView.separated(
              itemCount: logs.length,
              separatorBuilder: (_, index) => const Divider(height: 1),
              itemBuilder: (context, index) {
                final log = logs[index];
                return ListTile(
                  dense: true,
                  title: Text(log.message),
                );
              },
            ),
    );
  }
}
