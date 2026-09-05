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
  int numQuestions = 5;
  bool loading = false;
  String? errorMessage;

  Future<void> generateQuiz() async {
    if (notesController.text.trim().isEmpty) {
      setState(() => errorMessage = 'Paste some notes first.');
      return;
    }

    setState(() {
      loading = true;
      errorMessage = null;
    });

    try {
      final questions = await api.generateQuiz(
        notes: notesController.text.trim(),
        numQuestions: numQuestions,
      );
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => QuizScreen(questions: questions)),
      );
    } on QuizApiException catch (e) {
      setState(() => errorMessage = e.message);
    } finally {
      if (mounted) setState(() => loading = false);
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
                constraints: const BoxConstraints(maxWidth: 640),
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
                      decoration: InputDecoration(
                        border: InputBorder.none,
                        hintText: 'Paste study notes here...',
                        hintStyle: StudyText.mono.copyWith(
                          color: StudyColors.inkSoft,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Text('Questions', style: StudyText.mono),
                      const SizedBox(width: 12),
                      Container(
                        decoration: BoxDecoration(
                          border: Border.all(color: StudyColors.ink, width: 2),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<int>(
                            value: numQuestions,
                            isDense: true,
                            padding: const EdgeInsets.symmetric(
                                horizontal: 10, vertical: 8),
                            style: StudyText.mono,
                            items: [3, 5, 7, 10]
                                .map((n) => DropdownMenuItem(
                                    value: n, child: Text('$n')))
                                .toList(),
                            onChanged: (value) {
                              if (value != null) {
                                setState(() => numQuestions = value);
                              }
                            },
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (errorMessage != null) ...[
                    const SizedBox(height: 16),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 12),
                      decoration: BoxDecoration(
                        color: StudyColors.incorrectBg,
                        border: Border(
                          left: BorderSide(
                              color: StudyColors.incorrect, width: 4),
                        ),
                      ),
                      child: Text(
                        errorMessage!,
                        style: StudyText.mono.copyWith(
                          color: StudyColors.incorrect,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 20),
                  HighlighterButton(
                    label: 'Generate quiz',
                    onPressed: loading ? null : generateQuiz,
                    child: loading
                        ? const SizedBox(
                            height: 18,
                            width: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: StudyColors.ink,
                            ),
                          )
                        : Text(
                            'Generate quiz',
                            style: StudyText.body.copyWith(
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                  ),
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
