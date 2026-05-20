'use strict';

const API = (() => {
    const PIN_KEY = 'mentor_dashboard_pin';

    function getPin() {
        return sessionStorage.getItem(PIN_KEY) || '';
    }

    function setPin(pin) {
        sessionStorage.setItem(PIN_KEY, pin);
    }

    function clearPin() {
        sessionStorage.removeItem(PIN_KEY);
    }

    function hasPin() {
        return !!getPin();
    }

    async function request(method, path, body) {
        const opts = {
            method,
            headers: {
                'X-Dashboard-Pin': getPin(),
                'Content-Type': 'application/json',
            },
        };
        if (body) opts.body = JSON.stringify(body);

        const res = await fetch(path, opts);
        if (res.status === 401) {
            clearPin();
            location.reload();
            throw new Error('Invalid PIN');
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return res.json();
    }

    return {
        getPin,
        setPin,
        clearPin,
        hasPin,
        getSummary: () => request('GET', '/api/summary'),
        getStatus: () => request('GET', '/api/status'),
        getMemory: (params = {}) => {
            const qs = new URLSearchParams();
            if (params.type) qs.set('type', params.type);
            if (params.tag) qs.set('tag', params.tag);
            if (params.status) qs.set('status', params.status);
            const q = qs.toString();
            return request('GET', `/api/memory${q ? '?' + q : ''}`);
        },
        getMemoryItem: (id) => request('GET', `/api/memory/${id}`),
        patchMemory: (id, data) => request('PATCH', `/api/memory/${id}`, data),
        createMemory: (data) => request('POST', '/api/memory', data),
        getTriggerRules: () => request('GET', '/api/triggers/rules'),
    };
})();
