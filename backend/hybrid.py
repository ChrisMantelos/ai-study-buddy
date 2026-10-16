"""Dense and hybrid retrieval, to measure against plain BM25.

Not wired into main.py: it is an experiment that evaluate.py can run, so the
decision to adopt it can be made on numbers.

    bm25    keyword ranking (same tokenizer as rag.py)
    dense   cosine similarity between embeddings of the query and of each chunk
    hybrid  both rankings merged with Reciprocal Rank Fusion (RRF)

Embedders (pick with `evaluate.py retrieval --embedder ...`):
    glove   averaged GloVe word vectors, IDF-weighted. Needs `pip install gensim`
            and downloads ~70 MB once. Static word vectors: weaker than a real
            sentence-embedding model, but small and easy to run anywhere.
    minilm  sentence-transformers all-MiniLM-L6-v2. Needs `pip install
            sentence-transformers` (pulls in PyTorch, which is large).
"""
import math
from collections import Counter

import numpy as np
from rank_bm25 import BM25Okapi

from rag import tokenize


class GloveEmbedder:
    name = "glove"

    def __init__(self, model: str = "glove-wiki-gigaword-50"):
        import gensim.downloader as api

        self.vectors = api.load(model)
        self.idf: dict[str, float] = {}
        self.default_idf = 1.0

    def fit(self, texts: list[str]) -> None:
        """Learn IDF weights from the library so common words count for less."""
        n = len(texts)
        df: Counter = Counter()
        for text in texts:
            df.update(set(tokenize(text)))
        self.idf = {word: math.log(1 + n / count) for word, count in df.items()}
        self.default_idf = math.log(1 + n)

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.vectors.vector_size), dtype=float)
        for i, text in enumerate(texts):
            for token in tokenize(text):
                if token in self.vectors:
                    out[i] += self.idf.get(token, self.default_idf) * self.vectors[token]
            norm = np.linalg.norm(out[i])
            if norm > 0:
                out[i] /= norm
        return out


class SentenceTransformerEmbedder:
    name = "minilm"

    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model)

    def fit(self, texts: list[str]) -> None:
        pass

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(list(texts), normalize_embeddings=True), dtype=float)


def make_embedder(name: str):
    if name == "glove":
        return GloveEmbedder()
    if name == "minilm":
        return SentenceTransformerEmbedder()
    raise ValueError(f"Unknown embedder '{name}'. Choose 'glove' or 'minilm'.")


class HybridIndex:
    """Search over a fixed list of chunks. Rebuild it when the chunks change."""

    def __init__(self, chunks: list[str], sources: list[str], embedder, rrf_k: int = 60):
        self.chunks = list(chunks)
        self.sources = list(sources)
        self.rrf_k = rrf_k
        self.bm25 = BM25Okapi([tokenize(c) for c in self.chunks]) if self.chunks else None
        self.embedder = embedder
        embedder.fit(self.chunks)
        self.matrix = embedder.encode(self.chunks) if self.chunks else np.zeros((0, 1))

    def _bm25_ranking(self, query: str) -> list[int]:
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [i for i in order if scores[i] > 0]

    def _dense_scores(self, query: str) -> np.ndarray:
        vector = self.embedder.encode([query])[0]
        if not np.any(vector):
            return np.full(len(self.chunks), -1.0)  # no known words: no signal
        return self.matrix @ vector

    def search(self, query: str, top_k: int = 5, mode: str = "hybrid") -> list[dict]:
        if not self.chunks:
            return []

        dense = self._dense_scores(query)
        dense_ranking = [i for i in np.argsort(-dense) if dense[i] > -1.0]

        if mode == "dense":
            ranked = [(i, float(dense[i])) for i in dense_ranking]
        elif mode == "hybrid":
            fused: dict[int, float] = {}
            for ranking in (self._bm25_ranking(query), dense_ranking):
                for rank, i in enumerate(ranking, 1):
                    fused[i] = fused.get(i, 0.0) + 1.0 / (self.rrf_k + rank)
            ranked = sorted(fused.items(), key=lambda item: item[1], reverse=True)
        else:
            raise ValueError(f"Unknown mode '{mode}'. Choose 'dense' or 'hybrid'.")

        return [
            {"text": self.chunks[i], "source": self.sources[i], "score": round(score, 4)}
            for i, score in ranked[:top_k]
        ]
