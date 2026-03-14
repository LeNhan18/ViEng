import '../network/api_client.dart';
import '../../models/exam_models.dart';
import '../../models/result_models.dart';
import '../../models/translate_models.dart';

class ApiService {
  static Future<GenerateTestResponse> generateTest({
    required String examType,
    required String skill,
    required String level,
    required int numQuestions,
    String? part,
  }) async {
    final body = <String, dynamic>{
      'exam_type': examType,
      'skill': skill,
      'level': level,
      'num_questions': numQuestions,
    };
    if (part != null) body['part'] = part;

    final res = await apiClient.post('/test/generate', data: body);
    return GenerateTestResponse.fromJson(res.data as Map<String, dynamic>);
  }

  static Future<SubmitAnswersResponse> submitAnswers({
    required String examType,
    required String skill,
    required List<Map<String, dynamic>> answers,
  }) async {
    final res = await apiClient.post('/test/submit', data: {
      'exam_type': examType,
      'skill': skill,
      'answers': answers,
    });
    return SubmitAnswersResponse.fromJson(res.data as Map<String, dynamic>);
  }

  static Future<TranslateResponse> translateText({
    required String text,
    required String direction,
    required String level,
    required bool useRag,
  }) async {
    final res = await apiClient.post('/translate', data: {
      'text': text,
      'direction': direction,
      'level': level,
      'use_rag': useRag,
    });
    return TranslateResponse.fromJson(res.data as Map<String, dynamic>);
  }
}
