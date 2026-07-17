/**
 * Main Dashboard Logic
 * Handles data loading, UI updates, and interactivity.
 */

document.addEventListener('DOMContentLoaded', () => {
    // Highlight active nav item based on current page
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-item').forEach(item => {
        const href = item.getAttribute('href') || '';
        if (currentPath === href || (currentPath === '/' && href === '/')) {
            item.classList.add('active');
        } else if (href !== '/' && currentPath.startsWith(href)) {
            item.classList.add('active');
        }
    });

    // Initialize page-specific functionality
    const pageId = document.body.dataset.page;
    if (pageId === 'dashboard') initDashboard();
    else if (pageId === 'competitors') initCompetitors();
    else if (pageId === 'threads') initThreads();
    else if (pageId === 'discover') initDiscover();
    else if (pageId === 'search') initSearchTraffic();
    else if (pageId === 'manual-entry') initManualEntry();
    else if (pageId === 'analysis') initAnalysis();
});


// ══════════════════════════════════════════════════════════════
// ANALYSIS PAGE — Estrategias, Insights y Acciones
// ══════════════════════════════════════════════════════════════

async function initAnalysis() {
    showLoading('market-kpis');
    showLoading('strategies-container');
    showLoading('insights-container');
    showLoading('weekly-actions-container');
    showLoading('competitors-analysis-container');

    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(tc => tc.style.display = 'none');
            tab.classList.add('active');
            const tabName = tab.dataset.tab;
            document.getElementById(`tab-${tabName}`).style.display = 'block';
        });
    });

    try {
        const data = await API.getMarketAnalysis();
        renderMarketKPIs(data.market);
        renderStrategies(data.overall_strategies);
        renderOverallInsights(data.overall_insights, data.overall_strategies);
        renderWeeklyActions(data.weekly_actions);
        renderCompetitorAnalysis(data.competitors);
        document.getElementById('last-updated-analysis').textContent =
            `Análisis generado: ${formatDateTime(new Date().toISOString())}`;
    } catch (error) {
        const containers = ['market-kpis', 'strategies-container', 'insights-container',
                          'weekly-actions-container', 'competitors-analysis-container'];
        containers.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = `<div class="alert alert-danger">⚠️ Error: ${error.message}</div>`;
        });
    }
}

function renderMarketKPIs(market) {
    const grid = document.getElementById('market-kpis');
    if (!grid) return;

    grid.innerHTML = `
        <div class="kpi-card market-kpi">
            <div class="market-kpi-value">${formatNumber(market.total_followers)}</div>
            <div class="market-kpi-label">Total Seguidores Monitoreados</div>
        </div>
        <div class="kpi-card market-kpi">
            <div class="market-kpi-value">${market.us_market_share?.toFixed(1) || 0}%</div>
            <div class="market-kpi-label">Nuestra Participación de Mercado</div>
        </div>
        <div class="kpi-card market-kpi">
            <div class="market-kpi-value">#${market.us_rank || '—'}</div>
            <div class="market-kpi-label">Posición en Ranking</div>
        </div>
        <div class="kpi-card market-kpi">
            <div class="market-kpi-value ${market.average_growth_rate > 0 ? 'positive' : market.average_growth_rate < 0 ? 'negative' : ''}">
                ${market.average_growth_rate ? (market.average_growth_rate > 0 ? '+' : '') + market.average_growth_rate.toFixed(1) + '%' : '—'}
            </div>
            <div class="market-kpi-label">Crecimiento Promedio del Mercado</div>
        </div>
    `;
}

function renderStrategies(strategies) {
    const container = document.getElementById('strategies-container');
    if (!container) return;

    if (!strategies || strategies.length === 0) {
        container.innerHTML = '<div class="alert alert-info">💡 No hay suficientes datos para generar estrategias. Scrapea datos de Threads primero.</div>';
        return;
    }

    container.innerHTML = strategies.map(s => `
        <div class="strategy-card">
            <div class="strategy-title">
                ${s.title}
                <span class="priority-badge priority-${s.priority === 'alta' ? 'alta' : s.priority === 'media' ? 'media' : 'baja'}">
                    ${s.priority === 'alta' ? '🔴 Alta' : s.priority === 'media' ? '🟡 Media' : '🟢 Baja'}
                </span>
            </div>
            <div class="strategy-desc">${s.description}</div>
            ${s.actions.map(a => `<div class="strategy-action">${a}</div>`).join('')}
        </div>
    `).join('');
}

function renderOverallInsights(overallInsights, strategies) {
    const container = document.getElementById('insights-container');
    if (!container) return;

    let html = '';

    // Overall market insights
    if (overallInsights && overallInsights.length > 0) {
        html += `
            <div class="card" style="grid-column: 1 / -1;">
                <div class="card-header"><h3>📊 Insights del Mercado</h3></div>
                <div class="card-body">
                    ${overallInsights.map(i => `<div class="insight-card"><div class="insight-text">${i}</div></div>`).join('')}
                </div>
            </div>
        `;
    }

    container.innerHTML = html || '<div class="alert alert-info">No hay insights aún. Scrapea datos para generar análisis.</div>';
}

function renderWeeklyActions(actions) {
    const container = document.getElementById('weekly-actions-container');
    if (!container) return;

    if (!actions || actions.length === 0) {
        container.innerHTML = '<div class="alert alert-info">No hay acciones generadas aún.</div>';
        return;
    }

    container.innerHTML = `
        <div class="card">
            <div class="card-header">
                <h3>✅ Plan de Acción Semanal</h3>
                <span style="font-size:0.8rem;color:var(--text-muted);">Marca las tareas completadas</span>
            </div>
            <div class="card-body">
                ${actions.map((a, i) => `
                    <div class="weekly-action">
                        <input type="checkbox" id="action-${i}" onchange="updateActionProgress()">
                        <label for="action-${i}" style="flex:1;cursor:pointer;">${a}</label>
                    </div>
                `).join('')}
                <div style="margin-top:1rem;padding-top:1rem;border-top:1px solid var(--border-color);">
                    <div style="display:flex;align-items:center;gap:1rem;">
                        <span style="font-size:0.85rem;color:var(--text-muted);">Progreso:</span>
                        <div style="flex:1;height:8px;background:var(--bg-primary);border-radius:4px;overflow:hidden;">
                            <div id="action-progress-bar" style="height:100%;width:0%;background:var(--accent-green);border-radius:4px;transition:width 0.3s ease;"></div>
                        </div>
                        <span id="action-progress-text" style="font-size:0.85rem;font-weight:600;color:var(--accent-green);">0%</span>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function updateActionProgress() {
    const checkboxes = document.querySelectorAll('.weekly-action input[type="checkbox"]');
    const total = checkboxes.length;
    const checked = document.querySelectorAll('.weekly-action input[type="checkbox"]:checked').length;
    const pct = total > 0 ? Math.round((checked / total) * 100) : 0;
    const bar = document.getElementById('action-progress-bar');
    const text = document.getElementById('action-progress-text');
    if (bar) bar.style.width = pct + '%';
    if (text) text.textContent = pct + '%';
    if (pct === 100 && bar) bar.style.background = 'var(--accent-green)';
}

function renderCompetitorAnalysis(competitors) {
    const container = document.getElementById('competitors-analysis-container');
    if (!container) return;

    if (!competitors || competitors.length === 0) {
        container.innerHTML = '<div class="alert alert-info">No hay datos de competidores aún.</div>';
        return;
    }

    container.innerHTML = competitors.map(c => `
        <div class="card" style="margin-bottom:1.25rem;">
            <div class="card-header">
                <h3>
                    <span style="display:inline-block;width:12px;height:12px;border-radius:50%;
                        background:${c.color || '#3b82f6'};margin-right:8px;"></span>
                    ${c.name}
                    ${c.is_us ? '<span class="competitor-badge badge-us" style="margin-left:6px;">NOSOTROS</span>' : ''}
                </h3>
                <span class="priority-badge ${c.threads_trend === 'growing' ? 'priority-alta' : c.threads_trend === 'declining' ? 'priority-baja' : 'priority-media'}">
                    ${c.threads_trend === 'growing' ? '📈 Creciendo' : c.threads_trend === 'declining' ? '📉 Declinando' : '➡️ Estable'}
                </span>
            </div>
            <div class="card-body">
                <div class="kpi-grid" style="grid-template-columns:repeat(auto-fit,minmax(120px,1fr));margin-bottom:1rem;">
                    <div class="">
                        <div style="font-size:1.3rem;font-weight:700;">${formatNumber(c.threads.current_followers)}</div>
                        <div style="font-size:0.7rem;color:var(--text-muted);text-transform:uppercase;">Seguidores</div>
                    </div>
                    <div class="">
                        <div style="font-size:1.3rem;font-weight:700;color:${c.threads.follower_growth_30d > 0 ? 'var(--accent-green)' : c.threads.follower_growth_30d < 0 ? 'var(--accent-red)' : 'var(--text-primary)'};">
                            ${c.threads.follower_growth_30d > 0 ? '+' : ''}${c.threads.follower_growth_30d?.toFixed(1) || '0.0'}%
                        </div>
                        <div style="font-size:0.7rem;color:var(--text-muted);text-transform:uppercase;">Crecimiento 30d</div>
                    </div>
                    <div class="">
                        <div style="font-size:1.3rem;font-weight:700;">${formatNumber(c.threads.posts_count)}</div>
                        <div style="font-size:0.7rem;color:var(--text-muted);text-transform:uppercase;">Posts</div>
                    </div>
                    <div class="">
                        <div style="font-size:1.3rem;font-weight:700;">${formatNumber(c.search.total_clicks_30d)}</div>
                        <div style="font-size:0.7rem;color:var(--text-muted);text-transform:uppercase;">Clics Search (30d)</div>
                    </div>
                </div>

                ${renderInsightList(c.insights, '💡', '')}
                ${renderInsightList(c.recommendations, '🎯', 'Recomendaciones')}
                ${renderInsightList(c.opportunities, '🟢', 'Oportunidades', 'opportunity-card')}
                ${renderInsightList(c.risks, '⚠️', 'Riesgos', 'risk-card')}
            </div>
        </div>
    `).join('');
}

function renderInsightList(items, icon, title, extraClass = '') {
    if (!items || items.length === 0) return '';
    const header = title ? `<h4 style="font-size:0.85rem;font-weight:600;color:var(--text-secondary);margin-bottom:0.5rem;margin-top:1rem;">${title}</h4>` : '';
    return `
        ${header}
        ${items.map(item => `
            <div class="insight-card ${extraClass}">
                <div class="insight-text">
                    <span>${item}</span>
                </div>
            </div>
        `).join('')}
    `;
}


// ══════════════════════════════════════════════════════════════
// DASHBOARD
// ══════════════════════════════════════════════════════════════

async function initDashboard() {
    showLoading('kpi-grid');
    showLoading('chart-threads-followers');
    showLoading('chart-threads-comparison');

    try {
        const data = await API.getDashboardSummary();
        renderDashboardKPIs(data.competitors);
        renderDashboardThreadsChart(data.competitors);
        renderDashboardBarChart(data.competitors);
        renderCompetitorTable(data.competitors);
        updateLastUpdated();
    } catch (error) {
        document.getElementById('kpi-grid').innerHTML = `
            <div class="alert alert-danger">
                ⚠️ Error al cargar datos: ${error.message}
            </div>`;
    }
}

function renderDashboardKPIs(competitors) {
    const grid = document.getElementById('kpi-grid');
    if (!grid) return;

    const us = competitors.filter(c => c.is_us);
    const usTotalFollowers = us.reduce((s, c) => s + (c.threads_followers || 0), 0);
    const usTotalWeeklySessions = us.reduce((s, c) => s + (c.weekly_sessions || 0), 0);
    const usTotalDiscover = us.reduce((s, c) => s + (c.weekly_discover_clicks || 0), 0);
    const avgEngagement = us.length > 0
        ? us.reduce((s, c) => s + (c.threads_engagement || 0), 0) / us.length
        : 0;

    const all = competitors;
    const totalCompetitors = all.length;
    const competitorFollowers = all
        .filter(c => !c.is_us)
        .reduce((s, c) => s + (c.threads_followers || 0), 0);

    grid.innerHTML = `
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">Seguidores Threads</span>
                <span class="kpi-card-icon">📱</span>
            </div>
            <div class="kpi-card-value">${formatNumber(usTotalFollowers)}</div>
            <div class="kpi-card-change positive">Total El Espectador + VEA</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">Sesiones Semanales</span>
                <span class="kpi-card-icon">📊</span>
            </div>
            <div class="kpi-card-value">${formatNumber(usTotalWeeklySessions)}</div>
            <div class="kpi-card-change neutral">Tráfico total web</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">Discover Clicks/Sem</span>
                <span class="kpi-card-icon">🔍</span>
            </div>
            <div class="kpi-card-value">${formatNumber(usTotalDiscover)}</div>
            <div class="kpi-card-change neutral">Google Discover semanal</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">Competidores</span>
                <span class="kpi-card-icon">🏆</span>
            </div>
            <div class="kpi-card-value">${totalCompetitors}</div>
            <div class="kpi-card-change neutral">${formatNumber(competitorFollowers)} seguidores totales competencia</div>
        </div>
    `;
}

function renderDashboardThreadsChart(competitors) {
    const ctx = document.getElementById('chart-threads-followers');
    if (!ctx) return;

    const sorted = [...competitors].sort((a, b) => b.threads_followers - a.threads_followers);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sorted.map(c => c.name),
            datasets: [{
                label: 'Seguidores en Threads',
                data: sorted.map(c => c.threads_followers),
                backgroundColor: sorted.map(c => {
                    const color = c.color || '#3b82f6';
                    return color + 'CC';
                }),
                borderColor: sorted.map(c => c.color || '#3b82f6'),
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
                        label: ctx => formatNumber(ctx.parsed.x),
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: '#1e293b' },
                    ticks: {
                        callback: v => formatNumber(v),
                        font: { size: 10 },
                    },
                },
                y: {
                    grid: { display: false },
                    ticks: {
                        font: { size: 11, weight: '500' },
                    },
                },
            },
        },
    });
}

function renderDashboardBarChart(competitors) {
    const ctx = document.getElementById('chart-threads-comparison');
    if (!ctx) return;

    const sorted = [...competitors].sort((a, b) => b.threads_followers - a.threads_followers);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sorted.map(c => c.name),
            datasets: [
                {
                    label: 'Seguidores',
                    data: sorted.map(c => c.threads_followers || 0),
                    backgroundColor: sorted.map(c => (c.color || '#3b82f6') + 'CC'),
                    borderRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true, position: 'top', labels: { usePointStyle: true, font: { size: 11 } } },
                tooltip: {
                    backgroundColor: '#1e293b',
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: ctx => formatNumber(ctx.parsed.y),
                    },
                },
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10 } } },
                y: {
                    grid: { color: '#1e293b' },
                    ticks: { callback: v => formatNumber(v), font: { size: 10 } },
                },
            },
        },
    });
}

function renderCompetitorTable(competitors) {
    const tbody = document.getElementById('competitor-table-body');
    if (!tbody) return;

    const sorted = [...competitors].sort((a, b) => b.threads_followers - a.threads_followers);

    tbody.innerHTML = sorted.map(c => `
        <tr>
            <td>
                <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
                    background:${c.color || '#3b82f6'};margin-right:8px;"></span>
                ${c.name}
                ${c.is_us ? '<span class="competitor-badge badge-us" style="margin-left:6px;">NOSOTROS</span>' : ''}
            </td>
            <td>${formatNumber(c.threads_followers)}</td>
            <td>
                <span class="${c.threads_follower_growth >= 0 ? 'kpi-card-change positive' : 'kpi-card-change negative'}">
                    ${c.threads_follower_growth >= 0 ? '↑' : '↓'} ${Math.abs(c.threads_follower_growth).toFixed(1)}%
                </span>
            </td>
            <td>${c.threads_engagement ? c.threads_engagement.toFixed(2) + '%' : '—'}</td>
            <td>${formatNumber(c.weekly_sessions)}</td>
            <td>${formatNumber(c.weekly_discover_clicks)}</td>
            <td>${c.last_updated ? timeAgo(c.last_updated) : '—'}</td>
        </tr>
    `).join('');
}

function updateLastUpdated() {
    const el = document.getElementById('last-updated');
    if (el) {
        el.textContent = `Última actualización: ${formatDateTime(new Date().toISOString())}`;
    }
}


// ══════════════════════════════════════════════════════════════
// COMPETITORS PAGE
// ══════════════════════════════════════════════════════════════

async function initCompetitors() {
    showLoading('competitors-list');
    showLoading('competitor-chart');
    try {
        const data = await API.getLatestAllThreads();
        renderCompetitorCards(data);
        renderCompetitorChart(data);
    } catch (error) {
        document.getElementById('competitors-list').innerHTML = `
            <div class="alert alert-danger">⚠️ ${error.message}</div>`;
    }
}

function renderCompetitorCards(data) {
    const container = document.getElementById('competitors-list');
    if (!container) return;

    const sorted = [...data].sort((a, b) => (b.snapshot?.followers || 0) - (a.snapshot?.followers || 0));

    container.innerHTML = sorted.map(item => `
        <div class="competitor-row">
            <div class="competitor-avatar" style="background:${item.competitor.color || '#3b82f6'}">
                ${item.competitor.name.charAt(0)}
            </div>
            <div class="competitor-info">
                <div class="competitor-name">
                    ${item.competitor.name}
                    <span class="competitor-badge ${item.competitor.is_us ? 'badge-us' : 'badge-competitor'}"
                          style="margin-left:6px;">
                        ${item.competitor.is_us ? 'NOSOTROS' : 'COMPETIDOR'}
                    </span>
                </div>
                <div class="competitor-handle">${item.competitor.threads_handle || ''}</div>
            </div>
            <div class="competitor-metrics">
                <div class="competitor-metric">
                    <div class="competitor-metric-value">${formatNumber(item.snapshot?.followers || 0)}</div>
                    <div class="competitor-metric-label">Seguidores</div>
                </div>
                <div class="competitor-metric">
                    <div class="competitor-metric-value">${formatNumber(item.snapshot?.posts_count || 0)}</div>
                    <div class="competitor-metric-label">Posts</div>
                </div>
                <div class="competitor-metric">
                    <div class="competitor-metric-value">${item.snapshot?.engagement_rate ? item.snapshot.engagement_rate.toFixed(2) + '%' : '—'}</div>
                    <div class="competitor-metric-label">Engagement</div>
                </div>
            </div>
            <button class="btn btn-secondary btn-sm scrape-btn" data-id="${item.competitor.id}">
                🔄 Scrape
            </button>
        </div>
    `).join('');

    // Bind scrape buttons
    document.querySelectorAll('.scrape-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            btn.disabled = true;
            btn.textContent = '⏳ Scrapeando...';
            try {
                await API.scrapeThreads(parseInt(id));
                showToast('✅ Datos actualizados', 'success');
                // Reload
                const data = await API.getLatestAllThreads();
                renderCompetitorCards(data);
                renderCompetitorChart(data);
            } catch (error) {
                showToast('❌ Error: ' + error.message, 'error');
                btn.textContent = '🔄 Scrape';
                btn.disabled = false;
            }
        });
    });
}

function renderCompetitorChart(data) {
    const ctx = document.getElementById('competitor-chart');
    if (!ctx) return;

    const sorted = [...data].sort((a, b) => (b.snapshot?.followers || 0) - (a.snapshot?.followers || 0));

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sorted.map(d => d.competitor.name),
            datasets: [{
                label: 'Seguidores Threads',
                data: sorted.map(d => d.snapshot?.followers || 0),
                backgroundColor: sorted.map(d => (d.competitor.color || '#3b82f6') + 'CC'),
                borderColor: sorted.map(d => d.competitor.color || '#3b82f6'),
                borderWidth: 2,
                borderRadius: 6,
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
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: ctx => formatNumber(ctx.parsed.x),
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: '#1e293b' },
                    ticks: { callback: v => formatNumber(v), font: { size: 10 } },
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { size: 11, weight: '500' } },
                },
            },
        },
    });
}


// ══════════════════════════════════════════════════════════════
// THREADS PAGE
// ══════════════════════════════════════════════════════════════

async function initThreads() {
    showLoading('threads-chart');
    showLoading('threads-selector');
    try {
        const competitors = await API.getCompetitors();
        const selector = document.getElementById('threads-selector');
        if (selector) {
            selector.innerHTML = competitors.map(c => `
                <option value="${c.id}" ${c.is_us ? 'selected' : ''}>${c.name}</option>
            `).join('');
            selector.addEventListener('change', () => loadThreadsChart(parseInt(selector.value)));
        }
        await loadThreadsChart(competitors.find(c => c.is_us)?.id || 1);
    } catch (error) {
        console.error('Threads page error:', error);
    }
}

async function loadThreadsChart(competitorId) {
    const chartEl = document.getElementById('threads-chart');
    if (!chartEl) return;

    chartEl.innerHTML = '<div class="loading"><div class="spinner"></div><span>Cargando...</span></div>';

    try {
        const snapshots = await API.getThreadsSnapshots(competitorId, 30);
        const comp = await API.getCompetitor(competitorId);

        if (!snapshots || snapshots.length === 0) {
            chartEl.innerHTML = `
                <div class="alert alert-info">
                    💡 No hay datos de Threads para ${comp.name}. 
                    <button class="btn btn-primary btn-sm scrape-btn" data-id="${comp.id}" style="margin-left:1rem;">
                        🔄 Scrapear ahora
                    </button>
                </div>`;
            const btn = chartEl.querySelector('.scrape-btn');
            if (btn) btn.addEventListener('click', async () => {
                await API.scrapeThreads(comp.id);
                showToast('✅ Datos actualizados', 'success');
                loadThreadsChart(competitorId);
            });
            return;
        }

        const labels = snapshots.map(s => formatDate(s.snapshot_date));
        const followers = snapshots.map(s => s.followers);

        chartEl.innerHTML = '<canvas id="threads-chart-canvas" height="300"></canvas>';
        const canvas = document.getElementById('threads-chart-canvas');
        if (canvas) {
            new Chart(canvas, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: `${comp.name} - Seguidores`,
                        data: followers,
                        borderColor: comp.color || '#3b82f6',
                        backgroundColor: (comp.color || '#3b82f6') + '20',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 4,
                        pointHoverRadius: 8,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: true, position: 'top' },
                        tooltip: {
                            backgroundColor: '#1e293b',
                            borderColor: '#334155',
                            borderWidth: 1,
                            padding: 12,
                            callbacks: {
                                label: ctx => `${ctx.dataset.label}: ${formatNumber(ctx.parsed.y)}`,
                            },
                        },
                    },
                    scales: {
                        x: { grid: { display: false }, ticks: { font: { size: 10 }, maxTicksLimit: 10 } },
                        y: {
                            grid: { color: '#1e293b' },
                            ticks: { callback: v => formatNumber(v), font: { size: 10 } },
                        },
                    },
                },
            });
        }
    } catch (error) {
        chartEl.innerHTML = `<div class="alert alert-danger">⚠️ ${error.message}</div>`;
    }
}


// ══════════════════════════════════════════════════════════════
// DISCOVER PAGE
// ══════════════════════════════════════════════════════════════

async function initDiscover() {
    showLoading('discover-chart');
    showLoading('discover-stats');
    try {
        const competitors = await API.getCompetitors();
        const us = competitors.filter(c => c.is_us);

        // Show chart for first "us" competitor
        if (us.length > 0) {
            const data = await API.getDiscoverData(us[0].id, 30);
            renderDiscoverChart(data, us[0].name);
            renderDiscoverStats(data);
        }
        renderDiscoverCompetitorTable(competitors);
    } catch (error) {
        document.getElementById('discover-chart').innerHTML = `
            <div class="alert alert-danger">⚠️ ${error.message}</div>`;
    }
}

function renderDiscoverChart(data, name) {
    const canvas = document.getElementById('discover-chart');
    if (!canvas) return;

    if (!data || data.length === 0) {
        canvas.innerHTML = '<div class="alert alert-info">💡 No hay datos de Discover aún. Conecta Google Search Console para ver métricas.</div>';
        return;
    }

    canvas.innerHTML = '<canvas id="discover-canvas" height="300"></canvas>';
    const ctx = document.getElementById('discover-canvas');
    if (!ctx) return;

    const labels = data.map(d => formatDate(d.date));
    const impressions = data.map(d => d.impressions);
    const clicks = data.map(d => d.clicks);

    new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Impresiones',
                    data: impressions,
                    borderColor: '#3b82f6',
                    backgroundColor: '#3b82f620',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                },
                {
                    label: 'Clics',
                    data: clicks,
                    borderColor: '#22c55e',
                    backgroundColor: '#22c55e20',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                    yAxisID: 'y1',
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top', labels: { usePointStyle: true, font: { size: 11 } } },
                tooltip: {
                    backgroundColor: '#1e293b',
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${formatNumber(ctx.parsed.y)}`,
                    },
                },
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10 }, maxTicksLimit: 10 } },
                y: {
                    grid: { color: '#1e293b' },
                    ticks: { callback: v => formatNumber(v), font: { size: 10 } },
                },
                y1: {
                    position: 'right',
                    grid: { display: false },
                    ticks: { callback: v => formatNumber(v), font: { size: 10 } },
                },
            },
        },
    });
}

function renderDiscoverStats(data) {
    const stats = document.getElementById('discover-stats');
    if (!stats || !data || data.length === 0) {
        if (stats) stats.innerHTML = '<div class="alert alert-info">No hay datos para mostrar</div>';
        return;
    }

    const totalImpressions = data.reduce((s, d) => s + d.impressions, 0);
    const totalClicks = data.reduce((s, d) => s + d.clicks, 0);
    const avgCtr = totalImpressions > 0 ? (totalClicks / totalImpressions * 100) : 0;

    stats.innerHTML = `
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">Total Impresiones (30d)</span>
                <span class="kpi-card-icon">👁️</span>
            </div>
            <div class="kpi-card-value">${formatNumber(totalImpressions)}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">Total Clics (30d)</span>
                <span class="kpi-card-icon">🖱️</span>
            </div>
            <div class="kpi-card-value">${formatNumber(totalClicks)}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">CTR Promedio</span>
                <span class="kpi-card-icon">📈</span>
            </div>
            <div class="kpi-card-value">${avgCtr.toFixed(2)}%</div>
        </div>
    `;
}

async function renderDiscoverCompetitorTable(competitors) {
    const table = document.getElementById('discover-table-body');
    if (!table) return;

    const rows = await Promise.all(competitors
        .filter(c => c.is_us)
        .map(async c => {
            try {
                const data = await API.getDiscoverData(c.id, 7);
                const totalClicks = data.reduce((s, d) => s + d.clicks, 0);
                const totalImpressions = data.reduce((s, d) => s + d.impressions, 0);
                return {
                    name: c.name,
                    color: c.color,
                    impressions: totalImpressions,
                    clicks: totalClicks,
                    ctr: totalImpressions > 0 ? (totalClicks / totalImpressions * 100) : 0,
                };
            } catch {
                return { name: c.name, color: c.color, impressions: 0, clicks: 0, ctr: 0 };
            }
        }));

    table.innerHTML = rows.map(r => `
        <tr>
            <td>
                <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
                    background:${r.color};margin-right:8px;"></span>
                ${r.name}
            </td>
            <td>${formatNumber(r.impressions)}</td>
            <td>${formatNumber(r.clicks)}</td>
            <td>${r.ctr.toFixed(2)}%</td>
        </tr>
    `).join('');
}


// ══════════════════════════════════════════════════════════════
// SEARCH TRAFFIC PAGE
// ══════════════════════════════════════════════════════════════

async function initSearchTraffic() {
    showLoading('search-chart');
    showLoading('search-stats');
    try {
        const competitors = await API.getCompetitors();
        const us = competitors.filter(c => c.is_us);
        if (us.length > 0) {
            const data = await API.getSearchData(us[0].id, 30);
            renderSearchChart(data, us[0].name);
            renderSearchStats(data);
        }
    } catch (error) {
        document.getElementById('search-chart').innerHTML = `
            <div class="alert alert-danger">⚠️ ${error.message}</div>`;
    }
}

function renderSearchChart(data, name) {
    const canvas = document.getElementById('search-chart');
    if (!canvas) return;

    if (!data || data.length === 0) {
        canvas.innerHTML = '<div class="alert alert-info">💡 No hay datos de Search Console aún.</div>';
        return;
    }

    canvas.innerHTML = '<canvas id="search-canvas" height="300"></canvas>';
    const ctx = document.getElementById('search-canvas');
    if (!ctx) return;

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => formatDate(d.date)),
            datasets: [
                {
                    label: 'Clics',
                    data: data.map(d => d.clicks),
                    borderColor: '#22c55e',
                    backgroundColor: '#22c55e20',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.3,
                },
                {
                    label: 'Impresiones',
                    data: data.map(d => d.impressions),
                    borderColor: '#3b82f6',
                    backgroundColor: '#3b82f620',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.3,
                    yAxisID: 'y1',
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top', labels: { usePointStyle: true, font: { size: 11 } } },
                tooltip: {
                    backgroundColor: '#1e293b',
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${formatNumber(ctx.parsed.y)}`,
                    },
                },
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10 }, maxTicksLimit: 10 } },
                y: {
                    grid: { color: '#1e293b' },
                    ticks: { callback: v => formatNumber(v), font: { size: 10 } },
                },
                y1: {
                    position: 'right',
                    grid: { display: false },
                    ticks: { callback: v => formatNumber(v), font: { size: 10 } },
                },
            },
        },
    });
}

function renderSearchStats(data) {
    const stats = document.getElementById('search-stats');
    if (!stats || !data || data.length === 0) {
        if (stats) stats.innerHTML = '<div class="alert alert-info">No hay datos</div>';
        return;
    }

    const totalClicks = data.reduce((s, d) => s + d.clicks, 0);
    const totalImpressions = data.reduce((s, d) => s + d.impressions, 0);
    const avgPosition = data.reduce((s, d) => s + d.avg_position, 0) / data.length;
    const avgCtr = totalImpressions > 0 ? (totalClicks / totalImpressions * 100) : 0;

    stats.innerHTML = `
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">Clics (30d)</span>
                <span class="kpi-card-icon">🖱️</span>
            </div>
            <div class="kpi-card-value">${formatNumber(totalClicks)}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">Impresiones (30d)</span>
                <span class="kpi-card-icon">👁️</span>
            </div>
            <div class="kpi-card-value">${formatNumber(totalImpressions)}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">CTR</span>
                <span class="kpi-card-icon">📈</span>
            </div>
            <div class="kpi-card-value">${avgCtr.toFixed(2)}%</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-card-header">
                <span class="kpi-card-label">Posición Promedio</span>
                <span class="kpi-card-icon">🎯</span>
            </div>
            <div class="kpi-card-value">${avgPosition.toFixed(1)}</div>
        </div>
    `;
}


// ══════════════════════════════════════════════════════════════
// MANUAL ENTRY PAGE
// ══════════════════════════════════════════════════════════════

async function initManualEntry() {
    try {
        const competitors = await API.getCompetitors();

        // Populate competitor select
        const compSelect = document.getElementById('entry-competitor');
        if (compSelect) {
            compSelect.innerHTML = competitors.map(c => `
                <option value="${c.id}">${c.name}</option>
            `).join('');
        }

        // Populate filter selects
        const filterComp = document.getElementById('filter-competitor');
        if (filterComp) {
            filterComp.innerHTML = `
                <option value="">Todos</option>
                ${competitors.map(c => `<option value="${c.id}">${c.name}</option>`).join('')}
            `;
        }

        // Bind form submit
        const form = document.getElementById('manual-entry-form');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = {
                    competitor_id: parseInt(document.getElementById('entry-competitor').value),
                    category: document.getElementById('entry-category').value,
                    metric_name: document.getElementById('entry-metric').value,
                    metric_value: parseFloat(document.getElementById('entry-value').value) || null,
                    metric_text: document.getElementById('entry-text').value || null,
                    entry_date: document.getElementById('entry-date').value,
                    notes: document.getElementById('entry-notes').value || null,
                };
                try {
                    await API.createManualEntry(data);
                    showToast('✅ Dato registrado exitosamente', 'success');
                    form.reset();
                    document.getElementById('entry-date').value = new Date().toISOString().split('T')[0];
                    loadManualEntries();
                } catch (error) {
                    showToast('❌ Error: ' + error.message, 'error');
                }
            });
        }

        // Set today's date
        const dateInput = document.getElementById('entry-date');
        if (dateInput) {
            dateInput.value = new Date().toISOString().split('T')[0];
        }

        // Bind filter
        const filterBtn = document.getElementById('filter-btn');
        if (filterBtn) {
            filterBtn.addEventListener('click', loadManualEntries);
        }

        await loadManualEntries();
    } catch (error) {
        console.error('Manual entry init error:', error);
    }
}

async function loadManualEntries() {
    const tbody = document.getElementById('manual-entries-table');
    if (!tbody) return;

    const params = {};
    const filterComp = document.getElementById('filter-competitor');
    const filterCat = document.getElementById('filter-category');

    if (filterComp?.value) params.competitor_id = parseInt(filterComp.value);
    if (filterCat?.value) params.category = filterCat.value;

    try {
        const entries = await API.getManualEntries(params);
        const competitors = await API.getCompetitors();
        const compMap = {};
        competitors.forEach(c => compMap[c.id] = c);

        if (entries.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No hay entradas manuales aún</td></tr>';
            return;
        }

        tbody.innerHTML = entries.slice(0, 50).map(e => `
            <tr>
                <td>${compMap[e.competitor_id]?.name || '—'}</td>
                <td><span class="competitor-badge badge-competitor">${e.category}</span></td>
                <td>${e.metric_name}</td>
                <td>${e.metric_value !== null ? formatNumber(e.metric_value) : e.metric_text || '—'}</td>
                <td>${formatDate(e.entry_date)}</td>
            </tr>
        `).join('');
    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="5" class="alert alert-danger">⚠️ ${error.message}</td></tr>`;
    }
}
