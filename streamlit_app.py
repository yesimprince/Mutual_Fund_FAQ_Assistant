"""
Streamlit App — HDFC Mutual Fund FAQ Assistant

A Groww-inspired chat interface for the Mutual Fund FAQ Assistant,
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
import base64

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
    page_title="Mutual Fund FAQ Assistant — Powered by Groww Data",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Load logo as base64 for inline rendering
# ---------------------------------------------------------------------------
@st.cache_data
def get_logo_base64():
    """Load the Groww logo and return as base64 string."""
    logo_path = os.path.join(PROJECT_ROOT, "assets", "groww_logo.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


LOGO_B64 = get_logo_base64()


# ---------------------------------------------------------------------------
# Custom CSS — Groww-inspired design system
#
# Groww Design Language:
#   Primary Blue: #5367FF (trust, security)
#   Success Green: #00D09C (profit, positive)
#   Error Red: #EB5B3C (loss, negative)
#   Dark BG: #0D0D0D / #121212
#   Card BG: #1E1E2D
#   Text Primary: #FFFFFF
#   Text Secondary: #9B9B9B
#   Font: Inter
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* ===== Google Fonts ===== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* ===== Groww Design Tokens ===== */
    :root {
        --groww-blue: #5367FF;
        --groww-blue-light: #7B8CFF;
        --groww-blue-dark: #3D4FCC;
        --groww-green: #00D09C;
        --groww-green-bg: rgba(0, 208, 156, 0.1);
        --groww-green-border: rgba(0, 208, 156, 0.25);
        --groww-red: #EB5B3C;
        --groww-red-bg: rgba(235, 91, 60, 0.1);
        --groww-red-border: rgba(235, 91, 60, 0.25);
        --groww-amber: #FFB800;
        --groww-amber-bg: rgba(255, 184, 0, 0.1);
        --groww-amber-border: rgba(255, 184, 0, 0.25);
        --bg-primary: #0D0D0D;
        --bg-secondary: #121212;
        --bg-card: #1E1E2D;
        --bg-card-hover: #252540;
        --bg-elevated: #2A2A3C;
        --text-primary: #FFFFFF;
        --text-secondary: #9B9B9B;
        --text-muted: #6B6B6B;
        --border-default: #2A2A3C;
        --border-subtle: #1E1E2D;
    }

    /* ===== Global Reset ===== */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    /* ===== Hide Streamlit Chrome ===== */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] {
        background: var(--bg-primary) !important;
        border-bottom: 1px solid var(--border-default);
    }

    /* ===== App Background ===== */
    .stApp {
        background: var(--bg-primary) !important;
    }

    /* ===== Sidebar — Groww Dark Nav ===== */
    section[data-testid="stSidebar"] {
        background: var(--bg-secondary) !important;
        border-right: 1px solid var(--border-default);
    }

    section[data-testid="stSidebar"] .stMarkdown {
        color: var(--text-primary);
    }

    section[data-testid="stSidebar"] hr {
        border-color: var(--border-default) !important;
        margin: 12px 0;
    }

    /* ===== Groww Logo Header ===== */
    .groww-header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 4px 0 8px 0;
    }

    .groww-header img {
        height: 36px;
        width: auto;
    }

    .groww-header .title {
        font-size: 0.85rem;
        font-weight: 600;
        color: var(--text-primary);
        letter-spacing: -0.01em;
        line-height: 1.3;
    }

    .groww-header .subtitle {
        font-size: 0.7rem;
        font-weight: 400;
        color: var(--text-secondary);
        margin-top: 1px;
    }

    /* ===== Metric Cards — Groww Style ===== */
    .metric-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
    }

    .metric-card {
        background: var(--bg-card);
        border: 1px solid var(--border-default);
        border-radius: 12px;
        padding: 14px 12px;
        text-align: center;
        transition: background 0.2s ease;
    }

    .metric-card:hover {
        background: var(--bg-card-hover);
    }

    .metric-card .metric-value {
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--groww-green);
        letter-spacing: -0.02em;
    }

    .metric-card .metric-value.warning {
        color: var(--groww-amber);
    }

    .metric-card .metric-value.danger {
        color: var(--groww-red);
    }

    .metric-card .metric-label {
        font-size: 0.68rem;
        font-weight: 500;
        color: var(--text-muted);
        margin-top: 4px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    /* ===== Section Labels ===== */
    .section-label {
        font-size: 0.72rem;
        font-weight: 600;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin: 16px 0 8px 0;
    }

    /* ===== Quick Ask Chips — Groww Button Style ===== */
    .stButton > button {
        background: var(--bg-card) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-default) !important;
        border-radius: 10px !important;
        padding: 10px 14px !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        text-align: left !important;
        width: 100% !important;
        transition: all 0.2s ease !important;
        letter-spacing: -0.01em !important;
    }

    .stButton > button:hover {
        background: var(--bg-card-hover) !important;
        border-color: var(--groww-blue) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(83, 103, 255, 0.15) !important;
    }

    .stButton > button:active {
        transform: translateY(0) !important;
    }

    /* ===== Chat Messages — Groww Card Style ===== */
    .stChatMessage {
        background: transparent !important;
        border: none !important;
        padding: 0.4rem 0 !important;
    }

    /* User bubble — Groww Blue */
    .stChatMessage[data-testid="stChatMessage-user"] > div {
        background: linear-gradient(135deg, #5367FF 0%, #3D4FCC 100%) !important;
        border-radius: 16px 16px 4px 16px !important;
        padding: 14px 18px !important;
        color: white !important;
        font-size: 0.92rem !important;
        line-height: 1.5 !important;
        box-shadow: 0 2px 8px rgba(83, 103, 255, 0.2) !important;
    }

    /* Assistant bubble — Dark card */
    .stChatMessage[data-testid="stChatMessage-assistant"] > div {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-default) !important;
        border-radius: 16px 16px 16px 4px !important;
        padding: 14px 18px !important;
        color: var(--text-primary) !important;
        font-size: 0.92rem !important;
        line-height: 1.6 !important;
    }

    /* ===== Chat Input — Clean Groww Style ===== */
    .stChatInput > div {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border-default) !important;
        border-radius: 12px !important;
        transition: border-color 0.2s ease !important;
    }

    .stChatInput > div:focus-within {
        border-color: var(--groww-blue) !important;
        box-shadow: 0 0 0 3px rgba(83, 103, 255, 0.1) !important;
    }

    .stChatInput textarea {
        color: var(--text-primary) !important;
        font-size: 0.9rem !important;
    }

    /* ===== Status Badges ===== */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        margin-bottom: 8px;
    }

    .badge-success {
        background: var(--groww-green-bg);
        color: var(--groww-green);
        border: 1px solid var(--groww-green-border);
    }

    .badge-refused {
        background: var(--groww-amber-bg);
        color: var(--groww-amber);
        border: 1px solid var(--groww-amber-border);
    }

    .badge-blocked {
        background: var(--groww-red-bg);
        color: var(--groww-red);
        border: 1px solid var(--groww-red-border);
    }

    .badge-rate-limited {
        background: var(--groww-amber-bg);
        color: var(--groww-amber);
        border: 1px solid var(--groww-amber-border);
    }

    .badge-error {
        background: var(--groww-red-bg);
        color: var(--groww-red);
        border: 1px solid var(--groww-red-border);
    }

    /* ===== Citation Box — Groww Info Card ===== */
    .citation-box {
        background: rgba(83, 103, 255, 0.06);
        border: 1px solid rgba(83, 103, 255, 0.15);
        border-radius: 10px;
        padding: 10px 14px;
        margin-top: 10px;
        font-size: 0.82rem;
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
    }

    .citation-box a {
        color: var(--groww-blue-light) !important;
        text-decoration: none !important;
        font-weight: 500;
    }

    .citation-box a:hover {
        text-decoration: underline !important;
        color: var(--groww-blue) !important;
    }

    .updated-tag {
        color: var(--text-secondary);
        font-size: 0.78rem;
    }

    /* ===== Disclaimer Banner ===== */
    .disclaimer-banner {
        background: var(--groww-amber-bg);
        border: 1px solid var(--groww-amber-border);
        border-radius: 8px;
        padding: 8px 16px;
        text-align: center;
        font-size: 0.78rem;
        font-weight: 500;
        color: var(--groww-amber);
    }

    /* ===== Welcome Card — Groww Onboarding Style ===== */
    .welcome-card {
        background: var(--bg-card);
        border: 1px solid var(--border-default);
        border-radius: 16px;
        padding: 32px 28px;
        text-align: center;
        margin: 48px auto 24px auto;
        max-width: 480px;
        position: relative;
        overflow: hidden;
    }

    .welcome-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--groww-green), var(--groww-blue));
        border-radius: 16px 16px 0 0;
    }

    .welcome-card .welcome-icon {
        width: 52px;
        height: 52px;
        background: linear-gradient(135deg, var(--groww-blue) 0%, var(--groww-green) 100%);
        border-radius: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.5rem;
        margin: 0 auto 16px auto;
    }

    .welcome-card .welcome-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--text-primary);
        margin-bottom: 8px;
        letter-spacing: -0.02em;
    }

    .welcome-card .welcome-text {
        color: var(--text-secondary);
        font-size: 0.88rem;
        line-height: 1.6;
    }

    .welcome-card .welcome-text strong {
        color: var(--text-primary);
        font-weight: 600;
    }

    /* ===== Schemes Covered Pills ===== */
    .scheme-pills {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        justify-content: center;
        margin-top: 14px;
    }

    .scheme-pill {
        background: var(--bg-elevated);
        border: 1px solid var(--border-default);
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 0.72rem;
        font-weight: 500;
        color: var(--text-secondary);
    }

    /* ===== About Expander ===== */
    .groww-about {
        background: var(--bg-card);
        border: 1px solid var(--border-default);
        border-radius: 10px;
        padding: 14px;
        font-size: 0.82rem;
        color: var(--text-secondary);
        line-height: 1.6;
    }

    .groww-about strong {
        color: var(--text-primary);
    }

    .groww-about .about-row {
        display: flex;
        justify-content: space-between;
        padding: 5px 0;
        border-bottom: 1px solid var(--border-subtle);
    }

    .groww-about .about-row:last-child {
        border-bottom: none;
    }

    .groww-about .about-key {
        color: var(--text-muted);
        font-size: 0.78rem;
    }

    .groww-about .about-val {
        color: var(--text-primary);
        font-weight: 500;
        font-size: 0.78rem;
    }

    /* ===== Scrollbar — Subtle ===== */
    ::-webkit-scrollbar {
        width: 6px;
    }

    ::-webkit-scrollbar-track {
        background: transparent;
    }

    ::-webkit-scrollbar-thumb {
        background: var(--border-default);
        border-radius: 3px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: var(--text-muted);
    }

    /* ===== Dividers ===== */
    hr {
        border-color: var(--border-default) !important;
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
        return f'<div class="citation-box">{"&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts)}</div>'
    return ""


def clean_answer(answer: str) -> str:
    """Strip the 'Last updated from sources:' footer from the answer text."""
    return re.sub(r"\n?\n?Last updated from sources:\s*.+", "", answer, flags=re.IGNORECASE).strip()


def process_query(query: str) -> dict:
    """
    Run the full RAG pipeline on a user query.

    Flow: Input guardrails → Classify → Route → Generate response
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
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "answer": f"I'm having trouble processing your request right now. Error: {str(e)}",
                "source": None,
                "last_updated": None,
                "query_type": "factual",
            }


# ---------------------------------------------------------------------------
# Sidebar — Groww-style navigation panel
# ---------------------------------------------------------------------------
with st.sidebar:
    # Groww Logo + App Title
    if LOGO_B64:
        st.markdown(f"""
        <div class="groww-header">
            <img src="data:image/png;base64,{LOGO_B64}" alt="Groww Logo">
            <div>
                <div class="title">Mutual Fund FAQ</div>
                <div class="subtitle">Powered by Groww Data</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("### 📈 Mutual Fund FAQ Assistant")

    st.markdown("---")

    # Rate Limit Status
    st.markdown('<div class="section-label">📊 API Status</div>', unsafe_allow_html=True)
    try:
        limiter = get_rate_limiter()
        status = limiter.get_status()
        rpm = status.get("rpm", {})
        rpd = status.get("rpd", {})
        rpm_remaining = rpm.get("remaining", 30)
        rpm_limit = rpm.get("limit", 30)
        rpd_remaining = rpd.get("remaining", 1000)
        rpd_limit = rpd.get("limit", 1000)

        # Determine color class based on usage
        rpm_pct = rpm_remaining / rpm_limit if rpm_limit else 0
        rpm_color = "" if rpm_pct > 0.3 else (" warning" if rpm_pct > 0.1 else " danger")

        rpd_pct = rpd_remaining / rpd_limit if rpd_limit else 0
        rpd_color = "" if rpd_pct > 0.3 else (" warning" if rpd_pct > 0.1 else " danger")

        st.markdown(f"""
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-value{rpm_color}">{rpm_remaining}/{rpm_limit}</div>
                <div class="metric-label">Req / Min</div>
            </div>
            <div class="metric-card">
                <div class="metric-value{rpd_color}">{rpd_remaining}/{rpd_limit}</div>
                <div class="metric-label">Req / Day</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.caption("Rate limit info unavailable")

    st.markdown("---")

    # Quick Ask
    st.markdown('<div class="section-label">⚡ Quick Ask</div>', unsafe_allow_html=True)
    quick_queries = [
        ("📊 Expense Ratio — Large Cap", "What is the expense ratio of HDFC Large Cap Fund?"),
        ("🚪 Exit Load — Small Cap", "What is the exit load for HDFC Small Cap Fund?"),
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

    st.markdown("")

    # About Section
    with st.expander("ℹ️ About"):
        st.markdown("""
        <div class="groww-about">
            <div class="about-row">
                <span class="about-key">Data Source</span>
                <span class="about-val">Groww.in</span>
            </div>
            <div class="about-row">
                <span class="about-key">Schemes</span>
                <span class="about-val">5 HDFC Funds</span>
            </div>
            <div class="about-row">
                <span class="about-key">LLM</span>
                <span class="about-val">Llama 3.3 70B</span>
            </div>
            <div class="about-row">
                <span class="about-key">Embeddings</span>
                <span class="about-val">BGE-small-en</span>
            </div>
            <div class="about-row">
                <span class="about-key">Vector Store</span>
                <span class="about-val">ChromaDB</span>
            </div>
            <div class="about-row">
                <span class="about-key">Data Refresh</span>
                <span class="about-val">Daily 10:30 AM IST</span>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

# Disclaimer
st.markdown(
    '<div class="disclaimer-banner">⚠️ Facts only. No investment advice.</div>',
    unsafe_allow_html=True,
)

# Welcome card (shown only when no messages)
if not st.session_state.messages:
    st.markdown(f"""
    <div class="welcome-card">
        <div class="welcome-icon">💬</div>
        <div class="welcome-title">HDFC Mutual Fund FAQ</div>
        <div class="welcome-text">
            Ask <strong>factual questions</strong> about HDFC mutual fund schemes —
            expense ratios, exit loads, NAV, SIP details, and more.
            Data sourced from <strong>Groww.in</strong>.
        </div>
        <div class="scheme-pills">
            <span class="scheme-pill">Large Cap</span>
            <span class="scheme-pill">Mid Cap</span>
            <span class="scheme-pill">Small Cap</span>
            <span class="scheme-pill">Gold ETF FoF</span>
            <span class="scheme-pill">Silver ETF FoF</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            st.markdown(get_status_badge(msg.get("status", "success")), unsafe_allow_html=True)
            st.markdown(clean_answer(msg["content"]))
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
            result = process_query(prompt)

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
