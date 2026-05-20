'use strict';

const App = (() => {
    let currentTab = 'now';
    let memoryFilter = null;

    function init() {
        if (!API.hasPin()) {
            showAuthModal();
        } else {
            hideAuthModal();
            loadTab(currentTab);
        }
        bindTabs();
        bindAuth();
    }

    function showAuthModal() {
        document.getElementById('auth-modal').classList.remove('hidden');
    }

    function hideAuthModal() {
        document.getElementById('auth-modal').classList.add('hidden');
    }

    function bindAuth() {
        const input = document.getElementById('pin-input');
        const btn = document.getElementById('pin-submit');
        const err = document.getElementById('pin-error');

        btn.addEventListener('click', async () => {
            const pin = input.value.trim();
            if (!pin) { err.textContent = 'PIN required'; return; }
            API.setPin(pin);
            err.textContent = '';
            try {
                await API.getStatus();
                hideAuthModal();
                loadTab(currentTab);
            } catch (e) {
                err.textContent = 'Invalid PIN';
                API.clearPin();
            }
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') btn.click();
        });
    }

    function bindTabs() {
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const name = tab.dataset.tab;
                if (name === currentTab) return;
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
                document.getElementById(`view-${name}`).classList.add('active');
                currentTab = name;
                loadTab(name);
            });
        });
    }

    function loadTab(name) {
        switch (name) {
            case 'now': loadNow(); break;
            case 'memory': loadMemory(); break;
            case 'triggers': loadTriggers(); break;
            case 'more': loadMore(); break;
        }
    }

    async function loadNow() {
        const view = document.getElementById('view-now');
        view.innerHTML = Components.skeleton(3);

        try {
            const [summary, status] = await Promise.all([API.getSummary(), API.getStatus()]);
            updateStatusPill('ok');

            let html = '';
            html += Components.overdueBanner(summary.overdue_count);
            html += Components.zoneCard(status);

            if (summary.upcoming_reminders.length) {
                html += '<div class="section-title">Upcoming</div>';
                summary.upcoming_reminders.forEach(item => {
                    html += Components.memoryCard(item, { showActions: true });
                });
            }

            const counts = summary.counts;
            if (Object.keys(counts).length) {
                html += '<div class="section-title">Active items</div>';
                html += '<div class="card"><div style="display:flex;gap:16px;flex-wrap:wrap;">';
                for (const [type, count] of Object.entries(counts)) {
                    html += `<div style="text-align:center;">
                        <div style="font-family:var(--font-display);font-size:1.4rem;color:var(--accent)">${count}</div>
                        <div class="card-meta">${type}s</div>
                    </div>`;
                }
                html += '</div></div>';
            }

            view.innerHTML = html;
            bindCardActions(view);
        } catch (e) {
            updateStatusPill('error');
            view.innerHTML = `<div class="empty-state">Failed to load: ${Components.escapeHtml(e.message)}</div>`;
        }
    }

    async function loadMemory() {
        const view = document.getElementById('view-memory');
        const types = ['all', 'goal', 'plan', 'reminder', 'fact'];

        let html = '<div class="chips">';
        types.forEach(t => {
            html += `<button class="chip ${(memoryFilter || 'all') === t ? 'active' : ''}" data-filter="${t}">${t}</button>`;
        });
        html += '</div>';
        html += `<button class="btn btn--sm btn--primary" id="toggle-add" style="margin-bottom:12px;">+ Add</button>`;
        html += '<div id="add-form-slot"></div>';
        html += '<div id="memory-list">' + Components.skeleton(4) + '</div>';
        view.innerHTML = html;

        view.querySelectorAll('.chip').forEach(chip => {
            chip.addEventListener('click', () => {
                memoryFilter = chip.dataset.filter === 'all' ? null : chip.dataset.filter;
                view.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                fetchMemoryList();
            });
        });

        document.getElementById('toggle-add').addEventListener('click', () => {
            const slot = document.getElementById('add-form-slot');
            if (slot.innerHTML) { slot.innerHTML = ''; return; }
            slot.innerHTML = Components.addForm();
            bindAddForm();
        });

        fetchMemoryList();
    }

    async function fetchMemoryList() {
        const list = document.getElementById('memory-list');
        if (!list) return;
        list.innerHTML = Components.skeleton(4);

        try {
            const params = {};
            if (memoryFilter) params.type = memoryFilter;
            const data = await API.getMemory(params);
            if (!data.items.length) {
                list.innerHTML = '<div class="empty-state">No items found.</div>';
                return;
            }
            list.innerHTML = data.items.map(i => Components.memoryCard(i)).join('');
            bindCardActions(list);
        } catch (e) {
            list.innerHTML = `<div class="empty-state">${Components.escapeHtml(e.message)}</div>`;
        }
    }

    function bindAddForm() {
        const btn = document.getElementById('add-submit');
        if (!btn) return;
        btn.addEventListener('click', async () => {
            const type = document.getElementById('add-type').value;
            const title = document.getElementById('add-title').value.trim();
            const body = document.getElementById('add-body').value.trim();
            const dateVal = document.getElementById('add-due-date').value;
            const timeVal = document.getElementById('add-due-time').value;
            const tagsRaw = document.getElementById('add-tags').value.trim();
            const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : undefined;

            if (!title) { toast('Title required'); return; }

            let due_at;
            if (dateVal) {
                due_at = timeVal ? `${dateVal}T${timeVal}:00` : `${dateVal}T09:00:00`;
            }

            try {
                await API.createMemory({
                    type,
                    title,
                    body: body || undefined,
                    due_at,
                    tags,
                });
                toast('Created');
                document.getElementById('add-form-slot').innerHTML = '';
                fetchMemoryList();
            } catch (e) {
                toast(e.message);
            }
        });
    }

    async function loadTriggers() {
        const view = document.getElementById('view-triggers');
        view.innerHTML = Components.skeleton(3);

        try {
            const data = await API.getTriggerRules();
            if (!data.rules.length) {
                view.innerHTML = '<div class="empty-state">No trigger rules configured.</div>';
                return;
            }
            let html = '<div class="section-title">Active rules</div>';
            html += data.rules.map(r => Components.triggerRule(r)).join('');
            view.innerHTML = html;
        } catch (e) {
            view.innerHTML = `<div class="empty-state">${Components.escapeHtml(e.message)}</div>`;
        }
    }

    async function loadMore() {
        const view = document.getElementById('view-more');
        try {
            const status = await API.getStatus();
            const summary = await API.getSummary();

            let html = '<div class="section-title">System</div>';
            html += `<div class="info-row"><span class="info-label">Health</span><span class="info-value">${status.health}</span></div>`;
            html += `<div class="info-row"><span class="info-label">Timezone</span><span class="info-value">${Components.escapeHtml(summary.timezone)}</span></div>`;
            html += `<div class="info-row"><span class="info-label">Last zone</span><span class="info-value">${status.last_zone || '—'}</span></div>`;

            html += '<div class="section-title">Actions</div>';
            html += `<button class="btn btn--sm btn--ghost" id="btn-logout" style="margin-top:8px;">Clear PIN & sign out</button>`;

            view.innerHTML = html;

            document.getElementById('btn-logout').addEventListener('click', () => {
                API.clearPin();
                location.reload();
            });
        } catch (e) {
            view.innerHTML = `<div class="empty-state">${Components.escapeHtml(e.message)}</div>`;
        }
    }

    function bindCardActions(container) {
        container.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                const id = parseInt(btn.dataset.id);

                try {
                    if (action === 'done') {
                        await API.patchMemory(id, { status: 'done' });
                        toast('Marked done');
                    } else if (action === 'cancel') {
                        await API.patchMemory(id, { status: 'cancelled' });
                        toast('Cancelled');
                    } else if (action === 'snooze1h') {
                        const newDue = new Date(Date.now() + 3600000).toISOString().slice(0, 19);
                        await API.patchMemory(id, { due_at: newDue });
                        toast('Snoozed +1h');
                    }
                    loadTab(currentTab);
                } catch (err) {
                    toast(err.message);
                }
            });
        });
    }

    function updateStatusPill(state) {
        const pill = document.getElementById('status-pill');
        pill.className = 'pill';
        if (state === 'ok') {
            pill.textContent = 'ONLINE';
            pill.classList.add('pill');
        } else {
            pill.textContent = 'ERROR';
            pill.classList.add('pill--error');
        }
    }

    function toast(msg) {
        const el = document.getElementById('toast');
        el.textContent = msg;
        el.classList.add('show');
        setTimeout(() => el.classList.remove('show'), 2500);
    }

    document.addEventListener('DOMContentLoaded', init);

    return { loadTab, toast };
})();
