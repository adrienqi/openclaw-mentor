'use strict';

const Components = (() => {

    function skeleton(count = 3) {
        return Array(count).fill('<div class="skeleton skeleton--lg"></div>').join('');
    }

    function formatDue(isoStr) {
        if (!isoStr) return '';
        const d = new Date(isoStr);
        const now = new Date();
        const diffMs = d - now;
        const diffH = Math.round(diffMs / 3600000);
        const diffD = Math.round(diffMs / 86400000);

        if (diffMs < 0) {
            const agoH = Math.abs(diffH);
            if (agoH < 1) return 'overdue';
            if (agoH < 24) return `${agoH}h overdue`;
            return `${Math.abs(diffD)}d overdue`;
        }
        if (diffH < 1) return 'soon';
        if (diffH < 24) return `in ${diffH}h`;
        if (diffD < 7) return `in ${diffD}d`;
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }

    function formatDate(isoStr) {
        if (!isoStr) return '—';
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    }

    function timeAgo(isoStr) {
        if (!isoStr) return 'unknown';
        const d = new Date(isoStr);
        const diff = Date.now() - d.getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) return `${hrs}h ago`;
        return `${Math.floor(hrs / 24)}d ago`;
    }

    function typeIcon(type) {
        const icons = {
            goal: '◎',
            plan: '▤',
            reminder: '⏱',
            fact: '◆',
        };
        return icons[type] || '•';
    }

    function memoryCard(item, opts = {}) {
        const due = item.due_at ? `<span class="card-meta">${formatDue(item.due_at)}</span>` : '';
        const tags = item.tags && item.tags.length
            ? `<span class="card-meta">${item.tags.map(t => '#' + t).join(' ')}</span>`
            : '';
        const isOverdue = item.due_at && new Date(item.due_at) < new Date() && item.status === 'active';
        const cls = isOverdue ? 'card card--overdue' : 'card';

        let actions = '';
        if (item.status === 'active') {
            actions = `
                <div class="card-actions">
                    <button class="btn btn--sm btn--done" data-action="done" data-id="${item.id}">Done</button>
                    <button class="btn btn--sm btn--ghost" data-action="cancel" data-id="${item.id}">Cancel</button>
                    ${item.type === 'reminder' && item.due_at ? `<button class="btn btn--sm btn--ghost" data-action="snooze1h" data-id="${item.id}">+1h</button>` : ''}
                </div>`;
        }

        return `
            <div class="${cls}" data-item-id="${item.id}">
                <div style="display:flex;align-items:baseline;gap:8px;">
                    <span style="color:var(--accent);font-size:0.9rem">${typeIcon(item.type)}</span>
                    <div class="card-title">${escapeHtml(item.title)}</div>
                </div>
                <div style="display:flex;gap:12px;margin-top:4px;">${due}${tags}</div>
                ${item.body ? `<div class="card-body">${escapeHtml(item.body)}</div>` : ''}
                ${opts.showActions !== false ? actions : ''}
            </div>`;
    }

    function zoneCard(data) {
        if (!data.last_zone) {
            return `
                <div class="zone-card">
                    <div class="zone-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                    </div>
                    <div class="zone-info">
                        <div class="zone-name">No location yet</div>
                        <div class="zone-detail">Waiting for Home Assistant event</div>
                    </div>
                </div>`;
        }
        const verb = data.last_zone_event === 'enter' ? 'Entered' : 'Left';
        return `
            <div class="zone-card">
                <div class="zone-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                </div>
                <div class="zone-info">
                    <div class="zone-name">${escapeHtml(data.last_zone)}</div>
                    <div class="zone-detail">${verb} · ${timeAgo(data.last_zone_at)}</div>
                </div>
            </div>`;
    }

    function overdueBanner(count) {
        if (!count) return '';
        return `
            <div class="overdue-banner">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                <span class="overdue-text">${count} overdue reminder${count > 1 ? 's' : ''}</span>
            </div>`;
    }

    function triggerRule(rule) {
        const match = rule.match || {};
        const label = [match.kind || '*', match.entity || '*'].join(' · ');
        const msg = rule.message || rule.message_template || rule.template || '';
        return `
            <div class="rule-item">
                <span class="rule-badge">${escapeHtml(rule.reaction || 'notify')}</span>
                <span class="rule-text">${escapeHtml(msg || label)}</span>
                <span class="rule-reaction">${escapeHtml(label)}</span>
            </div>`;
    }

    function addForm() {
        return `
            <div class="add-form" id="add-form">
                <div class="form-row">
                    <select id="add-type">
                        <option value="reminder">Reminder</option>
                        <option value="goal">Goal</option>
                        <option value="plan">Plan</option>
                        <option value="fact">Fact</option>
                    </select>
                </div>
                <label class="form-label" for="add-title">Title</label>
                <input type="text" id="add-title" placeholder="What do you need to remember?" autocomplete="off">
                <label class="form-label" for="add-body">Description</label>
                <textarea id="add-body" rows="3" placeholder="Details, context, next steps…"></textarea>
                <p class="form-hint">Due (optional)</p>
                <div class="form-row form-row--datetime">
                    <div class="form-field">
                        <label class="form-label" for="add-due-date">Date</label>
                        <input type="date" id="add-due-date">
                    </div>
                    <div class="form-field">
                        <label class="form-label" for="add-due-time">Time</label>
                        <input type="time" id="add-due-time">
                    </div>
                </div>
                <label class="form-label" for="add-tags">Tags</label>
                <input type="text" id="add-tags" placeholder="work, health (comma separated)" autocomplete="off">
                <button class="btn btn--primary btn--sm" id="add-submit">Add</button>
            </div>`;
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    return { skeleton, memoryCard, zoneCard, overdueBanner, triggerRule, addForm, formatDate, timeAgo, escapeHtml };
})();
