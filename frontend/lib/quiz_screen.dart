import 'package:flutter/material.dart';
import 'study_theme.dart';
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
      return NotebookBackground(
        child: _ResultView(
          score: score,
          total: widget.questions.length,
          onRestart: () => Navigator.of(context).pop(),
        ),
      );
    }

    return Scaffold(
      body: NotebookBackground(
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 24, 24, 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 640),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      IconButton(
                        onPressed: () => Navigator.of(context).pop(),
                        icon: const Icon(Icons.arrow_back, color: StudyColors.ink),
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        'Question ${currentIndex + 1} of ${widget.questions.length}',
                        style: StudyText.label,
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  Text(currentQuestion.question, style: StudyText.questionText),
                  const SizedBox(height: 24),
                  ...List.generate(currentQuestion.options.length, (index) {
                    return _OptionRow(
                      letter: String.fromCharCode(65 + index),
                      text: currentQuestion.options[index],
                      state: _tileState(index),
                      onTap: () => selectOption(index),
                    );
                  }),
                  if (selectedOption != null) ...[
                    const SizedBox(height: 12),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 12),
                      decoration: BoxDecoration(
                        color: StudyColors.correctBg,
                        border: Border(
                          left: BorderSide(color: StudyColors.correct, width: 4),
                        ),
                      ),
                      child: Text(
                        currentQuestion.explanation,
                        style: StudyText.bodySoft.copyWith(fontSize: 13.5),
                      ),
                    ),
                    const SizedBox(height: 20),
                    HighlighterButton(
                      label: currentIndex == widget.questions.length - 1
                          ? 'Finish'
                          : 'Next question',
                      onPressed: nextQuestion,
                    ),
                  ],
                ],
              ),
            ),
          ),
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

class _OptionRow extends StatelessWidget {
  final String letter;
  final String text;
  final _OptionState state;
  final VoidCallback onTap;

  const _OptionRow({
    required this.letter,
    required this.text,
    required this.state,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final locked = state != _OptionState.neutral;

    Color borderColor = StudyColors.ink;
    Color fillColor = Colors.white;
    Color textColor = StudyColors.ink;

    switch (state) {
      case _OptionState.correct:
        borderColor = StudyColors.correct;
        fillColor = StudyColors.correct;
        textColor = Colors.white;
        break;
      case _OptionState.incorrect:
        borderColor = StudyColors.incorrect;
        fillColor = StudyColors.incorrect;
        textColor = Colors.white;
        break;
      case _OptionState.disabled:
      case _OptionState.neutral:
        break;
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: locked ? null : onTap,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Container(
                width: 28,
                height: 28,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: state == _OptionState.neutral ? Colors.white : fillColor,
                  border: Border.all(color: borderColor, width: 2),
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(14),
                    topRight: Radius.circular(12),
                    bottomLeft: Radius.circular(12),
                    bottomRight: Radius.circular(15),
                  ),
                ),
                child: Text(
                  letter,
                  style: StudyText.mono.copyWith(
                    fontSize: 12,
                    color: state == _OptionState.neutral
                        ? StudyColors.ink
                        : textColor,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  text,
                  style: StudyText.body.copyWith(
                    color: state == _OptionState.disabled
                        ? StudyColors.inkSoft
                        : StudyColors.ink,
                  ),
                ),
              ),
            ],
          ),
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
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('$score / $total', style: StudyText.score),
            const SizedBox(height: 8),
            Text('Quiz complete', style: StudyText.bodySoft),
            const SizedBox(height: 28),
            SizedBox(
              width: 220,
              child: HighlighterButton(
                label: 'Back to notes',
                onPressed: onRestart,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
