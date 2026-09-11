import 'dart:convert';
import 'package:http/http.dart' as http;
import 'quiz_question.dart';

class QuizApiException implements Exception {
  final String message;
  QuizApiException(this.message);

  @override
  String toString() => message;
}

class StudyBuddyApi {
  final String baseUrl;

  StudyBuddyApi({required this.baseUrl});

  Future<QuizResult> generateQuiz({
    required String notes,
    int numQuestions = 5,
    String difficulty = 'medium',
  }) async {
    final uri = Uri.parse('$baseUrl/generate-quiz');

    late final http.Response response;
    try {
      response = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'notes': notes,
              'num_questions': numQuestions,
              'difficulty': difficulty,
            }),
          )
          .timeout(const Duration(seconds: 30));
    } catch (_) {
      throw QuizApiException('Could not reach the server. Check your connection.');
    }

    return _parseQuizResponse(response);
  }

  Future<void> submitScore({
    required int quizId,
    required int score,
    required int total,
  }) async {
    final uri = Uri.parse('$baseUrl/quiz-history/$quizId/score');

    try {
      await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'score': score, 'total': total}),
          )
          .timeout(const Duration(seconds: 15));
    } catch (_) {
      // Score submission is best-effort - if it fails, the quiz result
      // is still shown to the user locally, so we don't throw here.
    }
  }

  QuizResult _parseQuizResponse(http.Response response) {
    if (response.statusCode != 200) {
      final body = _tryDecode(response.body);
      final detail = body?['detail']?.toString() ?? 'Unknown error.';
      throw QuizApiException(detail);
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final questions = (data['questions'] as List)
        .map((q) => QuizQuestion.fromJson(q as Map<String, dynamic>))
        .toList();

    if (questions.isEmpty) {
      throw QuizApiException('The AI did not return any questions.');
    }

    return QuizResult(quizId: data['quiz_id'] as int, questions: questions);
  }

  Map<String, dynamic>? _tryDecode(String body) {
    try {
      return jsonDecode(body) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }
}
