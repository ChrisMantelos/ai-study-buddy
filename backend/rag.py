import re
from rank_bm25 import BM25Okapi


def chunk_text(text: str, max_words: int = 120) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []

    for paragraph in paragraphs:
        words = paragraph.split()
        if len(words) <= max_words:
            chunks.append(paragraph)
            continue
        for i in range(0, len(words), max_words):
            chunks.append(" ".join(words[i:i + max_words]))

    return chunks


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z]+", text.lower())


class NoteLibrary:
    def __init__(self):
        self.chunks: list[str] = []
        self.sources: list[str] = []

    def add_document(self, title: str, text: str) -> int:
        new_chunks = chunk_text(text)
        self.chunks.extend(new_chunks)
        self.sources.extend([title] * len(new_chunks))
        return len(new_chunks)

    def is_empty(self) -> bool:
        return len(self.chunks) == 0

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if self.is_empty():
            return []

        tokenized_chunks = [tokenize(chunk) for chunk in self.chunks]
        bm25 = BM25Okapi(tokenized_chunks)

        tokenized_query = tokenize(query)
        scores = bm25.get_scores(tokenized_query)

        ranked_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )

        results = []
        for i in ranked_indices[:top_k]:
            if scores[i] <= 0:
                continue
            results.append({
                "text": self.chunks[i],
                "source": self.sources[i],
                "score": round(float(scores[i]), 3),
            })

        return results
