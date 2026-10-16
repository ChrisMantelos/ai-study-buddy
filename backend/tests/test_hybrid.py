"""Tests for hybrid.py using a tiny fake embedder (no model download, no network)."""
import numpy as np
import pytest

from hybrid import HybridIndex
from rag import tokenize

# word -> concept id; synonyms share an id, which is what a real embedder would give
CONCEPTS = {"cats": 0, "feline": 0, "purr": 1, "dogs": 2, "canine": 2, "bark": 3}


class FakeEmbedder:
    name = "fake"

    def fit(self, texts):
        pass

    def encode(self, texts):
        out = np.zeros((len(texts), 4))
        for i, text in enumerate(texts):
            for token in tokenize(text):
                if token in CONCEPTS:
                    out[i, CONCEPTS[token]] += 1
            norm = np.linalg.norm(out[i])
            if norm:
                out[i] /= norm
        return out


CHUNKS = ["cats purr softly", "dogs bark loudly", "the weather is mild today"]
SOURCES = ["Cats", "Dogs", "Weather"]


def make_index():
    return HybridIndex(CHUNKS, SOURCES, FakeEmbedder())


def test_dense_finds_synonym_that_keyword_search_misses():
    index = make_index()
    # "feline" appears in no chunk, so BM25 has nothing; the embedder maps it to "cats"
    assert index._bm25_ranking("feline") == []
    results = index.search("feline", top_k=3, mode="dense")
    assert results[0]["source"] == "Cats"


def test_hybrid_returns_dense_only_matches():
    results = make_index().search("feline", top_k=3, mode="hybrid")
    assert results[0]["source"] == "Cats"


def test_hybrid_ranks_chunk_found_by_both_rankings_first():
    results = make_index().search("dogs bark", top_k=3, mode="hybrid")
    assert results[0]["source"] == "Dogs"
    assert results[0]["score"] > results[-1]["score"]


def test_query_with_no_known_words_falls_back_to_keyword_ranking():
    index = make_index()
    # "weather" is unknown to the embedder (zero vector) but BM25 still matches it
    results = index.search("weather", top_k=3, mode="hybrid")
    assert [r["source"] for r in results] == ["Weather"]
    assert index.search("weather", top_k=3, mode="dense") == []


def test_top_k_limits_results_and_result_shape():
    results = make_index().search("cats dogs", top_k=1, mode="hybrid")
    assert len(results) == 1
    assert set(results[0]) == {"text", "source", "score"}


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        make_index().search("cats", mode="magic")


def test_empty_index_returns_nothing():
    assert HybridIndex([], [], FakeEmbedder()).search("cats", mode="hybrid") == []
