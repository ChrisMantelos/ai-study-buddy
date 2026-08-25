import 'package:flutter/material.dart';
import 'quiz_question.dart';

class QuizScreen extends StatefulWidget {
  final List<QuizQuestion> questions;

  const QuizScreen({super.key, required this.questions});

  @override
  State<QuizScreen> createState() => _QuizScreenState();
}

class _QuizScreenState extends State<QuizScreen> {
  int currentIndex = 0;
  int? selectedOption;
  int score = 0;
  bool finished = false;

  QuizQuestion get currentQuestion => widget.questions[currentIndex];

  void selectOption(int index) {
    if (selectedOption != null) return;
    setState(() {
      selectedOption = index;
      if (index == currentQuestion.correctIndex) {
        score++;
      }
    });
  }

  void nextQuestion() {
    if (currentIndex == widget.questions.length - 1) {
      setState(() => finished = true);
      return;
    }
    setState(() {
      currentIndex++;
      selectedOption = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (finished) {
      return _ResultView(
        score: score,
        total: widget.questions.length,
        onRestart: () => Navigator.of(context).pop(),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text('Question ${currentIndex + 1} of ${widget.questions.length}'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              currentQuestion.question,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 24),
            ...List.generate(currentQuestion.options.length, (index) {
              return _OptionTile(
                text: currentQuestion.options[index],
                state: _tileState(index),
                onTap: () => selectOption(index),
              );
            }),
            if (selectedOption != null) ...[
              const SizedBox(height: 16),
              Text(
                currentQuestion.explanation,
                style: TextStyle(color: Colors.grey.shade600),
              ),
              const Spacer(),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: nextQuestion,
                  child: Text(
                    currentIndex == widget.questions.length - 1
                        ? 'Finish'
                        : 'Next question',
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  _OptionState _tileState(int index) {
    if (selectedOption == null) return _OptionState.neutral;
    if (index == currentQuestion.correctIndex) return _OptionState.correct;
    if (index == selectedOption) return _OptionState.incorrect;
    return _OptionState.disabled;
  }
}

enum _OptionState { neutral, correct, incorrect, disabled }

class _OptionTile extends StatelessWidget {
  final String text;
  final _OptionState state;
  final VoidCallback onTap;

  const _OptionTile({
    required this.text,
    required this.state,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    Color? backgroundColor;
    Color borderColor = Colors.grey.shade300;

    switch (state) {
      case _OptionState.correct:
        backgroundColor = Colors.green.shade50;
        borderColor = Colors.green;
        break;
      case _OptionState.incorrect:
        backgroundColor = Colors.red.shade50;
        borderColor = Colors.red;
        break;
      case _OptionState.disabled:
      case _OptionState.neutral:
        break;
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
          decoration: BoxDecoration(
            color: backgroundColor,
            border: Border.all(color: borderColor),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(text),
        ),
      ),
    );
  }
}

class _ResultView extends StatelessWidget {
  final int score;
  final int total;
  final VoidCallback onRestart;

  const _ResultView({
    required this.score,
    required this.total,
    required this.onRestart,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '$score / $total',
              style: const TextStyle(fontSize: 48, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            const Text('Quiz complete'),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: onRestart,
              child: const Text('Back to notes'),
            ),
          ],
        ),
      ),
    );
  }
}
