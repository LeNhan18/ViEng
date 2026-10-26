/// Response từ POST /translate
class TranslateResponse {
  final String translated;
  final List<VocabularyItem>? vocabulary;
  final List<String>? grammarNotes;

  TranslateResponse({
    required this.translated,
    this.vocabulary,
    this.grammarNotes,
  });

  factory TranslateResponse.fromJson(Map<String, dynamic> json) {
    return TranslateResponse(
      translated: json['translated'] as String? ?? '',
      vocabulary: (json['vocabulary'] as List<dynamic>?)
          ?.map((e) => VocabularyItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      grammarNotes: (json['grammar_notes'] as List<dynamic>?)?.cast<String>(),
    );
  }
}

class VocabularyItem {
  final String word;
  final String meaning;
  final String? example;

  VocabularyItem({required this.word, required this.meaning, this.example});

  factory VocabularyItem.fromJson(Map<String, dynamic> json) {
    return VocabularyItem(
      word: json['word'] as String? ?? '',
      meaning: json['meaning'] as String? ?? '',
      example: json['example'] as String?,
    );
  }
}
