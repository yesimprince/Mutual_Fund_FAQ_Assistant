"""
Streamlit App — HDFC Mutual Fund FAQ Assistant

A premium dark-themed chat interface for the Mutual Fund FAQ Assistant,
powered by the same RAG pipeline (guardrails → classify → retrieve → generate)
used by the FastAPI backend. Designed for deployment on Streamlit Community Cloud.

Usage:
    Local:   streamlit run streamlit_app.py
    Cloud:   Deploy via share.streamlit.io (auto-detects this file at repo root)
"""

import os
import sys
import re
import time

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so `src.*` imports work
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

# ---------------------------------------------------------------------------
# Streamlit secrets → environment variables (must happen before pipeline imports)
# ---------------------------------------------------------------------------
if hasattr(st, "secrets"):
    for key in ["GROQ_API_KEY", "EMBEDDING_MODEL", "GROQ_MODEL", "VECTOR_STORE_PATH"]:
        val = st.secrets.get(key, "")
        if val:
            os.environ[key] = val

# Load .env as fallback for local development
from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Pipeline imports (after env vars are set)
# ---------------------------------------------------------------------------
from src.pipeline.guardrails import apply_input_guardrails
from src.pipeline.query_classifier import classify
from src.pipeline.generator import generate_response, generate_refusal, generate_pii_block
from src.pipeline.retriever import retrieve
from src.pipeline.rate_limiter import get_rate_limiter

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="HDFC Mutual Fund FAQ Assistant",
    page_icon="🏦",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — premium dark theme matching the existing UI
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* Root variables */
    :root {
        --bg-primary: #0a0e1a;
        --bg-secondary: #131830;
        --bg-card: #1a2040;
        --text-primary: #e2e8f0;
        --text-secondary: #94a3b8;
        --accent-purple: #7c3aed;
        --accent-purple-light: #a78bfa;
        --accent-green: #10b981;
        --accent-amber: #f59e0b;
        --accent-red: #ef4444;
        --border-color: #1e293b;
        --gradient-purple: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
        --gradient-card: linear-gradient(135deg, #1a2040 0%, #131830 100%);
    }

    /* Global font */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] {
        background: var(--bg-primary) !important;
        border-bottom: 1px solid var(--border-color);
    }

    /* Main app background */
    .stApp {
        background: var(--bg-primary) !important;
    }

    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: var(--bg-secondary) !important;
        border-right: 1px solid var(--border-color);
    }

    section[data-testid="stSidebar"] .stMarkdown {
        color: var(--text-primary);
    }

    /* Chat message styling */
    .stChatMessage {
        background: transparent !important;
        border: none !important;
        padding: 0.5rem 0 !important;
    }

    /* User messages */
    .stChatMessage[data-testid="stChatMessage-user"] {
        background: transparent !important;
    }

    .stChatMessage[data-testid="stChatMessage-user"] > div {
        background: var(--gradient-purple) !important;
        border-radius: 18px 18px 4px 18px !important;
        padding: 12px 18px !important;
        color: white !important;
    }

    /* Assistant messages */
    .stChatMessage[data-testid="stChatMessage-assistant"] > div {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 18px 18px 18px 4px !important;
        padding: 12px 18px !important;
        color: var(--text-primary) !important;
    }

    /* Chat input */
    .stChatInput {
        border-color: var(--border-color) !important;
    }

    .stChatInput > div {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
    }

    .stChatInput textarea {
        color: var(--text-primary) !important;
    }

    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.025em;
        margin-bottom: 8px;
    }

    .badge-success {
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }

    .badge-refused {
        background: rgba(245, 158, 11, 0.15);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.3);
    }

    .badge-blocked {
        background: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    .badge-rate-limited {
        background: rgba(245, 158, 11, 0.15);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.3);
    }

    .badge-error {
        background: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    /* Citation link */
    .citation-box {
        background: rgba(124, 58, 237, 0.08);
        border: 1px solid rgba(124, 58, 237, 0.2);
        border-radius: 10px;
        padding: 8px 14px;
        margin-top: 10px;
        font-size: 0.85rem;
    }

    .citation-box a {
        color: var(--accent-purple-light) !important;
        text-decoration: none !important;
    }

    .citation-box a:hover {
        text-decoration: underline !important;
    }

    .updated-tag {
        color: var(--text-secondary);
        font-size: 0.8rem;
        margin-left: 12px;
    }

    /* Sidebar quick-ask buttons */
    .stButton > button {
        background: var(--bg-card) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 10px !important;
        padding: 8px 14px !important;
        font-size: 0.85rem !important;
        text-align: left !important;
        width: 100% !important;
        transition: all 0.2s ease !important;
    }

    .stButton > button:hover {
        background: rgba(124, 58, 237, 0.15) !important;
        border-color: var(--accent-purple) !important;
        transform: translateY(-1px) !important;
    }

    /* Sidebar rate limit metric */
    .rate-metric {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 10px;
        padding: 12px 16px;
        text-align: center;
    }

    .rate-metric .value {
        font-size: 1.4rem;
        font-weight: 700;
        color: var(--accent-green);
    }

    .rate-metric .label {
        font-size: 0.75rem;
        color: var(--text-secondary);
        margin-top: 2px;
    }

    /* Disclaimer banner */
    .disclaimer-banner {
        background: rgba(245, 158, 11, 0.08);
        border: 1px solid rgba(245, 158, 11, 0.2);
        border-radius: 8px;
        padding: 8px 14px;
        text-align: center;
        font-size: 0.8rem;
        color: #f59e0b;
        margin-bottom: 16px;
    }

    /* Welcome card */
    .welcome-card {
        background: var(--gradient-card);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 28px;
        text-align: center;
        margin: 40px auto;
        max-width: 500px;
    }

    .welcome-card .icon {
        font-size: 2.5rem;
        margin-bottom: 12px;
    }

    .welcome-card .text {
        color: var(--text-secondary);
        font-size: 0.95rem;
        line-height: 1.6;
    }

    .welcome-card .text strong {
        color: var(--text-primary);
    }

    /* Divider */
    hr {
        border-color: var(--border-color) !important;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_status_badge(status: str) -> str:
    """Return an HTML badge for the response status."""
    badges = {
        "success":      ("✅ Factual Answer", "badge-success"),
        "refused":      ("⚠️ Advisory Refused", "badge-refused"),
        "blocked":      ("🛑 PII Blocked", "badge-blocked"),
        "rate_limited": ("⏳ Rate Limited", "badge-rate-limited"),
        "error":        ("❌ Error", "badge-error"),
    }
    label, css_class = badges.get(status, ("🤖 Response", "badge-success"))
    return f'<span class="status-badge {css_class}">{label}</span>'


def format_citation(source: str, last_updated: str, answer: str) -> str:
    """Build the citation HTML box shown below an answer."""
    # Extract date from answer footer if not provided
    footer_date = last_updated
    match = re.search(r"Last updated from sources:\s*(.+)", answer, re.IGNORECASE)
    if match and (not footer_date or footer_date == "Unknown"):
        footer_date = match.group(1).strip()

    parts = []
    if source:
        display_url = source
        if len(display_url) > 50:
            display_url = display_url[:47] + "..."
        parts.append(f'📎 <a href="{source}" target="_blank">{display_url}</a>')
    if footer_date and footer_date != "Unknown":
        parts.append(f'<span class="updated-tag">🕐 Updated: {footer_date}</span>')

    if parts:
        return f'<div class="citation-box">{"&nbsp;&nbsp;•&nbsp;&nbsp;".join(parts)}</div>'
    return ""


def clean_answer(answer: str) -> str:
    """Strip the 'Last updated from sources:' footer from the answer text."""
    return re.sub(r"\n?\n?Last updated from sources:\s*.+", "", answer, flags=re.IGNORECASE).strip()


def process_query(query: str) -> dict:
    """
    Run the full RAG pipeline on a user query.

    Flow: Input guardrails → Classify → Route → Generate response
    Returns a dict with status, answer, source, last_updated, query_type.
    """
    # Step 1: Input guardrails
    sanitized_query, guardrail_error = apply_input_guardrails(query)

    if guardrail_error:
        return {
            "status": "blocked",
            "answer": guardrail_error,
            "source": None,
            "last_updated": None,
            "query_type": "pii_detected",
        }

    # Step 2: Classify query
    query_type = classify(sanitized_query)

    # Step 3: Route to handler
    if query_type == "advisory":
        return generate_refusal(sanitized_query)

    elif query_type == "pii_detected":
        return generate_pii_block(sanitized_query)

    else:
        # Factual — full RAG pipeline
        try:
            chunks = retrieve(sanitized_query, top_k=3)

            if not chunks:
                return {
                    "status": "success",
                    "answer": (
                        "I don't have this information in my sources. "
                        "Please check https://groww.in/mutual-funds for the latest details."
                    ),
                    "source": "https://groww.in/mutual-funds",
                    "last_updated": None,
                    "query_type": "factual",
                }

            return generate_response(sanitized_query, chunks)

        except Exception as e:
            return {
                "status": "error",
                "answer": "I'm having trouble processing your request right now. Please try again later.",
                "source": None,
                "last_updated": None,
                "query_type": "factual",
            }


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🏦 HDFC MF FAQ Assistant")
    st.markdown("---")

    # Rate limit status
    st.markdown("##### 📊 Rate Limit Status")
    try:
        limiter = get_rate_limiter()
        status = limiter.get_status()
        rpm = status.get("rpm", {})
        rpd = status.get("rpd", {})
        rpm_remaining = rpm.get("remaining", 30)
        rpm_limit = rpm.get("limit", 30)
        rpd_remaining = rpd.get("remaining", 1000)
        rpd_limit = rpd.get("limit", 1000)

        col1, col2 = st.columns(2)
        with col1:
            pct = rpm_remaining / rpm_limit if rpm_limit else 0
            color = "🟢" if pct > 0.3 else ("🟡" if pct > 0.1 else "🔴")
            st.markdown(
                f'<div class="rate-metric">'
                f'<div class="value">{color} {rpm_remaining}/{rpm_limit}</div>'
                f'<div class="label">Requests / min</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f'<div class="rate-metric">'
                f'<div class="value">{rpd_remaining}/{rpd_limit}</div>'
                f'<div class="label">Requests / day</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    except Exception:
        st.caption("Rate limit info unavailable")

    st.markdown("---")

    # Quick-ask chips
    st.markdown("##### ⚡ Quick Ask")
    quick_queries = [
        ("📊 Expense ratio — Large Cap", "What is the expense ratio of HDFC Large Cap Fund?"),
        ("🚪 Exit load — Small Cap", "What is the exit load for HDFC Small Cap Fund?"),
        ("💰 Min SIP — Mid Cap", "What is the minimum SIP amount for HDFC Mid Cap Fund?"),
        ("📈 NAV — Gold ETF FoF", "What is the NAV of HDFC Gold ETF Fund of Fund?"),
        ("🏦 AUM — Silver ETF FoF", "What is the AUM of HDFC Silver ETF FoF?"),
    ]

    for label, q in quick_queries:
        if st.button(label, key=f"chip_{q[:20]}", use_container_width=True):
            st.session_state.pending_query = q

    st.markdown("---")

    # Disclaimer
    st.markdown(
        '<div class="disclaimer-banner">⚠️ Facts only. No investment advice.</div>',
        unsafe_allow_html=True,
    )

    # About
    with st.expander("ℹ️ About this app"):
        st.markdown("""
        **Mutual Fund FAQ Assistant** answers factual questions about
        HDFC mutual fund schemes using a RAG pipeline.

        **Data Sources:** [Groww.in](https://groww.in) scheme pages
        **Schemes Covered:** 5 HDFC funds (Large Cap, Mid Cap, Small Cap, Gold ETF FoF, Silver ETF FoF)
        **LLM:** Groq API (`llama-3.3-70b-versatile`)
        **Embeddings:** BAAI/bge-small-en-v1.5
        **Vector Store:** ChromaDB
        **Data Refresh:** Daily at 10:30 AM IST via GitHub Actions
        """)


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

# Disclaimer banner
st.markdown(
    '<div class="disclaimer-banner">⚠️ Facts only. No investment advice.</div>',
    unsafe_allow_html=True,
)

# Welcome card (shown only when no messages)
if not st.session_state.messages:
    st.markdown("""
    <div class="welcome-card">
        <div class="icon">💬</div>
        <div class="text">
            Welcome! I can help you with <strong>factual information</strong> about
            HDFC mutual fund schemes — expense ratios, exit loads, SIP details, and more.
        </div>
    </div>
    """, unsafe_allow_html=True)

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            # Status badge
            st.markdown(get_status_badge(msg.get("status", "success")), unsafe_allow_html=True)
            # Answer text
            st.markdown(clean_answer(msg["content"]))
            # Citation
            citation_html = format_citation(
                msg.get("source", ""),
                msg.get("last_updated", ""),
                msg["content"],
            )
            if citation_html:
                st.markdown(citation_html, unsafe_allow_html=True)
        else:
            st.markdown(msg["content"])


# ---------------------------------------------------------------------------
# Handle input (chat input or quick-ask chip)
# ---------------------------------------------------------------------------
prompt = st.chat_input("Ask about any HDFC mutual fund scheme...", max_chars=500)

# Check for pending query from sidebar chip
if "pending_query" in st.session_state:
    prompt = st.session_state.pending_query
    del st.session_state.pending_query

if prompt:
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            start = time.time()
            result = process_query(prompt)
            elapsed = time.time() - start

        status = result.get("status", "error")
        answer = result.get("answer", "")
        source = result.get("source")
        last_updated = result.get("last_updated")

        # Status badge
        st.markdown(get_status_badge(status), unsafe_allow_html=True)

        # Answer text
        st.markdown(clean_answer(answer))

        # Citation
        citation_html = format_citation(source or "", last_updated or "", answer)
        if citation_html:
            st.markdown(citation_html, unsafe_allow_html=True)

        # Save assistant message to history
        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "status": status,
            "source": source,
            "last_updated": last_updated,
            "query_type": result.get("query_type", "factual"),
        })

    # Force rerun to update sidebar rate limits
    st.rerun()
