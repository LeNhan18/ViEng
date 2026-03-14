import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../models/exam_models.dart';

class ExamQuizScreen extends StatefulWidget {
  const ExamQuizScreen({super.key, this.quizPayload});

  final Map<String, dynamic>? quizPayload;

  @override
  State<ExamQuizScreen> createState() => _ExamQuizScreenState();
}

class _ExamQuizScreenState extends State<ExamQuizScreen> {
  late Map<String, dynamic> config;
  late GenerateTestResponse testData;
  final Map<String, String> _answers = {};
  int _current = 0;

  @override
  void initState() {
    super.initState();
    config = widget.quizPayload?['config'] as Map<String, dynamic>? ?? {};
    testData = widget.quizPayload?['testData'] as GenerateTestResponse? ?? GenerateTestResponse(questions: []);
  }

  List<QuestionItem> get questions => testData.questions;
  String get partLabel {
    final p = testData.part ?? '';
    if (p == 'part5') return 'Part 5 - Incomplete Sentences';
    if (p == 'part6') return 'Part 6 - Text Completion';
    if (p == 'part7_single') return 'Part 7 - Single Passage';
    if (p == 'part7_multiple') return 'Part 7 - Multiple Passages';
    return '${(config['examType'] ?? 'TOEIC').toString().toUpperCase()} Reading';
  }

  ({String? passage, List<String>? passages}) _passageFor(QuestionItem q) {
    final section = testData.readingSection;
    if (section == null) return (passage: null, passages: null);

    if (testData.part == 'part6' && section.part6 != null) {
      for (final block in section.part6!) {
        if (block.questions.any((pq) => pq.id == q.id)) {
          return (passage: block.passage, passages: null);
        }
      }
    }

    final part7List = testData.part == 'part7_single' ? section.part7Single : section.part7Multiple;
    if (part7List != null) {
      for (final block in part7List) {
        if (block.questions.any((pq) => pq.id == q.id)) {
          return (passage: null, passages: block.passages);
        }
      }
    }
    return (passage: null, passages: null);
  }

  void _submit() {
    final score = questions.fold<int>(0, (acc, q) {
      final selected = _answers[q.id];
      final correct = q.correctAnswer;
      final ok = selected != null && (selected == correct || selected.startsWith(correct));
      return acc + (ok ? 1 : 0);
    });
    final resultState = {
      'config': config,
      'questions': questions,
      'answers': Map<String, String>.from(_answers),
      'readingSection': testData.readingSection,
      'score': score,
    };
    context.go('/result', extra: resultState);
  }

  @override
  Widget build(BuildContext context) {
    if (questions.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: const Text('Bài thi')),
        body: const Center(child: Text('Không có câu hỏi')),
      );
    }

    final q = questions[_current];
    final passageInfo = _passageFor(q);
    final totalAnswered = _answers.length;

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('Làm bài'),
        backgroundColor: Colors.white,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      partLabel,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF0F172A),
                      ),
                    ),
                    Text(
                      'Trình độ: ${config['level'] ?? ''}',
                      style: const TextStyle(fontSize: 13, color: Color(0xFF64748B)),
                    ),
                  ],
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: const Color(0xFFEEF2FF),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    '$totalAnswered/${questions.length} đã trả lời',
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: Color(0xFF4F46E5),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: List.generate(questions.length, (i) {
                final answered = _answers[questions[i].id] != null;
                final selected = i == _current;
                return GestureDetector(
                  onTap: () => setState(() => _current = i),
                  child: Container(
                    width: 36,
                    height: 36,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: selected
                          ? const Color(0xFF4F46E5)
                          : answered
                              ? const Color(0xFFDCFCE7)
                              : const Color(0xFFF1F5F9),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      '${i + 1}',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: selected
                            ? Colors.white
                            : answered
                                ? const Color(0xFF16A34A)
                                : const Color(0xFF64748B),
                      ),
                    ),
                  ),
                );
              }),
            ),
            if (passageInfo.passage != null || (passageInfo.passages?.isNotEmpty ?? false)) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (passageInfo.passage != null) ...[
                      const Text(
                        'ĐOẠN VĂN',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF94A3B8),
                          letterSpacing: 1,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        passageInfo.passage!,
                        style: const TextStyle(
                          fontSize: 14,
                          height: 1.5,
                          color: Color(0xFF334155),
                        ),
                      ),
                    ],
                    if (passageInfo.passages != null)
                      ...passageInfo.passages!.asMap().entries.map((e) {
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Đoạn ${e.key + 1}',
                                style: const TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                  color: Color(0xFF94A3B8),
                                ),
                              ),
                              const SizedBox(height: 4),
                              Container(
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: Text(
                                  e.value,
                                  style: const TextStyle(
                                    fontSize: 14,
                                    height: 1.5,
                                    color: Color(0xFF334155),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        );
                      }),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Câu ${_current + 1}/${questions.length}',
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: Color(0xFF4F46E5),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    q.content,
                    style: const TextStyle(
                      fontSize: 16,
                      height: 1.5,
                      color: Color(0xFF1E293B),
                    ),
                  ),
                  if (q.options != null) ...[
                    const SizedBox(height: 16),
                    ...q.options!.map((opt) {
                      final isSelected = _answers[q.id] == opt;
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Material(
                          color: isSelected
                              ? const Color(0xFFEEF2FF)
                              : Colors.transparent,
                          borderRadius: BorderRadius.circular(12),
                          child: InkWell(
                            onTap: () => setState(() => _answers[q.id] = opt),
                            borderRadius: BorderRadius.circular(12),
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 16,
                                vertical: 14,
                              ),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: isSelected
                                      ? const Color(0xFF4F46E5)
                                      : const Color(0xFFE2E8F0),
                                  width: 2,
                                ),
                              ),
                              child: Row(
                                children: [
                                  if (isSelected)
                                    const Icon(
                                      Icons.check_circle,
                                      color: Color(0xFF4F46E5),
                                      size: 20,
                                    ),
                                  if (isSelected) const SizedBox(width: 12),
                                  Expanded(
                                    child: Text(
                                      opt,
                                      style: TextStyle(
                                        fontSize: 14,
                                        fontWeight:
                                            isSelected ? FontWeight.w600 : FontWeight.normal,
                                        color: const Color(0xFF334155),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      );
                    }),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                TextButton.icon(
                  onPressed: _current > 0
                      ? () => setState(() => _current--)
                      : null,
                  icon: const Icon(Icons.chevron_left, size: 20),
                  label: const Text('Câu trước'),
                ),
                if (_current < questions.length - 1)
                  FilledButton.icon(
                    onPressed: () => setState(() => _current++),
                    icon: const Icon(Icons.chevron_right, size: 20),
                    label: const Text('Câu tiếp'),
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF4F46E5),
                    ),
                  )
                else
                  FilledButton.icon(
                    onPressed: totalAnswered < questions.length ? null : _submit,
                    icon: const Icon(Icons.check_circle, size: 18),
                    label: Text('Nộp bài ($totalAnswered/${questions.length})'),
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF16A34A),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
