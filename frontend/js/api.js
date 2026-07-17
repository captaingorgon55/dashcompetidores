/**
 * API Client for Competitor Dashboard
 * Handles all communication with the FastAPI backend.
 */

const API = {
    BASE: '',  // Same origin in production

    async request(path, options = {}) {
        const url = `${this.BASE}${path}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
            ...options,
        };

        try {
            const response = await fetch(url, config);
            if (!response.ok) {
                const error = await response.text();
                throw new Error(error || `HTTP ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`API Error [${path}]:`, error);
            throw error;
        }
    },

    // ── Competitors ──────────────────────────────────────────
    getCompetitors() {
        return this.request('/api/competitors');
    },

    getCompetitor(id) {
        return this.request(`/api/competitors/${id}`);
    },

    // ── Dashboard Summary ────────────────────────────────────
    getDashboardSummary() {
        return this.request('/api/dashboard/summary');
    },

    // ── Threads ──────────────────────────────────────────────
    scrapeThreads(competitorId) {
        return this.request(`/api/threads/scrape/${competitorId}`, {
            method: 'POST',
        });
    },

    getThreadsSnapshots(competitorId, days = 30) {
        return this.request(`/api/threads/snapshots/${competitorId}?days=${days}`);
    },

    getLatestAllThreads() {
        return this.request('/api/threads/latest-all');
    },

    // ── Discover ─────────────────────────────────────────────
    getDiscoverData(competitorId, days = 30) {
        return this.request(`/api/discover/${competitorId}?days=${days}`);
    },

    // ── Search ───────────────────────────────────────────────
    getSearchData(competitorId, days = 30) {
        return this.request(`/api/search/${competitorId}?days=${days}`);
    },

    // ── Manual Entries ───────────────────────────────────────
    createManualEntry(data) {
        return this.request('/api/manual-entries', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    getManualEntries(params = {}) {
        const query = new URLSearchParams();
        if (params.competitor_id) query.set('competitor_id', params.competitor_id);
        if (params.category) query.set('category', params.category);
        if (params.days) query.set('days', params.days);
        const qs = query.toString();
        return this.request(`/api/manual-entries${qs ? '?' + qs : ''}`);
    },

    // ── Analysis Engine ────────────────────────────────────
    getMarketAnalysis() {
        return this.request('/api/analysis/market');
    },

    getCompetitorAnalysis(id) {
        return this.request(`/api/analysis/competitor/${id}`);
    },

    getStrategies() {
        return this.request('/api/analysis/strategies');
    },

    getInsights() {
        return this.request('/api/analysis/insights');
    },

    // ── Auth ────────────────────────────────────────────────
    getAuthStatus() {
        return this.request('/auth/status');
    },

    // ── Scrape All ──────────────────────────────────────────
    scrapeAllThreads() {
        return this.request('/api/threads/scrape-all', {
            method: 'POST',
        });
    },
};

// ─── Análisis de Competidores ──────────────────────────────────

const COMPETITOR_ANALYSIS_DATA = {};  // Cache

// ─── Utility Functions ─────────────────────────────────────────

function formatNumber(num) {
    if (num === null || num === undefined) return '—';
    if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + 'M';
    if (num >= 1_000) return (num / 1_000).toFixed(1) + 'K';
    return num.toLocaleString('es-CO');
}

function formatPercent(value) {
    if (value === null || value === undefined) return '—';
    return value.toFixed(2) + '%';
}

function formatDate(isoString) {
    if (!isoString) return '—';
    const d = new Date(isoString);
    return d.toLocaleDateString('es-CO', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
    });
}

function formatDateTime(isoString) {
    if (!isoString) return '—';
    const d = new Date(isoString);
    return d.toLocaleDateString('es-CO', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function timeAgo(isoString) {
    if (!isoString) return 'Nunca';
    const now = new Date();
    const d = new Date(isoString);
    const seconds = Math.floor((now - d) / 1000);

    if (seconds < 60) return 'Hace ' + seconds + 's';
    if (seconds < 3600) return 'Hace ' + Math.floor(seconds / 60) + 'min';
    if (seconds < 86400) return 'Hace ' + Math.floor(seconds / 3600) + 'h';
    if (seconds < 604800) return 'Hace ' + Math.floor(seconds / 86400) + 'd';
    return formatDate(isoString);
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function showLoading(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <span>Cargando datos...</span>
        </div>
    `;
}

function getCompetitorColor(name) {
    const colors = {
        'El Espectador': '#1E3A5F',
        'Revista VEA': '#E91E63',
        'G1 (Globo)': '#FF6F00',
        'La Nación': '#00796B',
        'Clarín': '#D32F2F',
    };
    return colors[name] || '#3B82F6';
}
