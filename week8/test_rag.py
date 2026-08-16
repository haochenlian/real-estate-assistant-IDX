"""Tests for the Week 8 RAG pipeline (chunking, retrieval, prompt grounding).

Uses a stand-in embedder so the retrieval logic is verified without API calls.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from rag import (chunk_text, load_documents, build_index, retrieve,
                 build_prompt, GROUNDING_INSTRUCTION)


# A deterministic stand-in for OpenAI embeddings: counts a few keywords so
# passages about the same topic land near each other in vector space.
KEYWORDS = ["dom", "market", "price", "ratio", "column", "table", "bedroom"]


def fake_embed(text: str) -> list[float]:
    low = text.lower()
    return [float(low.count(word)) for word in KEYWORDS]


# ---- chunking ----------------------------------------------------------
def test_chunks_cover_the_text():
    text = "a" * 1000
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_chunks_overlap():
    text = "".join(str(i % 10) for i in range(1000))
    chunks = chunk_text(text, chunk_size=300, overlap=100)
    # the tail of chunk 0 must reappear at the head of chunk 1
    assert chunks[0][-100:] == chunks[1][:100]


def test_short_text_is_one_chunk():
    assert chunk_text("Short definition.", chunk_size=600) == ["Short definition."]


def test_empty_text_returns_nothing():
    assert chunk_text("") == []


def test_invalid_overlap_rejected():
    try:
        chunk_text("some text", chunk_size=100, overlap=100)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


# ---- documents ---------------------------------------------------------
def test_knowledge_documents_load():
    docs = load_documents()
    assert len(docs) >= 2
    titles = [d["title"] for d in docs]
    assert "glossary.md" in titles
    assert "schema_fields.md" in titles


def test_documents_have_content():
    for doc in load_documents():
        assert len(doc["content"]) > 100


# ---- indexing ----------------------------------------------------------
def test_index_entries_carry_source_and_vector():
    index = build_index(load_documents(), fake_embed)
    assert len(index) > 5
    entry = index[0]
    assert set(entry) == {"source", "chunk", "embedding"}
    assert entry["source"].endswith(".md")
    assert len(entry["embedding"]) == len(KEYWORDS)


# ---- retrieval ---------------------------------------------------------
def test_retrieve_returns_top_k():
    index = build_index(load_documents(), fake_embed)
    assert len(retrieve(fake_embed("what does dom mean"), index, top_k=3)) == 3


def test_retrieve_is_ordered_by_score():
    index = build_index(load_documents(), fake_embed)
    hits = retrieve(fake_embed("list to close ratio price"), index, top_k=4)
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_finds_the_right_topic():
    index = build_index(load_documents(), fake_embed)
    hits = retrieve(fake_embed("dom days on market"), index, top_k=3)
    assert any("dom" in h["chunk"].lower() for h in hits)


def test_retrieve_handles_empty_index():
    assert retrieve([1, 0], [], top_k=3) == []


# ---- prompt grounding --------------------------------------------------
def test_prompt_contains_instruction_context_and_question():
    passages = [{"source": "glossary.md", "chunk": "DOM means days on market."}]
    prompt = build_prompt("What does DOM mean?", passages)
    assert GROUNDING_INSTRUCTION in prompt
    assert "DOM means days on market." in prompt
    assert "What does DOM mean?" in prompt


def test_prompt_labels_each_source():
    passages = [{"source": "glossary.md", "chunk": "A"},
                {"source": "schema_fields.md", "chunk": "B"}]
    prompt = build_prompt("q", passages)
    assert "[glossary.md]" in prompt
    assert "[schema_fields.md]" in prompt


def test_prompt_tells_model_not_to_guess():
    prompt = build_prompt("q", [{"source": "s", "chunk": "c"}])
    assert "ONLY" in prompt
    assert "guess" in prompt.lower()


TESTS = [test_chunks_cover_the_text, test_chunks_overlap, test_short_text_is_one_chunk,
         test_empty_text_returns_nothing, test_invalid_overlap_rejected,
         test_knowledge_documents_load, test_documents_have_content,
         test_index_entries_carry_source_and_vector, test_retrieve_returns_top_k,
         test_retrieve_is_ordered_by_score, test_retrieve_finds_the_right_topic,
         test_retrieve_handles_empty_index,
         test_prompt_contains_instruction_context_and_question,
         test_prompt_labels_each_source, test_prompt_tells_model_not_to_guess]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1; print(f"PASS | {t.__name__}")
        except AssertionError as e:
            print(f"FAIL | {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed.")
