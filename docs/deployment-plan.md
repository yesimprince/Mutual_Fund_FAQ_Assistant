# Deployment Plan — Mutual Fund FAQ Assistant

> **Target Platform:** Streamlit Community Cloud (Free Tier)
> **Date:** 17 Jul 2026
> **Status:** Ready for deployment

---

## Table of Contents

1. [Deployment Overview](#1-deployment-overview)
2. [Architecture: Local vs Streamlit Cloud](#2-architecture-local-vs-streamlit-cloud)
3. [Prerequisites](#3-prerequisites)
4. [Step-by-Step Deployment](#4-step-by-step-deployment)
5. [Secrets Configuration](#5-secrets-configuration)
6. [Data Freshness Strategy](#6-data-freshness-strategy)
7. [File Changes Required](#7-file-changes-required)
8. [Post-Deployment Verification](#8-post-deployment-verification)
9. [Troubleshooting](#9-troubleshooting)
10. [Limitations & Considerations](#10-limitations--considerations)

---

## 1. Deployment Overview

The Mutual Fund FAQ Assistant is deployed as a **single Streamlit app** that combines both the backend (RAG pipeline) and frontend (chat UI) into one Python file — `streamlit_app.py`.

### Why Streamlit?

| Feature | FastAPI (Local) | Streamlit Cloud |
|---------|----------------|-----------------|
| **Hosting** | `localhost:8000` | Public URL (free) |
| **Backend** | FastAPI REST API | Direct Python imports |
| **Frontend** | HTML/CSS/JS (`src/ui/`) | Streamlit chat components |
| **Secrets** | `.env` file | Streamlit Secrets Manager |
| **Data Updates** | Manual `git pull` | Automatic (from GitHub) |
| **Setup Required** | Python, pip, uvicorn | None (just deploy) |
| **Cost** | Free (local) | Free (Streamlit Community) |

---

## 2. Architecture: Local vs Streamlit Cloud

### Current Architecture (Local — FastAPI)

```
User Browser
    │
    ▼
FastAPI Server (localhost:8000)
    ├── POST /ask  ─── Guardrails → Classifier → Retriever → Generator (Groq API)
    ├── GET /health
    └── Static Files (src/ui/) ─── HTML/CSS/JS Chat UI
    │
    ▼
Local vectorstore/ (ChromaDB)
```

### Streamlit Cloud Architecture (After Deployment)

```
User Browser
    │
    ▼
Streamlit Cloud (streamlit_app.py)
    ├── st.chat_input()  ─── Guardrails → Classifier → Retriever → Generator (Groq API)
    ├── st.chat_message() ─── Renders responses with citations
    └── st.sidebar ─── Rate limits, quick-ask chips, disclaimer
    │
    ▼
GitHub Repo vectorstore/ (ChromaDB, updated daily by GitHub Actions)
```

### Data Flow: How Fresh Data Reaches Streamlit Cloud

```
┌──────────────────────────────────────────────────────────┐
│                    GitHub Actions                         │
│  (Runs daily at 10:30 AM IST / 05:00 UTC)               │
│                                                          │
│  1. Scrape Groww pages (5 HDFC schemes)                  │
│  2. Parse → Chunk → Embed (BGE-small)                    │
│  3. Store in ChromaDB (vectorstore/)                     │
│  4. git commit & push updated vectorstore/ and data/     │
└──────────────────┬───────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────┐
│              GitHub Repository (main branch)              │
│                                                          │
│  vectorstore/  ← Updated daily by Actions bot            │
│  data/         ← Updated daily by Actions bot            │
│  streamlit_app.py  ← Streamlit entry point               │
└──────────────────┬───────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────┐
│           Streamlit Community Cloud                       │
│                                                          │
│  • Auto-deploys from GitHub main branch                  │
│  • Reads vectorstore/ directly from repo                 │
│  • Uses Streamlit Secrets for GROQ_API_KEY               │
│  • Public URL: https://<app-name>.streamlit.app          │
└──────────────────────────────────────────────────────────┘
```

---

## 3. Prerequisites

Before deploying, ensure you have:

- [x] **GitHub account** — Repository: `yesimprince/Mutual_Fund_FAQ_Assistant`
- [x] **Groq API key** — Free tier from [console.groq.com](https://console.groq.com)
- [x] **Streamlit account** — Sign up at [share.streamlit.io](https://share.streamlit.io) (use GitHub login)
- [x] **`streamlit` in requirements.txt** — Already present (`streamlit>=1.30.0`)
- [x] **`vectorstore/` committed to repo** — Done via GitHub Actions (`git add -f`)

---

## 4. Step-by-Step Deployment

### Step 1: Create `streamlit_app.py`

Create a `streamlit_app.py` file at the **root** of the repository. This file:

- Imports the existing RAG pipeline modules directly (no HTTP calls)
- Uses `st.chat_message` and `st.chat_input` for the chat interface
- Manages chat history via `st.session_state`
- Displays rate limit status and quick-ask buttons in `st.sidebar`

> **Note:** The file must be named `streamlit_app.py` and placed at the repo root for Streamlit Cloud auto-detection.

### Step 2: Create `.streamlit/config.toml`

Create a Streamlit configuration file for dark theme:

```toml
[theme]
primaryColor = "#7c3aed"
backgroundColor = "#0a0e1a"
secondaryBackgroundColor = "#131830"
textColor = "#e2e8f0"
font = "sans serif"

[server]
headless = true
```

### Step 3: Update `.gitignore`

Add the local secrets file to `.gitignore`:

```gitignore
# Streamlit local secrets (contains API keys)
.streamlit/secrets.toml
```

### Step 4: Create Local Secrets (for testing)

Create `.streamlit/secrets.toml` locally (this file is gitignored):

```toml
GROQ_API_KEY = "gsk_your_groq_api_key_here"
```

### Step 5: Test Locally

```bash
cd "Mutual Fund FAQ Assistant"
streamlit run streamlit_app.py
```

Verify:
- App opens at `http://localhost:8501`
- Chat works with all query types (factual, advisory, PII)
- Rate limit status displays in sidebar
- Quick-ask chips work

### Step 6: Commit & Push

```bash
git add streamlit_app.py .streamlit/config.toml .gitignore
git commit -m "feat: add Streamlit app for cloud deployment"
git push origin main
```

### Step 7: Deploy to Streamlit Community Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)**
2. Click **"New app"**
3. Fill in:
   - **Repository:** `yesimprince/Mutual_Fund_FAQ_Assistant`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
4. Click **"Advanced settings"** → **"Secrets"**
5. Paste your Groq API key (see [Section 5](#5-secrets-configuration))
6. Click **"Deploy!"**

Your app will be live at: `https://<app-name>.streamlit.app`

---

## 5. Secrets Configuration

### On Streamlit Community Cloud

In the Streamlit Cloud dashboard → Your App → **Settings** → **Secrets**, paste:

```toml
GROQ_API_KEY = "gsk_your_actual_groq_api_key_here"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
GROQ_MODEL = "llama-3.3-70b-versatile"
VECTOR_STORE_PATH = "./vectorstore"
```

### How Secrets Are Accessed

The `streamlit_app.py` file reads secrets using:

```python
import streamlit as st
import os

# Streamlit secrets override .env for cloud deployment
if hasattr(st, "secrets"):
    os.environ["GROQ_API_KEY"] = st.secrets.get("GROQ_API_KEY", "")
```

This ensures the existing pipeline code (which reads `os.getenv("GROQ_API_KEY")`) works without modification in both local and cloud environments.

---

## 6. Data Freshness Strategy

### How Data Stays Fresh

| Component | Mechanism | Frequency |
|-----------|-----------|-----------|
| **Scraping** | GitHub Actions (`daily-ingestion.yml`) | Daily at 10:30 AM IST |
| **Vectorstore update** | `git add -f vectorstore/` + push | After each ingestion |
| **Streamlit Cloud refresh** | Auto-pulls from `main` branch | On each GitHub push |
| **Staleness check** | GitHub Actions (`staleness-check.yml`) | Every 6 hours |

### Timeline of a Daily Update

```
05:00 UTC  →  GitHub Actions triggers daily ingestion
05:00 UTC  →  Scrape 5 Groww pages
05:01 UTC  →  Parse → Chunk → Embed → Store in ChromaDB
05:02 UTC  →  git commit & push updated vectorstore/
05:02 UTC  →  Streamlit Cloud detects push → redeploys app
05:03 UTC  →  Users see fresh data (new "Last updated" date)
```

### Important Note

> After each GitHub Actions push, Streamlit Cloud automatically picks up the new code and data. There may be a brief (~1-2 minute) reboot period during redeployment. Users hitting the app during this window will see a "Please wait..." spinner.

---

## 7. File Changes Required

| Action | File | Purpose |
|--------|------|---------|
| **CREATE** | `streamlit_app.py` | Main Streamlit app (replaces FastAPI + HTML UI) |
| **CREATE** | `.streamlit/config.toml` | Dark theme and server config |
| **MODIFY** | `.gitignore` | Add `.streamlit/secrets.toml` |
| **CREATE** | `.streamlit/secrets.toml` | Local-only secrets (gitignored) |

> **No existing files are modified or deleted.** The FastAPI backend (`src/api/`) and HTML frontend (`src/ui/`) remain intact for local development.

---

## 8. Post-Deployment Verification

### Checklist

- [ ] App loads at `https://<app-name>.streamlit.app`
- [ ] Dark theme renders correctly
- [ ] Factual query returns answer with citation and "Last updated" date
- [ ] Advisory query shows polite refusal (no Groq API call)
- [ ] PII query shows security block (no Groq API call)
- [ ] Quick-ask chip buttons in sidebar work
- [ ] Rate limit status displays in sidebar
- [ ] "Last updated" date shows today's date (after ingestion)
- [ ] Chat history persists within a session

### Test Queries

| Query | Expected Result |
|-------|----------------|
| "What is the expense ratio of HDFC Large Cap Fund?" | ✅ Factual answer with 1.04% |
| "Should I invest in HDFC Mid Cap Fund?" | ⚠️ Advisory refused |
| "My PAN is ABCDE1234F" | 🛑 PII blocked |
| "What is the minimum SIP for HDFC Small Cap Fund?" | ✅ Factual answer with ₹100 |

---

## 9. Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **"ModuleNotFoundError: src"** | Streamlit can't find project modules | Ensure `streamlit_app.py` is at repo root and adds project root to `sys.path` |
| **"GROQ_API_KEY not set"** | Missing secret on Streamlit Cloud | Add key in Settings → Secrets |
| **"No module named chromadb"** | Missing dependency | Verify `chromadb` is in `requirements.txt` |
| **App shows stale data** | GitHub Actions hasn't run yet | Manually trigger workflow or wait for scheduled run |
| **Rate limit errors** | Too many public users | Monitor usage; consider adding authentication |
| **App crashes on boot** | Embedding model download timeout | Streamlit Cloud has limited boot time; the BGE-small model (33MB) should load fine |

### Logs

- **Streamlit Cloud logs:** App dashboard → "Manage app" (bottom-right) → "Logs"
- **GitHub Actions logs:** Repository → Actions tab → Select workflow run

---

## 10. Limitations & Considerations

### Streamlit Community Cloud Limits

| Resource | Limit |
|----------|-------|
| **Apps per account** | Unlimited (public repos) |
| **Memory** | 1 GB RAM |
| **Storage** | Included via GitHub repo |
| **Uptime** | App sleeps after inactivity; wakes on visit (~30s cold start) |
| **Custom domain** | Not supported (free tier) |

### Security Considerations

- **Public Access:** Anyone with the Streamlit URL can query the app
- **API Key Safety:** Groq API key is stored in Streamlit Secrets (encrypted, never in code)
- **Rate Limiting:** The existing `GroqRateLimiter` protects against excessive usage (30 RPM, 1000 RPD)
- **PII Protection:** Input guardrails block PAN, Aadhaar, phone, and email before any processing

### What Stays the Same

- ✅ All existing Python pipeline code (`src/`) — unchanged
- ✅ FastAPI backend (`src/api/`) — still works for local development
- ✅ HTML/JS frontend (`src/ui/`) — still works with FastAPI locally
- ✅ GitHub Actions workflows — continue running daily
- ✅ Tests — continue to pass

---

## Summary

| Aspect | Detail |
|--------|--------|
| **Platform** | Streamlit Community Cloud (free) |
| **Entry Point** | `streamlit_app.py` (repo root) |
| **Backend** | Direct Python imports from `src/` pipeline |
| **Frontend** | Streamlit `st.chat_message` + custom dark CSS |
| **Secrets** | Streamlit Secrets Manager (GROQ_API_KEY) |
| **Data Freshness** | GitHub Actions → push to main → auto-redeploy |
| **URL** | `https://<app-name>.streamlit.app` |
| **Cost** | **$0** |
