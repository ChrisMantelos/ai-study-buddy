# AI Study Buddy

Paste study notes, get a multiple-choice quiz generated from them, and test
yourself. A Flutter app talking to a Python backend that calls the Claude API.

Note: no live demo is deployed yet. See "Deploying the backend" below.

---

## Why I built this

Making practice questions from your own notes takes time. This automates
that step so studying starts faster.

## Architecture

```
Flutter app  --HTTP-->  FastAPI backend  --API call-->  Claude
```

The Flutter app never talks to Claude directly. It only calls the backend,
which holds the API key and does the actual generation. This keeps the key
off the client and makes it possible to add features later (auth, rate
limiting, saving quiz history) without touching the app.

## Project structure

```
ai-study-buddy/
    backend/
        main.py           FastAPI app: quiz generation, notes library endpoints
        rag.py            chunking and BM25 retrieval for the notes library
        requirements.txt
    frontend/
        lib/
            main.dart          app entry point, notes input screen
            quiz_screen.dart   quiz taking screen with scoring
            study_buddy_api.dart   HTTP client for the backend
            quiz_question.dart     data model
        pubspec.yaml
    frontend-web/
        index.html        standalone browser test page, no build step
```

## Running the backend

```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-your-key-here
uvicorn main:app --reload
```

Runs at `http://127.0.0.1:8000`. Check it works:

```bash
curl http://127.0.0.1:8000/health
```

## Running the Flutter app

```bash
cd frontend
flutter pub get
flutter run -d chrome --dart-define=BACKEND_URL=http://127.0.0.1:8000
```

The `BACKEND_URL` define points the app at your running backend. Without
it, the app defaults to `http://127.0.0.1:8000`.

## Trying the browser test page (no Flutter needed)

`frontend-web/index.html` is a standalone page that talks to the same
backend, useful for testing or demoing without installing Flutter. It has
no dependencies and no build step.

1. Start the backend as described above, and leave it running.
2. Open `frontend-web/index.html` directly in a browser (double-click it,
   or drag it into a browser window).
3. Paste some notes and generate a quiz.

It expects the backend at `http://127.0.0.1:8000`. If you deploy the
backend elsewhere, change the `BACKEND_URL` constant near the top of the
`<script>` section in that file.

## Building a quiz from a topic (RAG)

Besides pasting notes directly, you can build up a library of notes over
time and generate a quiz on a specific topic, without needing to paste
everything into one request.

Add a document to the library:

```bash
curl -X POST http://127.0.0.1:8000/notes \
  -H "Content-Type: application/json" \
  -d '{"title": "Biology Chapter 1", "text": "Photosynthesis is..."}'
```

Add as many documents as you like this way. Then generate a quiz on a
topic instead of pasting notes:

```bash
curl -X POST http://127.0.0.1:8000/generate-quiz-from-topic \
  -H "Content-Type: application/json" \
  -d '{"topic": "mitochondria", "num_questions": 5}'
```

The backend searches the library for the most relevant chunks using BM25
keyword search, sends only those chunks to Claude, and returns a quiz -
the same pattern used in the "RAG and Agentic Search" section of the
"Building with the Claude API" course. The library is kept in memory and
resets when the server restarts; it is not persisted to disk.

## Deploying the backend

1. Push this repo to GitHub.
2. Create a free account at render.com.
3. New Web Service, connect this repo, set the root directory to `backend`.
4. Build command: `pip install -r requirements.txt`. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
5. Add an environment variable: `ANTHROPIC_API_KEY` with your real key.
6. Deploy. You get a public URL, something like `https://ai-study-buddy.onrender.com`.
7. Run the Flutter app with that URL: `flutter run -d chrome --dart-define=BACKEND_URL=https://ai-study-buddy.onrender.com`

## Testing status

Backend: fully tested by running the server and sending real requests.
Confirmed working: input validation (empty notes rejected, question count
capped at 10), missing API key handled cleanly, invalid API key handled
cleanly with no crash. The notes library and topic-based retrieval
(`/notes`, `/generate-quiz-from-topic`) were also tested directly: adding
documents, listing them, searching with a matching topic (correctly
reaches the AI call and stops cleanly without a key), and searching with
an unrelated topic (correctly returns a 404 with no relevant chunks
found). The success path (a valid key producing a real quiz, from either
endpoint) was not run, since that requires a real key - confirm that once
yourself.

Frontend: written but not run against the Flutter SDK, since it is not
available in the environment this was built in. The code has been checked
for structural correctness (balanced brackets, consistent types across
files), but a real `flutter run` may still surface issues that only the
Flutter compiler and analyzer can catch. Run `flutter analyze` before
relying on this, and treat the first `flutter run` as your actual test.

## Possible extensions

- Save quiz history locally
- Support uploading a PDF or image of notes instead of pasting text
- Flashcard mode in addition to quiz mode
- Difficulty levels

## Tech stack

Flutter, Dart, Python, FastAPI, Anthropic SDK
