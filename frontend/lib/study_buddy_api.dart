import 'dart:async';
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
    String? source,
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
              if (source != null) 'source': source,
            }),
          )
          .timeout(const Duration(seconds: 30));
    } catch (_) {
      throw QuizApiException('Could not reach the server. Check your connection.');
    }

    return _parseQuizResponse(response);
  }

  /// Saves a note in the backend's library so it can be used for weak-spot review.
  Future<void> addNote({required String title, required String text}) async {
    final uri = Uri.parse('$baseUrl/notes');

    late final http.Response response;
    try {
      response = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'title': title, 'text': text}),
          )
          .timeout(const Duration(seconds: 30));
    } on TimeoutException {
      throw QuizApiException(
          'The server took too long to answer. Try again in a moment.');
    } catch (_) {
      throw QuizApiException('Could not reach the server. Check your connection.');
    }

    if (response.statusCode != 200) {
      throw QuizApiException(_errorDetail(response));
    }
  }

  /// Saved notes ranked by the user's accuracy, weakest first. No AI is involved,
  /// so this is cheap and tells us whether there is anything to review.
  Future<List<WeakSpot>> fetchWeakSpots() async {
    final uri = Uri.parse('$baseUrl/weak-spots');

    late final http.Response response;
    try {
      response = await http.get(uri).timeout(const Duration(seconds: 30));
    } on TimeoutException {
      throw QuizApiException(
          'The server took too long to answer. Try again in a moment.');
    } catch (_) {
      throw QuizApiException('Could not reach the server. Check your connection.');
    }

    if (response.statusCode != 200) {
      throw QuizApiException(_errorDetail(response));
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    return (data['sources'] as List)
        .map((s) => WeakSpot.fromJson(s as Map<String, dynamic>))
        .toList();
  }

  static const weakSpotGoal =
      'Review my weak spots: build the quiz from the notes where my accuracy is lowest.';

  /// Asks the backend's agent to build a quiz from the user's weakest notes.
  /// The agent makes several calls to the AI, so this is allowed to take longer.
  Future<QuizResult> generateWeakSpotQuiz({
    int numQuestions = 5,
    String difficulty = 'medium',
  }) async {
    final uri = Uri.parse('$baseUrl/agent/generate-quiz');

    late final http.Response response;
    try {
      response = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'goal': weakSpotGoal,
              'num_questions': numQuestions,
              'difficulty': difficulty,
              'verify': true,
            }),
          )
          .timeout(const Duration(seconds: 120));
    } on TimeoutException {
      throw QuizApiException(
          'The quiz took too long to build. Try again with fewer questions.');
    } catch (_) {
      throw QuizApiException('Could not reach the server. Check your connection.');
    }

    return _parseQuizResponse(
      response,
      friendlyErrors: const {
        400: 'Your library is empty. Give your notes a title to save them, '
            'then take a quiz first.',
      },
    );
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

  String _errorDetail(http.Response response) {
    final body = _tryDecode(response.body);
    return body?['detail']?.toString() ?? 'Unknown error.';
  }

  QuizResult _parseQuizResponse(
    http.Response response, {
    Map<int, String> friendlyErrors = const {},
  }) {
    if (response.statusCode != 200) {
      final friendly = friendlyErrors[response.statusCode];
      if (friendly != null) throw QuizApiException(friendly);
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

    return QuizResult(
      quizId: data['quiz_id'] as int,
      questions: questions,
      source: data['source'] as String?,
    );
  }

  Map<String, dynamic>? _tryDecode(String body) {
    try {
      return jsonDecode(body) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }
}
