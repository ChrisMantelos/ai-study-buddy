import 'package:flutter/material.dart';
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
        colorSchemeSeed: Colors.indigo,
        useMaterial3: true,
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
      appBar: AppBar(title: const Text('AI Study Buddy')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Paste your notes and get a quiz to test yourself.',
              style: TextStyle(fontSize: 16),
            ),
            const SizedBox(height: 16),
            Expanded(
              child: TextField(
                controller: notesController,
                maxLines: null,
                expands: true,
                textAlignVertical: TextAlignVertical.top,
                decoration: const InputDecoration(
                  hintText: 'Paste study notes here...',
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                const Text('Questions:'),
                const SizedBox(width: 12),
                DropdownButton<int>(
                  value: numQuestions,
                  items: [3, 5, 7, 10]
                      .map((n) => DropdownMenuItem(value: n, child: Text('$n')))
                      .toList(),
                  onChanged: (value) {
                    if (value != null) setState(() => numQuestions = value);
                  },
                ),
              ],
            ),
            if (errorMessage != null) ...[
              const SizedBox(height: 8),
              Text(errorMessage!, style: const TextStyle(color: Colors.red)),
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: loading ? null : generateQuiz,
                child: loading
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Generate quiz'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
