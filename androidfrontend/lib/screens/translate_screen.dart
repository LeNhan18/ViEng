import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/network/api_service.dart';
import '../models/translate_models.dart';

const _directions = [
  ('en_to_vi', 'English', 'Tiếng Việt'),
  ('vi_to_en', 'Tiếng Việt', 'English'),
];

const _levels = [
  ('beginner', 'Beginner'),
  ('intermediate', 'Intermediate'),
  ('advanced', 'Advanced'),
];

class TranslateScreen extends StatefulWidget {
  const TranslateScreen({super.key});

  @override
  State<TranslateScreen> createState() => _TranslateScreenState();
}

class _TranslateScreenState extends State<TranslateScreen> {
  final _inputController = TextEditingController();
  String _direction = 'en_to_vi';
  String _level = 'intermediate';
  bool _useRag = true;
  bool _loading = false;
  String? _error;
  TranslateResponse? _result;
  bool _copied = false;

  String get _dirFrom {
    final d = _directions.where((e) => e.$1 == _direction).firstOrNull;
    return d?.$2 ?? 'English';
  }

  String get _dirTo {
    final d = _directions.where((e) => e.$1 == _direction).firstOrNull;
    return d?.$3 ?? 'Tiếng Việt';
  }

  @override
  void dispose() {
    _inputController.dispose();
    super.dispose();
  }

  void _swap() {
    setState(() {
      _direction = _direction == 'en_to_vi' ? 'vi_to_en' : 'en_to_vi';
      if (_result != null) {
        _inputController.text = _result!.translated;
        _result = null;
      }
    });
  }

  Future<void> _translate() async {
    final text = _inputController.text.trim();
    if (text.isEmpty) return;
    setState(() {
      _loading = true;
      _error = null;
      _result = null;
    });
    try {
      final data = await ApiService.translateText(
        text: text,
        direction: _direction,
        level: _level,
        useRag: _useRag,
      );
      if (mounted) setState(() {
        _result = data;
        _loading = false;
      });
    } on DioException catch (e) {
      final detail = e.response?.data is Map ? (e.response!.data as Map)['detail'] : null;
      final msg = detail?.toString() ?? e.message ?? 'Không thể dịch. Vui lòng thử lại.';
      if (mounted) setState(() {
        _error = msg;
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() {
        _error = 'Không thể dịch. Vui lòng thử lại.';
        _loading = false;
      });
    }
  }

  void _copy() {
    if (_result?.translated == null) return;
    Clipboard.setData(ClipboardData(text: _result!.translated));
    setState(() => _copied = true);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 8),
          const Text(
            'Dịch thuật AI',
            style: TextStyle(
              fontSize: 26,
              fontWeight: FontWeight.bold,
              color: Color(0xFF0F172A),
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'Dịch Anh-Việt thông minh, kèm giải thích từ vựng và ngữ pháp',
            style: TextStyle(color: Color(0xFF64748B), fontSize: 14),
          ),
          const SizedBox(height: 20),
          Container(
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFFE2E8F0)),
            ),
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        _dirFrom,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF334155),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Material(
                        color: const Color(0xFFEEF2FF),
                        borderRadius: BorderRadius.circular(20),
                        child: InkWell(
                          onTap: _swap,
                          borderRadius: BorderRadius.circular(20),
                          child: const Padding(
                            padding: EdgeInsets.all(10),
                            child: Icon(Icons.swap_horiz, color: Color(0xFF4F46E5), size: 22),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Text(
                        _dirTo,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF334155),
                        ),
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                IntrinsicHeight(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: TextField(
                            controller: _inputController,
                            maxLines: 6,
                            maxLength: 5000,
                          decoration: InputDecoration(
                            hintText: _direction == 'en_to_vi'
                                ? 'Enter English text...'
                                : 'Nhập văn bản tiếng Việt...',
                            border: InputBorder.none,
                            hintStyle: const TextStyle(color: Color(0xFF94A3B8)),
                            counterStyle: const TextStyle(fontSize: 12, color: Color(0xFF94A3B8)),
                          ),
                          style: const TextStyle(fontSize: 14, color: Color(0xFF1E293B)),
                        ),
                      ),
                    ),
                    Container(
                      width: 1,
                      color: const Color(0xFFF1F5F9),
                    ),
                    Expanded(
                      child: Container(
                        color: const Color(0xFFFAFAFA),
                        padding: const EdgeInsets.all(16),
                        child: _loading
                            ? const Center(
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    SizedBox(
                                      width: 24,
                                      height: 24,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Color(0xFF4F46E5),
                                      ),
                                    ),
                                    SizedBox(height: 8),
                                    Text(
                                      'Đang dịch...',
                                      style: TextStyle(fontSize: 13, color: Color(0xFF64748B)),
                                    ),
                                  ],
                                ),
                              )
                            : _result != null
                                ? Stack(
                                    alignment: Alignment.topRight,
                                    children: [
                                      Padding(
                                        padding: const EdgeInsets.only(top: 8),
                                        child: Text(
                                          _result!.translated,
                                          style: const TextStyle(
                                            fontSize: 14,
                                            height: 1.5,
                                            color: Color(0xFF1E293B),
                                          ),
                                        ),
                                      ),
                                      TextButton.icon(
                                        onPressed: _copy,
                                        icon: Icon(
                                          _copied ? Icons.check : Icons.copy,
                                          size: 16,
                                          color: _copied ? const Color(0xFF16A34A) : const Color(0xFF64748B),
                                        ),
                                        label: Text(
                                          _copied ? 'Đã copy' : 'Copy',
                                          style: const TextStyle(fontSize: 12),
                                        ),
                                      ),
                                    ],
                                  )
                                : const Center(
                                    child: Text(
                                      'Bản dịch sẽ hiện ở đây',
                                      style: TextStyle(fontSize: 14, color: Color(0xFF94A3B8)),
                                    ),
                                  ),
                      ),
                    ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          const Text(
                            'Trình độ: ',
                            style: TextStyle(fontSize: 12, color: Color(0xFF64748B)),
                          ),
                          ..._levels.map((e) {
                            final selected = _level == e.$1;
                            return GestureDetector(
                              onTap: () => setState(() => _level = e.$1),
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                decoration: BoxDecoration(
                                  color: selected
                                      ? const Color(0xFFEEF2FF)
                                      : Colors.transparent,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text(
                                  e.$2,
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w500,
                                    color: selected ? const Color(0xFF4F46E5) : const Color(0xFF94A3B8),
                                  ),
                                ),
                              ),
                            );
                          }),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          SizedBox(
                            height: 20,
                            width: 20,
                            child: Checkbox(
                              value: _useRag,
                              onChanged: (v) => setState(() => _useRag = v ?? true),
                              activeColor: const Color(0xFF4F46E5),
                            ),
                          ),
                          const SizedBox(width: 6),
                          const Expanded(
                            child: Text(
                              'Dùng Knowledge Base',
                              style: TextStyle(fontSize: 12, color: Color(0xFF64748B)),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          FilledButton.icon(
                            onPressed: _loading || _inputController.text.trim().isEmpty ? null : _translate,
                            icon: _loading
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: Colors.white,
                                    ),
                                  )
                                : const Icon(Icons.swap_horiz, size: 16),
                            label: const Text('Dịch'),
                            style: FilledButton.styleFrom(
                              backgroundColor: const Color(0xFF4F46E5),
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFFFEF2F2),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                _error!,
                style: const TextStyle(color: Color(0xFFDC2626), fontSize: 13),
              ),
            ),
          ],
          if (_result != null &&
              ((_result!.vocabulary?.isNotEmpty ?? false) ||
                  (_result!.grammarNotes?.isNotEmpty ?? false))) ...[
            const SizedBox(height: 20),
            LayoutBuilder(
              builder: (context, constraints) {
                final vocab = _result!.vocabulary?.isNotEmpty ?? false;
                final grammar = _result!.grammarNotes?.isNotEmpty ?? false;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (vocab) _buildVocabularySection(),
                    if (vocab && grammar) const SizedBox(height: 16),
                    if (grammar) _buildGrammarSection(),
                  ],
                );
              },
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildVocabularySection() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.menu_book, size: 18, color: Color(0xFF4F46E5)),
              SizedBox(width: 8),
              Text(
                'Từ vựng quan trọng',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF0F172A),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...(_result!.vocabulary ?? []).map((v) => Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFC),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Text(
                          v.word,
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            color: Color(0xFF4F46E5),
                            fontSize: 14,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            '— ${v.meaning}',
                            style: const TextStyle(
                              fontSize: 13,
                              color: Color(0xFF475569),
                            ),
                          ),
                        ),
                      ],
                    ),
                    if (v.example != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          v.example!,
                          style: const TextStyle(
                            fontSize: 12,
                            fontStyle: FontStyle.italic,
                            color: Color(0xFF64748B),
                          ),
                        ),
                      ),
                  ],
                ),
              )),
        ],
      ),
    );
  }

  Widget _buildGrammarSection() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.lightbulb_outline, size: 18, color: Color(0xFFF59E0B)),
              SizedBox(width: 8),
              Text(
                'Ghi chú ngữ pháp',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF0F172A),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...(_result!.grammarNotes ?? []).asMap().entries.map((e) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 20,
                      height: 20,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: const Color(0xFFFEF3C7),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        '${e.key + 1}',
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFFB45309),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        e.value,
                        style: const TextStyle(
                          fontSize: 13,
                          color: Color(0xFF334155),
                          height: 1.4,
                        ),
                      ),
                    ),
                  ],
                ),
              )),
        ],
      ),
    );
  }
}
