/**
 * Chart.js Configurations for Competitor Dashboard
 * Shared chart settings and creator functions.
 */

// ─── Global Defaults ────────────────────────────────────────────
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';
Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";

// ─── Color Palettes ─────────────────────────────────────────────
const CHART_COLORS = {
    blue: '#3b82f6',
    green: '#22c55e',
    red: '#ef4444',
    yellow: '#eab308',
    purple: '#a855f7',
    pink: '#ec4899',
    orange: '#f97316',
    cyan: '#06b6d4',
};

const CHART_COLORS_ARRAY = [
    '#3b82f6', '#22c55e', '#ef4444', '#eab308',
    '#a855f7', '#ec4899', '#f97316', '#06b6d4',
];

// ─── Chart Creator Functions ────────────────────────────────────

/**
 * Create a line chart comparing a metric across competitors over time.
 */
function createCompetitorLineChart(canvasId, datasets, labels, options = {}) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: datasets.map(d => ({
                label: d.label,
                data: d.data,
                borderColor: d.color,
                backgroundColor: d.color + '20',
                borderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 6,
                tension: 0.3,
                fill: false,
            })),
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 16,
                        font: { size: 11 },
                    },
                },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${formatNumber(context.parsed.y)}`;
                        }
                    }
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 10 } },
                },
                y: {
                    grid: { color: '#1e293b' },
                    ticks: {
                        font: { size: 10 },
                        callback: function(value) {
                            return formatNumber(value);
                        },
                    },
                },
            },
            interaction: {
                intersect: false,
                mode: 'index',
            },
            ...options,
        },
    });
}

/**
 * Create a bar chart comparing competitors on a single metric.
 */
function createCompetitorBarChart(canvasId, labels, values, colors, label) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: label || 'Valor',
                data: values,
                backgroundColor: colors.map(c => c + 'CC'),
                borderColor: colors,
                borderWidth: 1,
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            return formatNumber(context.parsed.x);
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: '#1e293b' },
                    ticks: {
                        font: { size: 10 },
                        callback: function(value) {
                            return formatNumber(value);
                        },
                    },
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { size: 11 } },
                },
            },
        },
    });
}

/**
 * Create a doughnut chart for traffic source distribution.
 */
function createDoughnutChart(canvasId, labels, values, colors) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    return new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 0,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        usePointStyle: true,
                        padding: 12,
                        font: { size: 11 },
                    },
                },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = ((context.parsed / total) * 100).toFixed(1);
                            return `${context.label}: ${formatNumber(context.parsed)} (${pct}%)`;
                        },
                    },
                },
            },
        },
    });
}

/**
 * Create a sparkline (mini chart) for a single metric trend.
 */
function createSparkline(canvasId, data, color = '#3b82f6') {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map((_, i) => i),
            datasets: [{
                data: data,
                borderColor: color,
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.3,
                fill: false,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: {
                x: { display: false },
                y: { display: false },
            },
            elements: {
                point: { radius: 0 },
            },
        },
    });
}
