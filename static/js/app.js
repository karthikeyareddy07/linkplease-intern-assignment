/**
 * LinkPlease Dashboard Client Application
 * Creator Automation Command Center
 */

// Application State
const state = {
    currentTab: 'overview',
    stats: { sent: 0, queued: 0, failed: 0, duplicates_blocked: 0 },
    rules: [],
    comments: [],
    activity: [],
    conversations: [],
    selectedConversation: null,
    pollingInterval: null,
    isRefreshing: false
};

// API Helper
const API = {
    async getStats() {
        const res = await fetch('/stats');
        return res.json();
    },
    async getRules() {
        const res = await fetch('/rules');
        return res.json();
    },
    async createRule(keyword, dm_message) {
        const res = await fetch('/rules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, dm_message })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed to create rule');
        }
        return res.json();
    },
    async deleteRule(ruleId) {
        const res = await fetch(`/rules/${ruleId}`, { method: 'DELETE' });
        return res.json();
    },
    async getComments() {
        const res = await fetch('/api/comments');
        return res.json();
    },
    async getActivity() {
        const res = await fetch('/api/activity');
        return res.json();
    },
    async getConversations() {
        const res = await fetch('/api/conversations');
        return res.json();
    },
    async simulateTestComment(keyword, username, text) {
        const res = await fetch('/api/simulate-test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, username, text })
        });
        return res.json();
    }
};

// Toast Notifications
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${type === 'success' ? '✓' : '⚠️'}</span>
        <span>${message}</span>
    `;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// Navigation & Tab Switching
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item[data-tab]');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tab = item.getAttribute('data-tab');
            switchTab(tab);
        });
    });

    // Mobile sidebar toggle
    const mobileBtn = document.getElementById('mobile-menu-btn');
    const sidebar = document.getElementById('sidebar');
    if (mobileBtn && sidebar) {
        mobileBtn.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }
}

function switchTab(tabId) {
    state.currentTab = tabId;

    // Update nav active states
    document.querySelectorAll('.nav-item[data-tab]').forEach(nav => {
        if (nav.getAttribute('data-tab') === tabId) {
            nav.classList.add('active');
        } else {
            nav.classList.remove('active');
        }
    });

    // Update views
    document.querySelectorAll('.page-view').forEach(view => {
        if (view.id === `view-${tabId}`) {
            view.classList.add('active');
        } else {
            view.classList.remove('active');
        }
    });

    // Update topbar titles
    const titles = {
        overview: { title: 'Command Center', sub: 'Turn comments into conversations in real time' },
        automations: { title: 'Automations', sub: 'Manage keyword triggers and automated DM responses' },
        comments: { title: 'Comments Stream', sub: 'Live feed of received comments and matched automations' },
        messages: { title: 'Direct Messages', sub: 'Track individual conversation lifecycles and delivery' },
        activity: { title: 'Live Activity', sub: 'Real-time audit ledger of webhooks, deduplication, and DMs' },
        analytics: { title: 'System Analytics', sub: 'Durable throughput, delivery metrics, and rate limit health' },
        settings: { title: 'Settings', sub: 'API connection, sliding window rate limits, and server health' }
    };

    const t = titles[tabId] || titles.overview;
    const mainHeading = document.getElementById('page-main-heading');
    const subHeading = document.getElementById('page-sub-heading');
    if (mainHeading) mainHeading.textContent = t.title;
    if (subHeading) subHeading.textContent = t.sub;

    // Render specific tab content if needed
    renderCurrentTab();
}

// Data Fetching & Sync
async function fetchAllData() {
    try {
        const [statsData, rulesData, commentsData, activityData, convosData] = await Promise.all([
            API.getStats().catch(() => ({ sent: 0, queued: 0, failed: 0, duplicates_blocked: 0 })),
            API.getRules().catch(() => []),
            API.getComments().catch(() => ({ comments: [] })),
            API.getActivity().catch(() => ({ activity: [] })),
            API.getConversations().catch(() => ({ conversations: [] }))
        ]);

        state.stats = statsData;
        state.rules = rulesData || [];
        state.comments = commentsData.comments || [];
        state.activity = activityData.activity || [];
        state.conversations = convosData.conversations || [];

        renderStats();
        renderCurrentTab();
    } catch (err) {
        console.error('Error fetching data:', err);
    }
}

// Render Stats on Metric Cards & Hero
function renderStats() {
    const { sent, queued, failed, duplicates_blocked } = state.stats;

    // Update numbers
    const elSent = document.getElementById('metric-sent');
    const elQueued = document.getElementById('metric-queued');
    const elFailed = document.getElementById('metric-failed');
    const elDups = document.getElementById('metric-duplicates');

    if (elSent) elSent.textContent = Number(sent).toLocaleString();
    if (elQueued) elQueued.textContent = Number(queued).toLocaleString();
    if (elFailed) elFailed.textContent = Number(failed).toLocaleString();
    if (elDups) elDups.textContent = Number(duplicates_blocked).toLocaleString();

    // Update Hero pill
    const heroActive = document.getElementById('hero-active-count');
    if (heroActive) {
        heroActive.textContent = (sent + queued).toLocaleString();
    }

    // Update sidebar rules count badge
    const badge = document.getElementById('sidebar-rules-badge');
    if (badge) {
        badge.textContent = state.rules.length;
    }
}

// Render Tab Specific Content
function renderCurrentTab() {
    switch (state.currentTab) {
        case 'overview':
            renderOverviewTab();
            break;
        case 'automations':
            renderAutomationsTab();
            break;
        case 'comments':
            renderCommentsTab();
            break;
        case 'messages':
            renderMessagesTab();
            break;
        case 'activity':
            renderActivityTab();
            break;
        case 'analytics':
            renderAnalyticsTab();
            break;
        case 'settings':
            renderSettingsTab();
            break;
    }
}

// 1. Overview Tab Rendering
function renderOverviewTab() {
    // Render Quick Activity Preview
    const container = document.getElementById('overview-activity-timeline');
    if (!container) return;

    if (state.activity.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="padding: 24px;">
                <div class="empty-state-icon">⚡</div>
                <h3>No activity recorded yet</h3>
                <p>Simulate a test comment or wait for incoming Instagram webhook events.</p>
                <button class="btn-secondary" onclick="openTestModal()">Simulate Test Comment</button>
            </div>
        `;
        return;
    }

    const items = state.activity.slice(0, 5);
    container.innerHTML = items.map(item => `
        <div class="activity-item">
            <div class="activity-icon status-${item.status || 'info'}">
                ${item.status === 'success' ? '✓' : item.status === 'warning' ? '🛡️' : item.status === 'error' ? '✕' : '💬'}
            </div>
            <div class="activity-content">
                <div class="activity-title">${escapeHtml(item.title || 'Event')}</div>
                <div class="activity-desc">${escapeHtml(item.text || item.comment_id || '')}</div>
            </div>
            <div class="activity-time">${formatTimeAgo(item.timestamp)}</div>
        </div>
    `).join('');

    // Update hero sample flow with first active rule if available
    const firstRule = state.rules[0];
    if (firstRule) {
        const heroRuleNode = document.getElementById('hero-node-rule');
        const heroMsgNode = document.getElementById('hero-node-msg');
        if (heroRuleNode) heroRuleNode.textContent = firstRule.keyword;
        if (heroMsgNode) heroMsgNode.textContent = firstRule.dm_message.slice(0, 30) + '...';
    }
}

// 2. Automations Tab Rendering
function renderAutomationsTab() {
    const grid = document.getElementById('automations-grid');
    if (!grid) return;

    if (state.rules.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <div class="empty-state-icon">🪄</div>
                <h3>No automations created yet</h3>
                <p>Create your first keyword-triggered automation to start turning comments into DMs.</p>
                <button class="btn-primary" onclick="openCreateRuleModal()">+ Create Automation</button>
            </div>
        `;
        return;
    }

    grid.innerHTML = state.rules.map(rule => `
        <div class="automation-card" id="rule-card-${rule.rule_id}">
            <div class="card-top-row">
                <div class="keyword-badge">
                    <span>🏷️</span>
                    <span>${escapeHtml(rule.keyword)}</span>
                </div>
                <div class="rule-status-badge">
                    <span class="status-dot"></span>
                    <span>Active</span>
                </div>
            </div>

            <div class="rule-body">
                <div class="rule-trigger-line">
                    When a comment contains <strong>${escapeHtml(rule.keyword)}</strong>:
                </div>
                <div class="rule-message-box">
                    "${escapeHtml(rule.dm_message)}"
                </div>
            </div>

            <div class="rule-footer">
                <div class="rule-stats-count">
                    ID: <code>${rule.rule_id}</code>
                </div>
                <div class="rule-actions">
                    <button class="btn-rule-test" onclick="simulateRuleMatch('${escapeHtml(rule.keyword)}')">
                        ▶ Test
                    </button>
                    <button class="btn-rule-delete" title="Delete Rule" onclick="deleteRuleHandler('${rule.rule_id}')">
                        🗑️
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

// 3. Comments Tab Rendering
function renderCommentsTab() {
    const list = document.getElementById('comments-feed-list');
    if (!list) return;

    if (state.comments.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">💬</div>
                <h3>No comments received yet</h3>
                <p>Comments from incoming webhooks will appear in this real-time stream.</p>
                <button class="btn-secondary" onclick="openTestModal()">Send Test Comment</button>
            </div>
        `;
        return;
    }

    list.innerHTML = state.comments.map(c => {
        const userInitial = (c.user_id || 'U').charAt(0).toUpperCase();
        const dmStatus = c.dm_status || 'none';
        let statusBadge = '';
        if (dmStatus === 'delivered') {
            statusBadge = '<span class="tag-dm-status trend-positive">DM Delivered ✓</span>';
        } else if (dmStatus === 'queued' || dmStatus === 'accepted') {
            statusBadge = '<span class="tag-dm-status trend-neutral">DM Queued ⏳</span>';
        } else if (dmStatus === 'failed') {
            statusBadge = '<span class="tag-dm-status trend-warning">DM Failed ✕</span>';
        }

        return `
            <div class="comment-card">
                <div class="comment-avatar">${userInitial}</div>
                <div class="comment-main">
                    <div class="comment-user-row">
                        <span class="comment-username">@${escapeHtml(c.user_id || 'anonymous')}</span>
                        <span class="comment-post-badge">${escapeHtml(c.post_id || 'post')}</span>
                        <span class="comment-time">${formatTimeAgo(c.received_at)}</span>
                    </div>
                    <div class="comment-text-bubble">
                        "${escapeHtml(c.text || '')}"
                    </div>
                    <div class="comment-status-tags">
                        ${c.matched_keyword ? `<span class="tag-matched-rule">Matched: ${escapeHtml(c.matched_keyword)}</span>` : ''}
                        ${statusBadge}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// 4. Messages Tab Rendering
function renderMessagesTab() {
    const listScroll = document.getElementById('convo-items-scroll');
    if (!listScroll) return;

    if (state.conversations.length === 0) {
        listScroll.innerHTML = `
            <div class="empty-state" style="padding: 24px;">
                <div class="empty-state-icon">✉️</div>
                <h3>No conversations yet</h3>
                <p>Automated DMs will populate this timeline.</p>
            </div>
        `;
        const detailBody = document.getElementById('convo-detail-body');
        if (detailBody) {
            detailBody.innerHTML = `
                <div class="empty-state">
                    <h3>Select a conversation</h3>
                    <p>Click on any user from the left pane to view the complete automation lifecycle.</p>
                </div>
            `;
        }
        return;
    }

    // Default select first conversation if none selected
    if (!state.selectedConversation || !state.conversations.find(c => c.job_id === state.selectedConversation.job_id)) {
        state.selectedConversation = state.conversations[0];
    }

    listScroll.innerHTML = state.conversations.map(c => `
        <div class="convo-list-item ${state.selectedConversation?.job_id === c.job_id ? 'active' : ''}" onclick="selectConversation('${c.job_id}')">
            <div class="user-avatar" style="width: 32px; height: 32px;">${(c.user_id || 'U').charAt(0).toUpperCase()}</div>
            <div style="flex: 1; overflow: hidden;">
                <div style="font-weight: 700; font-size: 13px;">@${escapeHtml(c.user_id || 'user')}</div>
                <div style="font-size: 11.5px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    ${escapeHtml(c.message || '')}
                </div>
            </div>
            <div style="font-size: 10.5px; color: var(--text-muted);">
                ${formatTimeAgo(c.updated_at)}
            </div>
        </div>
    `).join('');

    renderConversationDetail();
}

function selectConversation(jobId) {
    const convo = state.conversations.find(c => c.job_id === jobId);
    if (convo) {
        state.selectedConversation = convo;
        renderMessagesTab();
    }
}

function renderConversationDetail() {
    const c = state.selectedConversation;
    const detailHeader = document.getElementById('convo-detail-header');
    const detailBody = document.getElementById('convo-detail-body');

    if (!c || !detailHeader || !detailBody) return;

    detailHeader.innerHTML = `
        <div style="display: flex; align-items: center; gap: 12px;">
            <div class="user-avatar">${(c.user_id || 'U').charAt(0).toUpperCase()}</div>
            <div>
                <div style="font-weight: 800; font-size: 15px;">@${escapeHtml(c.user_id || 'user')}</div>
                <div style="font-size: 11.5px; color: var(--text-muted);">Job ID: <code>${c.job_id}</code></div>
            </div>
        </div>
        <div>
            <span class="tag-dm-status ${c.status === 'delivered' ? 'trend-positive' : c.status === 'failed' ? 'trend-warning' : 'trend-neutral'}">
                ● Status: ${escapeHtml(c.status)}
            </span>
        </div>
    `;

    const isDelivered = c.status === 'delivered';
    const isAccepted = c.status === 'accepted' || isDelivered;

    detailBody.innerHTML = `
        <!-- Chat Thread Preview -->
        <div class="convo-thread-box">
            <div class="chat-bubble-received">
                <div style="font-size: 11px; font-weight: 700; color: var(--text-muted); margin-bottom: 4px;">Original Comment</div>
                "${escapeHtml(c.comment_text || 'Comment matched keyword')}"
            </div>
            <div class="chat-bubble-sent">
                <div style="font-size: 11px; font-weight: 700; opacity: 0.85; margin-bottom: 4px;">Automated LinkPlease DM</div>
                "${escapeHtml(c.message)}"
            </div>
        </div>

        <!-- Automation Lifecycle Stepper -->
        <div class="lifecycle-stepper">
            <div style="font-size: 12.5px; font-weight: 800; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.5px;">
                End-to-End Delivery Lifecycle
            </div>
            <div class="stepper-row step-done">
                <div class="stepper-bullet">✓</div>
                <div>Comment Received & Ingested via Webhook</div>
            </div>
            <div class="stepper-row step-done">
                <div class="stepper-bullet">✓</div>
                <div>Rule Matched: <strong>${escapeHtml(c.rule_keyword || c.rule_id || 'KEYWORD')}</strong></div>
            </div>
            <div class="stepper-row step-done">
                <div class="stepper-bullet">✓</div>
                <div>User+Rule Deduplication Checked (Unique)</div>
            </div>
            <div class="stepper-row ${isAccepted ? 'step-done' : ''}">
                <div class="stepper-bullet">${isAccepted ? '✓' : '4'}</div>
                <div>Rate-Limited DM Dispatched (HTTP 202 Accepted)</div>
            </div>
            <div class="stepper-row ${isDelivered ? 'step-done' : ''}">
                <div class="stepper-bullet">${isDelivered ? '✓' : '5'}</div>
                <div>Asynchronous Delivery Reconciled (${isDelivered ? 'Confirmed Delivered' : 'Processing / Reconciling'})</div>
            </div>
        </div>
    `;
}

// 5. Activity Tab Rendering
function renderActivityTab() {
    const list = document.getElementById('full-activity-timeline');
    if (!list) return;

    if (state.activity.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🕒</div>
                <h3>No activity logged yet</h3>
                <p>System audit trail is clean and ready.</p>
            </div>
        `;
        return;
    }

    list.innerHTML = state.activity.map(item => `
        <div class="activity-item">
            <div class="activity-icon status-${item.status || 'info'}">
                ${item.status === 'success' ? '✓' : item.status === 'warning' ? '🛡️' : item.status === 'error' ? '✕' : '⚡'}
            </div>
            <div class="activity-content">
                <div class="activity-title">${escapeHtml(item.title || 'Event')}</div>
                <div class="activity-desc">${escapeHtml(item.text || item.event_id || '')}</div>
            </div>
            <div class="activity-time">${formatTimeAgo(item.timestamp)}</div>
        </div>
    `).join('');
}

// 6. Analytics Tab Rendering
function renderAnalyticsTab() {
    const { sent, queued, failed, duplicates_blocked } = state.stats;
    const totalJobs = sent + queued + failed;
    const deliveryRate = totalJobs > 0 ? ((sent / totalJobs) * 100).toFixed(1) : '100.0';
    const failureRate = totalJobs > 0 ? ((failed / totalJobs) * 100).toFixed(1) : '0.0';

    const elDeliveryRate = document.getElementById('analytics-delivery-rate');
    const elDeliveryBar = document.getElementById('analytics-delivery-bar');
    const elFailureRate = document.getElementById('analytics-failure-rate');
    const elFailureBar = document.getElementById('analytics-failure-bar');

    if (elDeliveryRate) elDeliveryRate.textContent = `${deliveryRate}%`;
    if (elDeliveryBar) elDeliveryBar.style.width = `${deliveryRate}%`;
    if (elFailureRate) elFailureRate.textContent = `${failureRate}%`;
    if (elFailureBar) elFailureBar.style.width = `${failureRate}%`;
}

// 7. Settings Tab Rendering
function renderSettingsTab() {
    // Already structured via static tokens
}

// Modal Handlers (Create Rule & Preview)
function initModals() {
    const createModal = document.getElementById('create-rule-modal');
    const testModal = document.getElementById('test-simulator-modal');

    // Create Rule Form live preview bindings
    const keywordInput = document.getElementById('modal-keyword-input');
    const messageInput = document.getElementById('modal-message-input');
    const previewKeyword = document.getElementById('preview-keyword');
    const previewMessage = document.getElementById('preview-message');

    if (keywordInput && previewKeyword) {
        keywordInput.addEventListener('input', (e) => {
            const val = e.target.value.trim();
            previewKeyword.textContent = val ? val.toUpperCase() : 'KEYWORD';
        });
    }

    if (messageInput && previewMessage) {
        messageInput.addEventListener('input', (e) => {
            const val = e.target.value.trim();
            previewMessage.textContent = val || 'Your automated DM response will appear here.';
        });
    }

    // Form Submission
    const form = document.getElementById('create-rule-form');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const keyword = keywordInput.value.trim();
            const message = messageInput.value.trim();

            if (!keyword || !message) {
                showToast('Please provide both a keyword and a DM message.', 'error');
                return;
            }

            try {
                const res = await API.createRule(keyword, message);
                showToast(`Automation rule "${res.keyword}" created successfully!`, 'success');
                closeModals();
                form.reset();
                if (previewKeyword) previewKeyword.textContent = 'KEYWORD';
                if (previewMessage) previewMessage.textContent = 'Your automated DM response will appear here.';
                await fetchAllData();
            } catch (err) {
                showToast(err.message || 'Failed to create automation rule', 'error');
            }
        });
    }

    // Simulator Form
    const testForm = document.getElementById('test-simulator-form');
    if (testForm) {
        testForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const keyword = document.getElementById('test-keyword-input').value.trim();
            const username = document.getElementById('test-username-input').value.trim() || 'creator_fan';
            const text = document.getElementById('test-comment-input').value.trim();

            try {
                const res = await API.simulateTestComment(keyword, username, text);
                showToast(`Test comment from @${username} ingested successfully!`, 'success');
                closeModals();
                await fetchAllData();
            } catch (err) {
                showToast('Failed to simulate test comment', 'error');
            }
        });
    }
}

function openCreateRuleModal() {
    const modal = document.getElementById('create-rule-modal');
    if (modal) modal.classList.add('open');
    const input = document.getElementById('modal-keyword-input');
    if (input) setTimeout(() => input.focus(), 100);
}

function openTestModal() {
    const modal = document.getElementById('test-simulator-modal');
    if (modal) modal.classList.add('open');
}

function closeModals() {
    document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('open'));
}

function selectSuggestion(keyword) {
    const input = document.getElementById('modal-keyword-input');
    const preview = document.getElementById('preview-keyword');
    if (input) {
        input.value = keyword;
        if (preview) preview.textContent = keyword;
    }
}

// Rule Actions
async function deleteRuleHandler(ruleId) {
    if (!confirm('Are you sure you want to delete this automation rule?')) return;
    try {
        await API.deleteRule(ruleId);
        showToast('Automation rule deleted.', 'success');
        await fetchAllData();
    } catch (err) {
        showToast('Failed to delete rule.', 'error');
    }
}

async function simulateRuleMatch(keyword) {
    try {
        const res = await API.simulateTestComment(keyword, 'test.creator', `Hey, I want the ${keyword}! 🙏`);
        showToast(`Triggered test comment matching "${keyword}"!`, 'success');
        await fetchAllData();
    } catch (err) {
        showToast('Simulation failed.', 'error');
    }
}

// Manual Refresh
async function handleManualRefresh() {
    const btn = document.getElementById('btn-refresh');
    if (btn) btn.classList.add('spinning');
    await fetchAllData();
    setTimeout(() => {
        if (btn) btn.classList.remove('spinning');
        showToast('Live system data updated.', 'success');
    }, 400);
}

// Utilities
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatTimeAgo(timestamp) {
    if (!timestamp) return 'Just now';
    const now = Date.now() / 1000;
    const diff = Math.max(0, Math.floor(now - timestamp));

    if (diff < 5) return 'Just now';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

// Global Keyboard Shortcuts
function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Cmd/Ctrl + K -> Focus search
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            const searchInput = document.getElementById('topbar-search-input');
            if (searchInput) searchInput.focus();
        }
        // Escape -> Close Modals
        if (e.key === 'Escape') {
            closeModals();
        }
    });
}

// App Initialization
document.addEventListener('DOMContentLoaded', async () => {
    initNavigation();
    initModals();
    initKeyboardShortcuts();

    // Initial Data Load
    await fetchAllData();

    // Start background auto-poll every 3 seconds for live dashboard updates
    state.pollingInterval = setInterval(fetchAllData, 3000);
});
