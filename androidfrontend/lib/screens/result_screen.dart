import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../core/network/api_service.dart';
import '../models/exam_models.dart';
import '../models/result_models.dart';

class ResultScreen extends StatefulWidget {
  const ResultScreen({super.key, this.resultState});

  final Map<String, dynamic>? resultState;

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  SubmitAnswersResponse? _feedback;
  bool _loadingFeedback = true;

  List<QuestionItem> get _questions {
    final q = widget.resultState?['questions'];
    if (q == null) return [];
    if (q is List<QuestionItem>) return q;
    return (q as List<dynamic>)
        .map((e) => e is Map ? QuestionItem.fromJson(Map<String, dynamic>.from(e)) : null)
        .whereType<QuestionItem>()
        .toList();
  }

  Map<String, String> get _answers {
    final a = widget.resultState?['answers'];
    if (a is Map<String, String>) return a;
    if (a is Map) return a.map((k, v) => MapEntry(k.toString(), v.toString()));
    return {};
  }

  Map<String, dynamic> get _config {
    final c = widget.resultState?['config'];
    if (c is Map<String, dynamic>) return c;
    if (c is Map) return Map<String, dynamic>.from(c);
    return {};
  }

  int get _score {
    final s = widget.resultState?['score'];
    return s is int ? s : 0;
  }

  @override
  void initState() {
    super.initState();
    _loadFeedback();
  }

  Future<void> _loadFeedback() async {
    final questions = _questions;
    final answers = _answers;
    if (questions.isEmpty) {
      setState(() => _loadingFeedback = false);
      return;
    }
    try {
      final answerList = questions.map((q) => {
        'question_id': q.id,
        'user_answer': answers[q.id] ?? '',
        'question_content': q.content,
        'correct_answer': q.correctAnswer,
        'options': q.options ?? [],
      }).toList();
      final data = await ApiService.submitAnswers(
        examType: _config['examType']?.toString() ?? 'toeic',
        skill: _config['skill']?.toString() ?? 'reading',
        answers: answerList,
      );
      if (mounted) setState(() {
        _feedback = data;
        _loadingFeedback = false;
      });
    } catch (_) {
      if (mounted) setState(() {
        _feedback = null;
        _loadingFeedback = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.resultState == null || _questions.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: const Text('Kết quả')),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text('Không có dữ liệu kết quả'),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: () => context.go('/exam'),
                child: const Text('Quay lại làm bài'),
              ),
            ],
          ),
        ),
      );
    }

    final total = _questions.length;
    final percentage = total > 0 ? ((_score / total) * 100).round() : 0;
    List<Color> scoreGradient = [const Color(0xFFEF4444), const Color(0xFFF43F5E)];
    if (percentage >= 80) {
      scoreGradient = [const Color(0xFF22C55E), const Color(0xFF059669)];
    } else if (percentage >= 50) {
      scoreGradient = [const Color(0xFFF59E0B), const Color(0xFFEA580C)];
    }

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('Kết quả'),
        backgroundColor: Colors.white,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(vertical: 32),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: scoreGradient,
                ),
                borderRadius: BorderRadius.circular(24),
                boxShadow: [
                  BoxShadow(
                    color: scoreGradient.first.withValues(alpha: 0.4),
                    blurRadius: 16,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child: Column(
                children: [
                  const Icon(Icons.emoji_events, size: 48, color: Colors.white),
                  const SizedBox(height: 12),
                  Text(
                    '$percentage%',
                    style: const TextStyle(
                      fontSize: 48,
                      fontWeight: FontWeight.w800,
                      color: Colors.white,
                    ),
                  ),
                  Text(
                    '$_score/$total câu đúng',
                    style: TextStyle(
                      fontSize: 18,
                      color: Colors.white.withValues(alpha: 0.95),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${_config['examType']?.toString().toUpperCase() ?? ''} • ${_config['skill'] ?? ''} • ${_config['level'] ?? ''}',
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.white.withValues(alpha: 0.8),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'Chi tiết từng câu',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: Color(0xFF0F172A),
              ),
            ),
            const SizedBox(height: 12),
            ..._questions.asMap().entries.map((entry) {
              final i = entry.key;
              final q = entry.value;
              final userAnswer = _answers[q.id] ?? '(Chưa trả lời)';
              final correct = q.correctAnswer;
              final isCorrect = userAnswer == correct || userAnswer.startsWith(correct);
              final feedbackItem = _feedback?.feedbacks?.where((f) => f.questionId == q.id).firstOrNull;

              return Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: isCorrect ? const Color(0xFF86EFAC) : const Color(0xFFFECACA),
                    width: 2,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          isCorrect ? Icons.check_circle : Icons.cancel,
                          size: 22,
                          color: isCorrect ? const Color(0xFF22C55E) : const Color(0xFFEF4444),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Câu ${i + 1}',
                                style: const TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: Color(0xFF64748B),
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                q.content,
                                style: const TextStyle(
                                  fontSize: 14,
                                  height: 1.4,
                                  color: Color(0xFF1E293B),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                          decoration: BoxDecoration(
                            color: isCorrect
                                ? const Color(0xFFDCFCE7)
                                : const Color(0xFFFEE2E2),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            'Bạn chọn: $userAnswer',
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                              color: isCorrect ? const Color(0xFF16A34A) : const Color(0xFFDC2626),
                            ),
                          ),
                        ),
                        if (!isCorrect)
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: const Color(0xFFDCFCE7),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              'Đáp án: $correct',
                              style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                                color: Color(0xFF16A34A),
                              ),
                            ),
                          ),
                      ],
                    ),
                    if (feedbackItem?.explanation != null) ...[
                      const SizedBox(height: 12),
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: const Color(0xFFEEF2FF),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.menu_book, size: 14, color: Color(0xFF4F46E5)),
                                const SizedBox(width: 6),
                                const Text(
                                  'Giải thích từ thầy cô AI',
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                    color: Color(0xFF4F46E5),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Text(
                              feedbackItem!.explanation!,
                              style: const TextStyle(
                                fontSize: 13,
                                height: 1.5,
                                color: Color(0xFF334155),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                    if (_loadingFeedback && feedbackItem == null)
                      const Padding(
                        padding: EdgeInsets.only(top: 8),
                        child: Row(
                          children: [
                            SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            ),
                            SizedBox(width: 8),
                            Text('Đang lấy giải thích...', style: TextStyle(fontSize: 13, color: Color(0xFF94A3B8))),
                          ],
                        ),
                      ),
                  ],
                ),
              );
            }),
            const SizedBox(height: 24),
            Center(
              child: FilledButton.icon(
                onPressed: () => context.go('/exam'),
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('Làm bài mới'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF4F46E5),
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
