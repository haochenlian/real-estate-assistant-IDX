"""
Live RAG demo (Week 8).

Indexes the knowledge documents with real OpenAI embeddings, then answers the
three sample questions from the handbook -- showing the answer plus which source
documents it came from. Needs an API key in .env.

Usage:
    python3 demo_rag.py                      # runs the three sample questions
    python3 demo_rag.py "What is a comp?"    # ask your own
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from rag import load_documents, build_index, get_embedding, answer_question  # noqa: E402

SAMPLE_QUESTIONS = [
    "What does DOM mean?",
    "What columns are in california_sold?",
    "How is the list-to-close ratio calculated?",
]


def main():
    questions = sys.argv[1:] or SAMPLE_QUESTIONS

    docs = load_documents()
    print(f"Indexing {len(docs)} documents via OpenAI embeddings...")
    index = build_index(docs, get_embedding)
    print(f"Indexed {len(index)} passages.\n")

    for question in questions:
        result = answer_question(question, index)
        print("=" * 70)
        print(f"Q: {result['question']}\n")
        print(f"A: {result['answer']}\n")
        print(f"Sources: {', '.join(result['sources'])}")
        top = result["passages"][0]
        print(f"Top passage [{top['source']}] score {top['score']}")
        print()


if __name__ == "__main__":
    main()
