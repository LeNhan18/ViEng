import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'screens/layout_shell.dart';
import 'screens/home_screen.dart';
import 'screens/exam_setup_screen.dart';
import 'screens/exam_quiz_screen.dart';
import 'screens/result_screen.dart';
import 'screens/translate_screen.dart';

final _rootKey = GlobalKey<NavigatorState>();

GoRouter createAppRouter() {
  return GoRouter(
    navigatorKey: _rootKey,
    initialLocation: '/',
    routes: [
      ShellRoute(
        builder: (context, state, child) => LayoutShell(
          currentLocation: state.uri.path,
          child: child,
        ),
        routes: [
          GoRoute(
            path: '/',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: HomeScreen(),
            ),
          ),
          GoRoute(
            path: '/exam',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: ExamSetupScreen(),
            ),
          ),
          GoRoute(
            path: '/translate',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: TranslateScreen(),
            ),
          ),
        ],
      ),
      GoRoute(
        path: '/result',
        parentNavigatorKey: _rootKey,
        pageBuilder: (context, state) {
          final extra = state.extra as Map<String, dynamic>?;
          return MaterialPage<void>(
            child: ResultScreen(resultState: extra),
          );
        },
      ),
      GoRoute(
        path: '/exam/quiz',
        parentNavigatorKey: _rootKey,
        pageBuilder: (context, state) {
          final extra = state.extra as Map<String, dynamic>?;
          return MaterialPage<void>(
            child: ExamQuizScreen(quizPayload: extra),
          );
        },
      ),
    ],
  );
}
