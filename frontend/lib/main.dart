import 'package:flutter/material.dart';
import 'study_theme.dart';
import 'study_buddy_api.dart';
import 'quiz_screen.dart';

const backendUrl = String.fromEnvironment(
  'BACKEND_URL',
  defaultValue: 'http://127.0.0.1:8000',
);

void main() {
  runApp(const StudyBuddyApp());
}

class StudyBuddyApp extends StatelessWidget {
  const StudyBuddyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'AI Study Buddy',
      theme: ThemeData(
        scaffoldBackgroundColor: StudyColors.paper,
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: StudyColors.ink,
          surface: StudyColors.paper,
        ),
      ),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final api = StudyBuddyApi(baseUrl: backendUrl);
  final notesController = TextEditingController();
  final titleController = TextEditingController();
  int numQuestions = 5;
  String difficulty = 'medium';
  // Which action is running: 'quiz', 'weak', or null when idle.
  String? busy;
  String? errorMessage;
  // Shown under the weak-spot button, so it appears next to what was pressed.
  String? weakErrorMessage;
  // The last note saved to the library, so that pressing the button again (for
  // example after a failed quiz) does not store the same note twice.
  String? lastSavedKey;

  Future<void> generateQuiz() async {
    final notes = notesController.text.trim();
    final title = titleController.text.trim();
    if (notes.isEmpty) {
      setState(() => errorMessage = 'Paste some notes first.');
      return;
    }

    setState(() {
      busy = 'quiz';
      errorMessage = null;
      weakErrorMessage = null;
    });

    try {
      // With a title, the note is also saved to the library and the quiz is
      // recorded under that title, so "Review my weak spots" can use its score.
      if (title.isNotEmpty) {
        final key = '$title\n$notes';
        if (key != lastSavedKey) {
          await api.addNote(title: title, text: notes);
          lastSavedKey = key;
        }
      }
      final result = await api.generateQuiz(
        notes: notes,
        numQuestions: numQuestions,
        difficulty: difficulty,
        source: title.isEmpty ? null : title,
      );
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => QuizScreen(api: api, result: result),
        ),
      );
    } on QuizApiException catch (e) {
      if (mounted) setState(() => errorMessage = e.message);
    } finally {
      if (mounted) setState(() => busy = null);
    }
  }

  Future<void> reviewWeakSpots() async {
    setState(() {
      busy = 'weak';
      errorMessage = null;
      weakErrorMessage = null;
    });

    try {
      // Cheap check first (no AI): is there any score to learn from?
      final spots = await api.fetchWeakSpots();
      if (spots.isEmpty) {
        throw QuizApiException(
          'No scores for saved notes yet. Give your notes a title under '
          '"Save to library as", finish a quiz, then come back here.',
        );
      }
      final result = await api.generateWeakSpotQuiz(
        numQuestions: numQuestions,
        difficulty: difficulty,
      );
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => QuizScreen(api: api, result: result),
        ),
      );
    } on QuizApiException catch (e) {
      if (mounted) setState(() => weakErrorMessage = e.message);
    } finally {
      if (mounted) setState(() => busy = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: NotebookBackground(
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 720),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Study Buddy', style: StudyText.masthead),
                        Text(
                          backendUrl.replaceFirst('http://', ''),
                          style: StudyText.label,
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Container(height: 3, color: StudyColors.ink),
                    const SizedBox(height: 16),
                    Text(
                      'Paste your notes below. Fill in the answer sheet that comes back.',
                      style: StudyText.bodySoft,
                    ),
                    const SizedBox(height: 24),
                    Text('NOTES', style: StudyText.label),
                    const SizedBox(height: 8),
                    Container(
                      height: 220,
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        border: Border.all(color: StudyColors.ink, width: 2),
                      ),
                      child: TextField(
                        controller: notesController,
                        maxLines: null,
                        expands: true,
                        textAlignVertical: TextAlignVertical.top,
                        style: StudyText.mono,
                        onChanged: (_) => setState(() {}),
                        decoration: InputDecoration(
                          border: InputBorder.none,
                          hintText: 'Paste study notes here...',
                          hintStyle: StudyText.mono.copyWith(
                            color: StudyColors.inkSoft,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Align(
                      alignment: Alignment.centerRight,
                      child: Text(
                        '${notesController.text.length} / 8000 characters',
                        style: StudyText.label,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text('SAVE TO LIBRARY AS (OPTIONAL)', style: StudyText.label),
                    const SizedBox(height: 8),
                    Container(
                      padding:
                          const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        border: Border.all(color: StudyColors.ink, width: 2),
                      ),
                      child: TextField(
                        controller: titleController,
                        maxLength: 200,
                        style: StudyText.mono,
                        decoration: InputDecoration(
                          border: InputBorder.none,
                          counterText: '',
                          hintText: 'e.g. Biology: Mitochondria',
                          hintStyle: StudyText.mono.copyWith(
                            color: StudyColors.inkSoft,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'A title keeps these notes in your library. '
                      'Saved notes are what weak-spot review uses.',
                      style: StudyText.label,
                    ),
                    const SizedBox(height: 16),
                    Wrap(
                      spacing: 24,
                      runSpacing: 12,
                      children: [
                        _DropdownField<int>(
                          label: 'Questions',
                          value: numQuestions,
                          options: const [3, 5, 7, 10],
                          labelBuilder: (n) => '$n',
                          onChanged: (value) => setState(() => numQuestions = value),
                        ),
                        _DropdownField<String>(
                          label: 'Difficulty',
                          value: difficulty,
                          options: const ['easy', 'medium', 'hard'],
                          labelBuilder: (d) => d,
                          onChanged: (value) => setState(() => difficulty = value),
                        ),
                      ],
                    ),
                    if (errorMessage != null) ...[
                      const SizedBox(height: 16),
                      _ErrorBox(message: errorMessage!),
                    ],
                    const SizedBox(height: 20),
                    HighlighterButton(
                      label: 'Generate quiz',
                      onPressed: busy != null ? null : generateQuiz,
                      child: busy == 'quiz'
                          ? const _Spinner()
                          : Text(
                              'Generate quiz',
                              style: StudyText.body.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                    ),
                    const SizedBox(height: 28),
                    Container(height: 1, color: StudyColors.paperLine),
                    const SizedBox(height: 20),
                    Text('WEAK SPOTS', style: StudyText.label),
                    const SizedBox(height: 6),
                    Text(
                      'Builds a quiz from your saved notes where your scores are '
                      'lowest. An agent reads your history first, so this takes '
                      'longer than a normal quiz.',
                      style: StudyText.bodySoft,
                    ),
                    const SizedBox(height: 12),
                    HighlighterButton(
                      label: 'Review my weak spots',
                      onPressed: busy != null ? null : reviewWeakSpots,
                      child: busy == 'weak'
                          ? const _Spinner()
                          : Text(
                              'Review my weak spots',
                              style: StudyText.body.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                    ),
                    if (weakErrorMessage != null) ...[
                      const SizedBox(height: 12),
                      _ErrorBox(message: weakErrorMessage!),
                    ],
                    const SizedBox(height: 40),
                    const _ExampleQuestionPreview(),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _DropdownField<T> extends StatelessWidget {
  final String label;
  final T value;
  final List<T> options;
  final String Function(T) labelBuilder;
  final ValueChanged<T> onChanged;

  const _DropdownField({
    required this.label,
    required this.value,
    required this.options,
    required this.labelBuilder,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: StudyText.mono),
        const SizedBox(width: 12),
        Container(
          decoration: BoxDecoration(
            border: Border.all(color: StudyColors.ink, width: 2),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<T>(
              value: value,
              isDense: true,
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              style: StudyText.mono,
              items: options
                  .map((o) => DropdownMenuItem(value: o, child: Text(labelBuilder(o))))
                  .toList(),
              onChanged: (v) {
                if (v != null) onChanged(v);
              },
            ),
          ),
        ),
      ],
    );
  }
}

class _ExampleQuestionPreview extends StatelessWidget {
  const _ExampleQuestionPreview();

  static const options = ['Ribosome', 'Mitochondria', 'Golgi apparatus'];

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: 0.55,
      child: Container(
        padding: const EdgeInsets.only(top: 20),
        decoration: BoxDecoration(
          border: Border(
            top: BorderSide(color: StudyColors.paperLine, width: 1),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Example - this is what comes back', style: StudyText.label),
            const SizedBox(height: 10),
            Text(
              'Which organelle is described as the site of cellular respiration?',
              style: StudyText.questionText,
            ),
            const SizedBox(height: 16),
            ...List.generate(options.length, (index) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  children: [
                    Container(
                      width: 26,
                      height: 26,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        border: Border.all(color: StudyColors.ink, width: 2),
                        borderRadius: const BorderRadius.only(
                          topLeft: Radius.circular(13),
                          topRight: Radius.circular(11),
                          bottomLeft: Radius.circular(11),
                          bottomRight: Radius.circular(14),
                        ),
                      ),
                      child: Text(
                        String.fromCharCode(65 + index),
                        style: StudyText.mono.copyWith(fontSize: 11),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Text(options[index], style: StudyText.body),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

class _Spinner extends StatelessWidget {
  const _Spinner();

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      height: 18,
      width: 18,
      child: CircularProgressIndicator(
        strokeWidth: 2,
        color: StudyColors.ink,
      ),
    );
  }
}

class _ErrorBox extends StatelessWidget {
  final String message;

  const _ErrorBox({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: StudyColors.incorrectBg,
        border: Border(
          left: BorderSide(color: StudyColors.incorrect, width: 4),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.error_outline,
            size: 16,
            color: StudyColors.incorrect,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: StudyText.mono.copyWith(
                color: StudyColors.incorrect,
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
