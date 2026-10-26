/// Response từ POST /test/submit (feedback)
class SubmitAnswersResponse {
  final List<FeedbackItem>? feedbacks;

  SubmitAnswersResponse({this.feedbacks});

  factory SubmitAnswersResponse.fromJson(Map<String, dynamic> json) {
    return SubmitAnswersResponse(
      feedbacks: (json['feedbacks'] as List<dynamic>?)
          ?.map((e) => FeedbackItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class FeedbackItem {
  final String? questionId;
  final String? explanation;

  FeedbackItem({this.questionId, this.explanation});

  factory FeedbackItem.fromJson(Map<String, dynamic> json) {
    return FeedbackItem(
      questionId: json['question_id'] as String?,
      explanation: json['explanation'] as String?,
    );
  }
}
