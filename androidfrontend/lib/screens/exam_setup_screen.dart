import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../core/network/api_service.dart';

const _examTypes = [
  ('toeic', 'TOEIC', 0xFF2563EB),
  ('ielts', 'IELTS', 0xFF16A34A),
];

const _toeicParts = [
  ('part5', 'Part 5', 'Incomplete Sentences', 'Hoàn thành câu - 30 câu chuẩn', 10, 30),
  ('part6', 'Part 6', 'Text Completion', 'Hoàn thành đoạn văn - 4 đoạn x 4 câu', 8, 16),
  ('part7_single', 'Part 7 (Single)', 'Single Passage', 'Đọc hiểu 1 đoạn - 2-4 câu/bài', 6, 29),
  ('part7_multiple', 'Part 7 (Multi)', 'Multiple Passages', 'Đọc hiểu 2-3 đoạn liên quan - 5 câu/bộ', 5, 25),
];

const _levels = [
  ('beginner', 'Beginner', 'Mới bắt đầu'),
  ('intermediate', 'Intermediate', 'Trung cấp'),
  ('advanced', 'Advanced', 'Nâng cao'),
];

class ExamSetupScreen extends StatefulWidget {
  const ExamSetupScreen({super.key});

  @override
  State<ExamSetupScreen> createState() => _ExamSetupScreenState();
}

class _ExamSetupScreenState extends State<ExamSetupScreen> {
  String examType = 'toeic';
  String part = 'part5';
  String level = 'intermediate';
  int numQuestions = 10;
  bool loading = false;
  String? error;

  int get maxN {
    final p = _toeicParts.where((e) => e.$1 == part).firstOrNull;
    return p?.$6 ?? 30;
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 8),
          const Text(
            'Tạo bài thi',
            style: TextStyle(
              fontSize: 26,
              fontWeight: FontWeight.bold,
              color: Color(0xFF0F172A),
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'Chọn dạng bài và trình độ để AI tạo đề TOEIC Reading cho bạn',
            style: TextStyle(color: Color(0xFF64748B), fontSize: 14),
          ),
          const SizedBox(height: 24),
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: const Color(0xFFE2E8F0)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Kỳ thi',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF334155),
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: _examTypes.map((e) {
                    final selected = examType == e.$1;
                    return Expanded(
                      child: Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: Material(
                          color: selected ? Color(e.$3).withValues(alpha: 0.15) : Colors.white,
                          borderRadius: BorderRadius.circular(12),
                          child: InkWell(
                            onTap: () => setState(() => examType = e.$1),
                            borderRadius: BorderRadius.circular(12),
                            child: Container(
                              padding: const EdgeInsets.symmetric(vertical: 14),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: selected ? Color(e.$3) : const Color(0xFFE2E8F0),
                                  width: 2,
                                ),
                              ),
                              child: Center(
                                child: Text(
                                  e.$2,
                                  style: TextStyle(
                                    fontWeight: FontWeight.w600,
                                    color: selected ? Color(e.$3) : const Color(0xFF64748B),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
                if (examType == 'toeic') ...[
                  const SizedBox(height: 20),
                  const Text(
                  'Dạng bài Reading',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF334155),
                  ),
                ),
                  const SizedBox(height: 8),
                  GridView.count(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    crossAxisCount: 2,
                    mainAxisSpacing: 8,
                    crossAxisSpacing: 8,
                    childAspectRatio: 1.05,
                    children: _toeicParts.map((e) {
                      final selected = part == e.$1;
                      return Material(
                        color: selected ? const Color(0xFF2563EB).withValues(alpha: 0.1) : Colors.white,
                        borderRadius: BorderRadius.circular(12),
                        child: InkWell(
                          onTap: () => setState(() {
                            part = e.$1;
                            numQuestions = e.$5;
                          }),
                          borderRadius: BorderRadius.circular(12),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: selected ? const Color(0xFF2563EB) : const Color(0xFFE2E8F0),
                                width: 2,
                              ),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.center,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  e.$2,
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.bold,
                                    color: selected ? const Color(0xFF1D4ED8) : const Color(0xFF334155),
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                Text(
                                  e.$3,
                                  style: TextStyle(
                                    fontSize: 10,
                                    color: selected ? const Color(0xFF2563EB) : const Color(0xFF64748B),
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                Text(
                                  e.$4,
                                  style: const TextStyle(fontSize: 9, color: Color(0xFF94A3B8)),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ],
                const SizedBox(height: 20),
                const Text(
                'Trình độ',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF334155),
                ),
              ),
                const SizedBox(height: 8),
                Row(
                  children: _levels.map((e) {
                    final selected = level == e.$1;
                    return Expanded(
                      child: Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: Material(
                          color: selected ? const Color(0xFF4F46E5).withValues(alpha: 0.1) : Colors.white,
                          borderRadius: BorderRadius.circular(12),
                          child: InkWell(
                            onTap: () => setState(() => level = e.$1),
                            borderRadius: BorderRadius.circular(12),
                            child: Container(
                              padding: const EdgeInsets.symmetric(vertical: 12),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: selected ? const Color(0xFF4F46E5) : const Color(0xFFE2E8F0),
                                  width: 2,
                                ),
                              ),
                              child: Column(
                                children: [
                                  Text(
                                    e.$2,
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600,
                                      color: selected ? const Color(0xFF4F46E5) : const Color(0xFF334155),
                                    ),
                                  ),
                                  Text(
                                    e.$3,
                                    style: const TextStyle(fontSize: 10, color: Color(0xFF94A3B8)),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 20),
                Text(
                  'Số câu hỏi: $numQuestions',
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF334155),
                  ),
                ),
                Slider(
                  value: numQuestions.toDouble(),
                  min: 2,
                  max: maxN.toDouble(),
                  divisions: maxN - 2,
                  activeColor: const Color(0xFF4F46E5),
                  onChanged: (v) => setState(() => numQuestions = v.round()),
                ),
                if (error != null) ...[
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEF2F2),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      error!,
                      style: const TextStyle(color: Color(0xFFDC2626), fontSize: 13),
                    ),
                  ),
                  const SizedBox(height: 12),
                ],
                FilledButton.icon(
                  onPressed: loading ? null : _generate,
                  icon: loading
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : const Icon(Icons.menu_book, size: 20),
                  label: Text(loading ? 'AI đang tạo đề...' : 'Tạo đề thi'),
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF4F46E5),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _generate() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final data = await ApiService.generateTest(
        examType: examType,
        skill: 'reading',
        level: level,
        numQuestions: numQuestions,
        part: examType == 'toeic' ? part : null,
      );
      if (!mounted) return;
      context.push<Map<String, dynamic>>('/exam/quiz', extra: {
        'config': {'examType': examType, 'skill': 'reading', 'level': level, 'part': part},
        'testData': data,
      });
    } on DioException catch (e) {
      final detail = e.response?.data is Map ? (e.response!.data as Map)['detail'] : null;
      final msg = detail?.toString() ?? e.message ?? 'Không thể tạo đề thi. Vui lòng thử lại.';
      if (mounted) setState(() {
        error = msg;
        loading = false;
      });
    } catch (_) {
      if (mounted) setState(() {
        error = 'Không thể tạo đề thi. Vui lòng thử lại.';
        loading = false;
      });
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }
}
