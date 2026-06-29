# Multi-Agent Real Estate Assistant (IDX Exchange — Agentic AI Track, Summer 2026)

A production-style **multi-agent AI system** built on the **OpenClaw** agent framework that helps users search, understand, and get recommendations on real estate listings through natural language — coordinated by a multi-agent orchestrator and delivered through a WhatsApp + email communication layer.

**Author:** Howard (Haochen) Lian — Northwestern University
**Program:** IDX Exchange Internship 2026 — Agentic AI Engineer track

## Project Objectives

Build an end-to-end agentic assistant over real MLS property data (`rets_property`, `california_sold`) that can:

- Understand natural-language property queries (intent recognition + structured output)
- Search and filter listings, and run market analytics
- Generate semantic search results using OpenAI embeddings
- Recommend listings via a recommendation engine
- Answer questions over a knowledge base using RAG
- Communicate with users over WhatsApp and email
- Coordinate all of the above through a multi-agent orchestrator

**Capstone:** a live WhatsApp demo of the full assistant.

## How to Run

```bash
git clone https://github.com/haochenlian/real-estate-assistant-IDX.git
cd real-estate-assistant-IDX
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Data

Uses MLS data (`rets_property`, `california_sold`) accessed via the program's FTP server.
Raw CSV / SQL / source data files are **not** committed to this repo (see `.gitignore`).

## Status

🚧 Early development — project setup in progress.
