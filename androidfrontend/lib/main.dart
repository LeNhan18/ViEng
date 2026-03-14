import 'package:flutter/material.dart';

import 'app_router.dart';

void main() {
  runApp(const ViEngApp());
}

class ViEngApp extends StatelessWidget {
  const ViEngApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'ViEng - Trợ lý luyện thi tiếng Anh AI',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF4F46E5)),
        useMaterial3: true,
      ),
      routerConfig: createAppRouter(),
    );
  }
}
