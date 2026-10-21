class QuizQuestion {
  final String question;
  final List<String> options;
  final int correctIndex;
  final String explanation;

  QuizQuestion({
    required this.question,
    required this.options,
    required this.correctIndex,
    required this.explanation,
  });

  factory QuizQuestion.fromJson(Map<String, dynamic> json) {
    return QuizQuestion(
      question: json['question'] as String,
      options: List<String>.from(json['options'] as List),
      correctIndex: json['correct_index'] as int,
      explanation: json['explanation'] as String,
    );
  }
}

class QuizResult {
  final int quizId;
  final List<QuizQuestion> questions;

  /// Title of the saved note the quiz was built from, when the backend knows it.
  final String? source;

  QuizResult({required this.quizId, required this.questions, this.source});
}

/// One saved note with the user's average quiz accuracy on it.
class WeakSpot {
  final String source;
  final double avgAccuracy;
  final int scoredQuizzes;

  WeakSpot({
    required this.source,
    required this.avgAccuracy,
    required this.scoredQuizzes,
  });

  factory WeakSpot.fromJson(Map<String, dynamic> json) {
    return WeakSpot(
      source: json['source'] as String,
      avgAccuracy: (json['avg_accuracy'] as num).toDouble(),
      scoredQuizzes: json['scored_quizzes'] as int,
    );
  }
}
