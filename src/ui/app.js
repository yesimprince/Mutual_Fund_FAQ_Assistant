/* ==========================================================================
   HDFC Mutual Fund FAQ Assistant — Application Logic
   ========================================================================== */

(() => {
    'use strict';

    // ======================================================================
    // Configuration
    // ======================================================================
    const API_BASE   = '';                  // Same origin (served by FastAPI)
    const ASK_URL    = `${API_BASE}/ask`;
    const RATE_URL   = `${API_BASE}/rate-limit-status`;
    const MAX_CHARS  = 500;
    const RATE_POLL_INTERVAL = 30_000;      // 30 seconds

    // ======================================================================
    // DOM Elements
    // ======================================================================
    const chatArea       = document.getElementById('chat-area');
    const chatContainer  = document.getElementById('chat-container');
    const queryInput     = document.getElementById('query-input');
    const sendBtn        = document.getElementById('send-btn');
    const charCount      = document.getElementById('char-count');
    const welcomeCard    = document.getElementById('welcome-card');
    const quickChips     = document.getElementById('quick-chips');
    const rateStatusEl   = document.getElementById('rate-status');
    const rateStatusText = document.getElementById('rate-status-text');

    // ======================================================================
    // State
    // ======================================================================
    let messages   = [];
    let isLoading  = false;

    // ======================================================================
    // Initialization
    // ======================================================================
    function init() {
        // Event listeners
        sendBtn.addEventListener('click', handleSend);
        queryInput.addEventListener('keydown', handleKeyDown);
        queryInput.addEventListener('input', handleInput);

        // Quick-ask chip buttons
        document.querySelectorAll('.chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const query = chip.dataset.query;
                if (query && !isLoading) {
                    queryInput.value = query;
                    updateCharCount();
                    handleSend();
                }
            });
        });

        // Auto-resize textarea
        queryInput.addEventListener('input', autoResize);

        // Initial rate-limit status fetch
        fetchRateStatus();
        setInterval(fetchRateStatus, RATE_POLL_INTERVAL);

        // Focus input
        queryInput.focus();
    }


    // ======================================================================
    // Input Handling
    // ======================================================================

    function handleKeyDown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
        if (e.key === 'Escape') {
            queryInput.value = '';
            updateCharCount();
            autoResize();
        }
    }

    function handleInput() {
        updateCharCount();
    }

    function updateCharCount() {
        const len = queryInput.value.length;
        charCount.textContent = `${len}/${MAX_CHARS}`;
        charCount.classList.remove('input-bar__char-count--warning', 'input-bar__char-count--danger');

        if (len >= MAX_CHARS) {
            charCount.classList.add('input-bar__char-count--danger');
        } else if (len >= 450) {
            charCount.classList.add('input-bar__char-count--warning');
        }
    }

    function autoResize() {
        queryInput.style.height = 'auto';
        queryInput.style.height = Math.min(queryInput.scrollHeight, 120) + 'px';
    }


    // ======================================================================
    // Send Query
    // ======================================================================

    async function handleSend() {
        const query = queryInput.value.trim();
        if (!query || isLoading) return;

        // Clear input
        queryInput.value = '';
        updateCharCount();
        autoResize();

        // Hide welcome card after first message
        if (welcomeCard && !welcomeCard.classList.contains('welcome--hidden')) {
            welcomeCard.classList.add('welcome--hidden');
        }

        // Add user message
        addMessage('user', query);

        // Show typing indicator
        const typingEl = showTyping();

        // Disable input
        setLoading(true);

        try {
            const response = await fetch(ASK_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query }),
            });

            // Remove typing indicator
            removeTyping(typingEl);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            addBotMessage(data);

        } catch (err) {
            removeTyping(typingEl);
            addBotMessage({
                status: 'error',
                answer: 'Unable to connect to the server. Please make sure the API is running and try again.',
                source: null,
                last_updated: null,
                query_type: 'factual',
            });
        } finally {
            setLoading(false);
            queryInput.focus();
        }
    }

    function setLoading(loading) {
        isLoading = loading;
        sendBtn.disabled = loading;
        queryInput.disabled = loading;
    }


    // ======================================================================
    // Message Rendering
    // ======================================================================

    function addMessage(role, content) {
        const msg = { role, content, timestamp: new Date() };
        messages.push(msg);

        if (role === 'user') {
            renderUserMessage(msg);
        }
    }

    function addBotMessage(data) {
        const msg = {
            role: 'bot',
            content: data.answer || '',
            status: data.status || 'error',
            source: data.source || null,
            lastUpdated: data.last_updated || null,
            queryType: data.query_type || 'factual',
            timestamp: new Date(),
        };
        messages.push(msg);
        renderBotMessage(msg);
    }

    function renderUserMessage(msg) {
        const el = document.createElement('div');
        el.className = 'message message--user';
        el.innerHTML = `
            <span class="message__label">You</span>
            <div class="message__bubble">
                <span class="message__answer">${escapeHtml(msg.content)}</span>
            </div>
        `;
        chatContainer.appendChild(el);
        scrollToBottom();
    }

    function renderBotMessage(msg) {
        const statusClass = getStatusClass(msg.status);
        const labelText   = getStatusLabel(msg.status);
        const labelIcon   = getStatusIcon(msg.status);

        const el = document.createElement('div');
        el.className = `message message--bot ${statusClass}`;

        // Build answer HTML — strip "Last updated from sources:" footer from answer
        // and display it as metadata instead
        let answerText = msg.content;
        let footerDate = msg.lastUpdated;

        const footerMatch = answerText.match(/Last updated from sources:\s*(.+)/i);
        if (footerMatch) {
            if (!footerDate || footerDate === 'Unknown') {
                footerDate = footerMatch[1].trim();
            }
            answerText = answerText.replace(/\n?\n?Last updated from sources:\s*.+/i, '').trim();
        }

        // Build meta section
        let metaHtml = '';
        if (msg.source || footerDate) {
            metaHtml = '<div class="message__meta">';
            if (msg.source) {
                const displayUrl = formatUrl(msg.source);
                metaHtml += `<a class="message__citation" href="${escapeHtml(msg.source)}" target="_blank" rel="noopener noreferrer">📎 ${escapeHtml(displayUrl)}</a>`;
            }
            if (footerDate && footerDate !== 'Unknown') {
                metaHtml += `<span class="message__timestamp">🕐 Updated: ${escapeHtml(footerDate)}</span>`;
            }
            metaHtml += '</div>';
        }

        el.innerHTML = `
            <span class="message__label">${labelIcon} ${labelText}</span>
            <div class="message__bubble">
                <span class="message__answer">${escapeHtml(answerText)}</span>
                ${metaHtml}
            </div>
        `;

        chatContainer.appendChild(el);
        scrollToBottom();
    }

    function getStatusClass(status) {
        const map = {
            success:      '',
            refused:      'message--refused',
            blocked:      'message--blocked',
            rate_limited: 'message--rate-limited',
            error:        'message--error',
        };
        return map[status] || 'message--error';
    }

    function getStatusLabel(status) {
        const map = {
            success:      'Assistant',
            refused:      'Advisory Blocked',
            blocked:      'PII Blocked',
            rate_limited: 'Rate Limited',
            error:        'Error',
        };
        return map[status] || 'Assistant';
    }

    function getStatusIcon(status) {
        const map = {
            success:      '🤖',
            refused:      '⚠️',
            blocked:      '🛑',
            rate_limited: '⏳',
            error:        '❌',
        };
        return map[status] || '🤖';
    }


    // ======================================================================
    // Typing Indicator
    // ======================================================================

    function showTyping() {
        const el = document.createElement('div');
        el.className = 'typing';
        el.id = 'typing-indicator';
        el.innerHTML = `
            <div class="typing__bubble">
                <span class="typing__dot"></span>
                <span class="typing__dot"></span>
                <span class="typing__dot"></span>
            </div>
        `;
        chatContainer.appendChild(el);
        scrollToBottom();
        return el;
    }

    function removeTyping(el) {
        if (el && el.parentNode) {
            el.parentNode.removeChild(el);
        }
    }


    // ======================================================================
    // Rate-Limit Status
    // ======================================================================

    async function fetchRateStatus() {
        try {
            const resp = await fetch(RATE_URL);
            if (!resp.ok) return;

            const data = await resp.json();
            const rpm = data.rpm || {};
            const used = rpm.used || 0;
            const limit = rpm.limit || 30;
            const remaining = rpm.remaining ?? (limit - used);

            rateStatusText.textContent = `${remaining}/${limit} RPM`;

            // Color coding
            rateStatusEl.classList.remove('header__status--warning', 'header__status--danger');
            const pct = remaining / limit;
            if (pct <= 0.1) {
                rateStatusEl.classList.add('header__status--danger');
            } else if (pct <= 0.3) {
                rateStatusEl.classList.add('header__status--warning');
            }

        } catch {
            rateStatusText.textContent = 'Offline';
            rateStatusEl.classList.add('header__status--danger');
        }
    }


    // ======================================================================
    // Utilities
    // ======================================================================

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatUrl(url) {
        try {
            const u = new URL(url);
            let path = u.pathname;
            if (path.length > 35) {
                path = path.substring(0, 32) + '...';
            }
            return u.hostname + path;
        } catch {
            return url.length > 40 ? url.substring(0, 37) + '...' : url;
        }
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatArea.scrollTop = chatArea.scrollHeight;
        });
    }


    // ======================================================================
    // Boot
    // ======================================================================
    document.addEventListener('DOMContentLoaded', init);

})();
