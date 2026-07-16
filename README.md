# Mutual Fund FAQ Assistant

A facts-only FAQ assistant for HDFC Mutual Fund schemes, built using a Retrieval-Augmented Generation (RAG) architecture. The assistant answers objective, verifiable queries by retrieving information exclusively from official Groww scheme pages.

> **Disclaimer:** Facts-only. No investment advice.

---

## Selected AMC & Schemes

| # | Scheme | Category |
|---|--------|----------|
| 1 | HDFC Large Cap Fund (Direct – Growth) | Large Cap |
| 2 | HDFC Mid Cap Fund (Direct – Growth) | Mid Cap |
| 3 | HDFC Small Cap Fund (Direct – Growth) | Small Cap |
| 4 | HDFC Gold ETF Fund of Fund (Direct – Growth) | Gold (Commodity) |
| 5 | HDFC Silver ETF FoF (Direct – Growth) | Silver (Commodity) |

---

## Architecture Overview

```
User Query → Input Guardrails → Query Classifier → [Factual / Advisory / PII]
  → (Factual) BGE Embedding → ChromaDB Vector Search → Top-3 Chunks
  → Rate Limiter → Groq LLM (llama-3.3-70b-versatile) → Output Guardrails
  → Facts-Only Response + Citation + Footer
```

**Key Components:**

| Component | Technology | Details |
|-----------|-----------|---------|
| **Embedding** | BAAI/bge-small-en-v1.5 | 384-dim, instruction-prefixed queries |
| **Vector Store** | ChromaDB | Local persistent, 55 chunks, L2 distance |
| **LLM** | Groq API | `llama-3.3-70b-versatile` (free tier) |
| **Rate Limiter** | Custom | 30 RPM, 1K RPD, 12K TPM, 100K TPD |
| **Backend** | FastAPI | REST API at `localhost:8000` |
| **Frontend** | HTML/CSS/JS | Premium dark-themed chat UI |

### Groq Free-Tier Rate Limits

| Limit | Value | Strategy |
|-------|-------|----------|
| Requests/min | 30 | Sliding window (60s) |
| Requests/day | 1,000 | Daily counter (UTC midnight reset) |
| Tokens/min | 12,000 | Sliding window (60s) |
| Tokens/day | 100,000 | Daily counter (UTC midnight reset) |

> Advisory and PII queries use **template-based responses** (zero Groq API calls) to conserve rate budget.

---

## Setup Instructions

### 1. Clone & Install

```bash
git clone <repo-url>
cd "Mutual Fund FAQ Assistant"
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 3. Run Data Ingestion

```bash
python3 scripts/ingest.py
```

This runs the full ingestion pipeline: scrape → parse → chunk → embed → store in ChromaDB.

### 4. Start the API

```bash
python3 -m uvicorn src.api.main:app --reload
```

The API will be available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### 5. Launch the Frontend

```bash
# Frontend is served via FastAPI static files (Phase 10)
# Just open http://localhost:8000/ in your browser
```

### 6. Test with curl

```bash
# Factual query
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the expense ratio of HDFC Large Cap Fund?"}'

# Advisory query (refused, no Groq call)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Should I invest in HDFC Mid Cap Fund?"}'

# Health check
curl http://localhost:8000/health

# Rate limit status
curl http://localhost:8000/rate-limit-status
```

### 7. Run Evaluation

```bash
# Start the API first, then in another terminal:
python3 scripts/evaluate.py
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ask` | Submit a query to the FAQ pipeline |
| `GET` | `/health` | Service health check |
| `GET` | `/rate-limit-status` | Current Groq rate limiter usage |
| `GET` | `/docs` | Swagger UI (interactive API docs) |
| `GET` | `/redoc` | ReDoc API documentation |

### POST /ask — Request

```json
{
  "query": "What is the expense ratio of HDFC Large Cap Fund?"
}
```

### POST /ask — Response

```json
{
  "status": "success",
  "answer": "The Expense Ratio of HDFC Large Cap Fund Direct Growth is 1.04% as of 10 Jul 2026. Source: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth. Last updated from sources: 10 Jul 2026",
  "source": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
  "last_updated": "10 Jul 2026",
  "query_type": "factual"
}
```

| `status` Value | Meaning | Groq API Call? |
|----------------|---------|----------------|
| `success` | Factual answer generated | ✅ Yes |
| `refused` | Advisory query politely refused | ❌ No |
| `blocked` | PII detected, query blocked | ❌ No |
| `rate_limited` | Groq rate limit hit | ❌ No |
| `error` | Internal error | ❌ No |

---

## Project Structure

```
├── docs/                   # Documentation (architecture, implementation plan)
├── data/
│   ├── raw/                # Scraped HTML from Groww (5 files)
│   ├── processed/          # Parsed clean text + metadata (5 JSON files)
│   └── chunks/             # Chunked documents (5 JSONL files)
├── vectorstore/            # ChromaDB persistent index (55 chunks)
├── src/
│   ├── ingestion/          # Scraping, parsing, chunking, embedding, vectorstore
│   ├── retrieval/          # Retriever (L2→cosine, threshold 0.55), reranker
│   ├── pipeline/           # Query classifier, rate limiter, guardrails, generator
│   ├── prompts/            # System & refusal prompt templates
│   ├── api/                # FastAPI backend (main.py, models.py)
│   └── ui/                 # Frontend (HTML/CSS/JS — Phase 10)
├── tests/                  # Unit & integration tests
├── scripts/                # Ingestion, evaluation, and testing runners
├── requirements.txt
├── .env.example
└── README.md
```

---

## Known Limitations

- Data sourced only from 5 Groww scheme pages (HTML scraping)
- Responses may become stale if source pages update — check the "Last updated" footer
- English language only
- No conversational memory (each query is independent)
- No user authentication
- Groq free-tier rate limits may throttle heavy usage (~10–15 RAG requests/minute max)

---

## Disclaimer

> **Facts-only. No investment advice.**
>
> This assistant provides factual information from official public sources only. It does not provide investment advice, opinions, or recommendations. Always verify information from official AMC/AMFI/SEBI sources before making any financial decisions.
# -Mutual_Fund_FAQ-_Assistant
