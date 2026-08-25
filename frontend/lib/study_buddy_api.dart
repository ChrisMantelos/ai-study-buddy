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

  Future<List<QuizQuestion>> generateQuiz({
    required String notes,
    int numQuestions = 5,
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
            }),
          )
          .timeout(const Duration(seconds: 30));
    } catch (_) {
      throw QuizApiException('Could not reach the server. Check your connection.');
    }

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

    return questions;
  }

  Map<String, dynamic>? _tryDecode(String body) {
    try {
      return jsonDecode(body) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }
}
