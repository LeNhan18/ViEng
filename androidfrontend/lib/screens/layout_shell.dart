import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class LayoutShell extends StatelessWidget {
  const LayoutShell({
    super.key,
    required this.currentLocation,
    required this.child,
  });

  final String currentLocation;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final isResultOrQuiz = currentLocation.startsWith('/result') ||
        currentLocation.startsWith('/exam/quiz');
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: isResultOrQuiz
          ? null
          : AppBar(
              backgroundColor: Colors.white.withValues(alpha: 0.9),
              elevation: 0,
              title: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  RichText(
                    overflow: TextOverflow.ellipsis,
                    text: const TextSpan(
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF0F172A),
                      ),
                      children: [
                        TextSpan(text: 'Vi'),
                        TextSpan(
                          text: 'Eng',
                          style: TextStyle(color: Color(0xFF4F46E5)),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              actions: [
                _NavChip(
                  label: 'Trang chủ',
                  path: '/',
                  isSelected: currentLocation == '/',
                  onTap: () => context.go('/'),
                ),
                _NavChip(
                  label: 'Làm bài',
                  path: '/exam',
                  isSelected: currentLocation == '/exam',
                  onTap: () => context.go('/exam'),
                ),
                _NavChip(
                  label: 'Dịch',
                  path: '/translate',
                  isSelected: currentLocation == '/translate',
                  onTap: () => context.go('/translate'),
                ),
              ],
            ),
      body: child,
      bottomNavigationBar: isResultOrQuiz
          ? null
          : Container(
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.8),
                border: Border(top: BorderSide(color: Colors.grey.shade200)),
              ),
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: SafeArea(
                child: Text(
                  'ViEng — Trợ lý luyện thi tiếng Anh AI cho sinh viên Việt Nam',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey.shade600,
                  ),
                ),
              ),
            ),
    );
  }
}

class _NavChip extends StatelessWidget {
  const _NavChip({
    required this.label,
    required this.path,
    required this.isSelected,
    required this.onTap,
  });

  final String label;
  final String path;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: Material(
        color: isSelected
            ? const Color(0xFF4F46E5)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            child: Text(
              label,
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: isSelected ? Colors.white : const Color(0xFF475569),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
