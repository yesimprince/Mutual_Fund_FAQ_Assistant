# Mutual Fund FAQ Assistant — Project Context

## 1. What is this project?

A **facts-only FAQ assistant** for mutual fund schemes, built with **Groww** as the reference product context. It uses a **Retrieval-Augmented Generation (RAG)** architecture to answer objective, verifiable queries by pulling information exclusively from official public sources (AMC websites, AMFI, SEBI).

> **Core principle:** Accuracy over intelligence — no investment advice, opinions, or recommendations.

---

## 2. Target Users

| User Segment | Use Case |
|---|---|
| **Retail investors** | Comparing mutual fund schemes on factual parameters |
| **Customer support / content teams** | Handling repetitive, factual mutual fund queries |

---

## 3. Data & Corpus

- **AMC:** HDFC Mutual Fund (HDFC Asset Management Company)
- **Scheme coverage:** 5 schemes across diverse categories (Direct Plan – Growth)

### Selected Schemes

| # | Scheme | Category | Groww URL |
|---|--------|----------|-----------|
| 1 | HDFC Large Cap Fund | Large Cap | [Link](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) |
| 2 | HDFC Mid Cap Fund | Mid Cap | [Link](https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth) |
| 3 | HDFC Small Cap Fund | Small Cap | [Link](https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth) |
| 4 | HDFC Gold ETF Fund of Fund | Gold (Commodity) | [Link](https://groww.in/mutual-funds/hdfc-gold-etf-fund-of-fund-direct-plan-growth) |
| 5 | HDFC Silver ETF FoF | Silver (Commodity) | [Link](https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth) |

### Source Documents

**Corpus URLs (collected — 5/15-25):**

| # | Source URL | Type |
|---|-----------|------|
| 1 | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth | Scheme page |
| 2 | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth | Scheme page |
| 3 | https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth | Scheme page |
| 4 | https://groww.in/mutual-funds/hdfc-gold-etf-fund-of-fund-direct-plan-growth | Scheme page |
| 5 | https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth | Scheme page |

**Additional sources to collect (to reach 15–25 URLs):**

- Scheme factsheets (from HDFC MF official site)
- KIM (Key Information Memorandum)
- SID (Scheme Information Document)
- AMC FAQ / help pages
- AMFI / SEBI guidance pages
- Statement & tax-document download guides

- **Allowed sources:** Only official public sources — AMC, AMFI, SEBI.
- **Disallowed sources:** Third-party blogs, aggregator websites.

---

## 4. Assistant Behavior

### 4.1 Answerable Queries (Facts-Only)

The assistant handles objective questions such as:

- Expense ratio of a scheme
- Exit load details
- Minimum SIP amount
- ELSS lock-in period
- Riskometer classification
- Benchmark index
- Process to download statements or capital gains reports

### 4.2 Response Format

Every response must:

1. Be **≤ 3 sentences**.
2. Include **exactly one citation link** to the source.
3. End with a footer: `"Last updated from sources: <date>"`.

### 4.3 Refusal Handling

Non-factual or advisory queries (e.g., *"Should I invest in this fund?"*, *"Which fund is better?"*) must be **politely refused** with:

- A clear, courteous message reinforcing the facts-only scope.
- A relevant educational link (e.g., AMFI or SEBI resource).

---

## 5. User Interface (Minimal)

- Welcome message on load.
- Three example questions to guide the user.
- Persistent disclaimer: **"Facts-only. No investment advice."**

---

## 6. Privacy & Security Constraints

The system must **never** collect, store, or process:

- PAN or Aadhaar numbers
- Account numbers
- OTPs
- Email addresses or phone numbers

---

## 7. Content Restrictions

| Rule | Detail |
|---|---|
| No investment advice | No recommendations or opinions |
| No performance comparisons | No return calculations or fund-vs-fund analysis |
| Performance queries | Respond only with a link to the official factsheet |
| Transparency | Every answer must be short, factual, verifiable, and include a source link + last-updated date |

---

## 8. Expected Deliverables

- **README** — setup instructions, selected AMC & schemes, architecture overview (RAG approach), known limitations.
- **Disclaimer snippet** — `"Facts-only. No investment advice."`

---

## 9. Success Criteria

- [x] Accurate retrieval of factual mutual fund information
- [x] Strict adherence to facts-only responses
- [x] Consistent inclusion of valid source citations
- [x] Proper refusal of advisory queries
- [x] Clean, minimal, and user-friendly interface

---

## 10. Technical Approach (High-Level)

```
User Query → Embedding → Vector Search (Curated Corpus) → Retrieved Chunks → LLM (Constrained Prompt) → Facts-Only Response + Citation
```

**Architecture:** Lightweight RAG pipeline over a curated corpus of official mutual fund documents.

---

*Source: [problemstatement.txt](file:///Users/iamprince/Desktop/Mutual%20Fund%20FAQ%20Assistant%20/docs/problemstatement.txt)*
