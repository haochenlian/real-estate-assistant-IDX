"""
RAG knowledge assistant (Week 8).

Answers conceptual questions -- "What does DOM mean?", "What columns are in
california_sold?", "How is the list-to-close ratio calculated?" -- by retrieving
relevant passages from source documents and having the model answer *only* from
those passages. This keeps answers grounded instead of hallucinated.

Pipeline (retrieval-augmented generation):
    documents --chunk--> passages --embed--> indexed vectors
    question  --embed--> vector
    rank passages by cosine similarity  -->  top passages
    passages + question --> LLM --> grounded answer (with sources)

Reuses Week 6 for embeddings and cosine similarity; only the LLM call and the
embedding call need an API key.

Author: Howard (Haochen) Lian - IDX Exchange, Agentic AI Track, Summer 2026
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "week6"))
from semantic_search import cosine_similarity  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "knowledge")


# ----------------------------------------------------------------- chunking ---

def chunk_text(text: str, chunk_size: int = 600, overlap: int = 100) -> list[str]:
    """Split a document into overlapping passages of roughly chunk_size characters.

    Overlap matters: a definition that straddles a boundary would otherwise be cut
    in half and lose its meaning, so consecutive chunks repeat some text.
    """
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks, start = [], 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def load_documents(directory: str = KNOWLEDGE_DIR) -> list[dict]:
    """Read every markdown/text file in the knowledge folder."""
    docs = []
    if not os.path.isdir(directory):
        return docs
    for name in sorted(os.listdir(directory)):
        if not name.endswith((".md", ".txt")):
            continue
        path = os.path.join(directory, name)
        with open(path, encoding="utf-8") as fh:
            docs.append({"title": name, "content": fh.read()})
    return docs


# ------------------------------------------------------------------ indexing ---

def build_index(docs: list[dict], embed_fn) -> list[dict]:
    """Turn documents into a searchable index of embedded passages.

    `embed_fn` is injected so the index can be built with the real OpenAI
    embedder or with a stand-in during testing.
    """
    index = []
    for doc in docs:
        for chunk in chunk_text(doc["content"]):
            index.append({
                "source": doc["title"],
                "chunk": chunk,
                "embedding": embed_fn(chunk),
            })
    return index


def retrieve(question_vec: list[float], index: list[dict], top_k: int = 4) -> list[dict]:
    """Return the top_k passages most similar in meaning to the question."""
    scored = [(entry, cosine_similarity(question_vec, entry["embedding"]))
              for entry in index]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [dict(entry, score=round(score, 4)) for entry, score in scored[:top_k]]


# ------------------------------------------------------------------- prompting ---

GROUNDING_INSTRUCTION = (
    "Answer the question using ONLY the context below. "
    "If the context does not contain the answer, say you don't have that "
    "information rather than guessing."
)


def build_prompt(question: str, passages: list[dict]) -> str:
    """Assemble the grounded prompt sent to the model."""
    context = "\n\n---\n\n".join(
        f"[{p['source']}]\n{p['chunk']}" for p in passages
    )
    return f"{GROUNDING_INSTRUCTION}\n\nContext:\n{context}\n\nQuestion: {question}"


# ------------------------------------------------------- live OpenAI functions ---

def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Embed text via OpenAI (needs an API key)."""
    from openai import OpenAI
    client = OpenAI()
    text = text.replace("\n", " ").strip()[:8000]
    resp = client.embeddings.create(model=model, input=text)
    return resp.data[0].embedding


def generate_answer(prompt: str, model: str = "gpt-4o-mini") -> str:
    """Ask the model to answer from the supplied context (needs an API key)."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def answer_question(question: str, index: list[dict], top_k: int = 4) -> dict:
    """Full RAG round trip: retrieve passages, then answer from them."""
    question_vec = get_embedding(question)
    passages = retrieve(question_vec, index, top_k)
    prompt = build_prompt(question, passages)
    answer = generate_answer(prompt)
    return {
        "question": question,
        "answer": answer,
        "sources": sorted({p["source"] for p in passages}),
        "passages": passages,
    }


if __name__ == "__main__":
    docs = load_documents()
    print(f"Loaded {len(docs)} knowledge documents:")
    for doc in docs:
        pieces = chunk_text(doc["content"])
        print(f"  {doc['title']}: {len(doc['content'])} chars -> {len(pieces)} chunks")

    total = sum(len(chunk_text(d["content"])) for d in docs)
    print(f"\nTotal passages to index: {total}")
    print("\nExample prompt structure (no API call made):\n")
    fake_passages = [{"source": "glossary.md",
                      "chunk": "Days on Market, abbreviated DOM, is the number of days..."}]
    print(build_prompt("What does DOM mean?", fake_passages)[:400] + " ...")
