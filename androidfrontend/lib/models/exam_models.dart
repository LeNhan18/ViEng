/// Response từ POST /test/generate
class GenerateTestResponse {
  final List<QuestionItem> questions;
  final String? part;
  final ReadingSection? readingSection;

  GenerateTestResponse({
    required this.questions,
    this.part,
    this.readingSection,
  });

  factory GenerateTestResponse.fromJson(Map<String, dynamic> json) {
    return GenerateTestResponse(
      questions: (json['questions'] as List<dynamic>?)
              ?.map((e) => QuestionItem.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      part: json['part'] as String?,
      readingSection: json['reading_section'] != null
          ? ReadingSection.fromJson(json['reading_section'] as Map<String, dynamic>)
          : null,
    );
  }
}

class QuestionItem {
  final String id;
  final String content;
  final String correctAnswer;
  final List<String>? options;

  QuestionItem({
    required this.id,
    required this.content,
    required this.correctAnswer,
    this.options,
  });

  factory QuestionItem.fromJson(Map<String, dynamic> json) {
    return QuestionItem(
      id: json['id'] as String? ?? '',
      content: json['content'] as String? ?? '',
      correctAnswer: json['correct_answer'] as String? ?? '',
      options: (json['options'] as List<dynamic>?)?.cast<String>(),
    );
  }
}

class ReadingSection {
  final List<Part6Block>? part6;
  final List<Part7Block>? part7Single;
  final List<Part7Block>? part7Multiple;

  ReadingSection({this.part6, this.part7Single, this.part7Multiple});

  factory ReadingSection.fromJson(Map<String, dynamic> json) {
    return ReadingSection(
      part6: (json['part6'] as List<dynamic>?)
          ?.map((e) => Part6Block.fromJson(e as Map<String, dynamic>))
          .toList(),
      part7Single: (json['part7_single'] as List<dynamic>?)
          ?.map((e) => Part7Block.fromJson(e as Map<String, dynamic>))
          .toList(),
      part7Multiple: (json['part7_multiple'] as List<dynamic>?)
          ?.map((e) => Part7Block.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class Part6Block {
  final String passage;
  final List<QuestionItem> questions;

  Part6Block({required this.passage, required this.questions});

  factory Part6Block.fromJson(Map<String, dynamic> json) {
    return Part6Block(
      passage: json['passage'] as String? ?? '',
      questions: (json['questions'] as List<dynamic>?)
              ?.map((e) => QuestionItem.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }
}

class Part7Block {
  final List<String> passages;
  final List<QuestionItem> questions;

  Part7Block({required this.passages, required this.questions});

  factory Part7Block.fromJson(Map<String, dynamic> json) {
    return Part7Block(
      passages: (json['passages'] as List<dynamic>?)?.cast<String>() ?? [],
      questions: (json['questions'] as List<dynamic>?)
              ?.map((e) => QuestionItem.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }
}
