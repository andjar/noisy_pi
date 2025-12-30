/**
 * Noisy Pi Dashboard Application - Enhanced Version
 */

// State
let chartManager = null;
let heatmapRenderer = null;
let spectrogramRenderer = null;
let baselineRenderer = null;
let refreshInterval = null;
let currentData = [];
let selectedMeasurement = null;
let config = {};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    // Setup tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });
    
    // Setup period buttons
    document.querySelectorAll('.btn-period').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.btn-period').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadStatistics(btn.dataset.period);
        });
    });
    
    // Setup time range change
    document.getElementById('time-range').addEventListener('change', loadData);
    document.getElementById('spectrogram-range')?.addEventListener('change', loadSpectrogramData);
    document.getElementById('colormap-select')?.addEventListener('change', updateColormap);
    
    // Setup date pickers
    const today = new Date().toISOString().split('T')[0];
    const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    document.getElementById('history-start').value = weekAgo;
    document.getElementById('history-end').value = today;
    
    // Initialize renderers
    chartManager = new ChartManager();
    heatmapRenderer = new HeatmapRenderer('heatmap-canvas');
    spectrogramRenderer = new SpectrogramRenderer('spectrogram-full-canvas');
    baselineRenderer = new BaselineRenderer('baseline-canvas');
    
    // Load config
    await loadConfig();
    
    // Initial data load
    loadData();
    loadStatistics('today');
    loadBaseline();
    
    // Setup auto-refresh
    setupRefresh();
    
    updateStatus('connected');
});

// Tab switching
function switchTab(tabId) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    
    document.querySelector(`.tab[data-tab="${tabId}"]`).classList.add('active');
    document.getElementById(`tab-${tabId}`).classList.add('active');
    
    // Load data for specific tabs
    if (tabId === 'spectrogram') {
        loadSpectrogramData();
    } else if (tabId === 'statistics') {
        loadStatistics('today');
        loadBaseline();
    }
}

// Status updates
function updateStatus(status) {
    const badge = document.getElementById('status-badge');
    if (status === 'connected') {
        badge.textContent = 'Live';
        badge.className = 'status-badge status-connected';
    } else if (status === 'error') {
        badge.textContent = 'Error';
        badge.className = 'status-badge status-error';
    } else {
        badge.textContent = 'Connecting...';
        badge.className = 'status-badge';
    }
}

// Setup refresh interval
function setupRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    const interval = parseInt(config.refresh_interval || 30) * 1000;
    if (interval > 0) {
        refreshInterval = setInterval(loadData, interval);
    }
}

// Load config
async function loadConfig() {
    try {
        const res = await fetch('api.php?action=config');
        config = await res.json();
    } catch (err) {
        console.error('Error loading config:', err);
        config = {};
    }
}

// Load all data
async function loadData() {
    try {
        const timeRange = document.getElementById('time-range').value;
        const limit = getLimit(timeRange);
        
        await Promise.all([
            loadStats(),
            loadChartData(limit),
            loadRecentData(),
            loadSnippets(),
            loadHourlyStats()
        ]);
        
        document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
        updateStatus('connected');
    } catch (err) {
        console.error('Error loading data:', err);
        updateStatus('error');
    }
}

function getLimit(timeRange) {
    switch (timeRange) {
        case '1h': return 120;
        case '6h': return 720;
        case '24h': return 2880;
        case '7d': return 20160;
        default: return 500;
    }
}

// Load statistics
async function loadStats() {
    try {
        const [statsRes, anomalyRes] = await Promise.all([
            fetch('api.php?action=stats&period=1h'),
            fetch('api.php?action=today_anomalies')
        ]);
        
        const stats = await statsRes.json();
        const anomalies = await anomalyRes.json();
        
        if (stats.data) {
            document.getElementById('current-level').textContent = 
                stats.data.avg_db !== null ? parseFloat(stats.data.avg_db).toFixed(1) : '--';
            document.getElementById('max-level').textContent = 
                stats.data.max_db !== null ? parseFloat(stats.data.max_db).toFixed(1) : '--';
            document.getElementById('min-level').textContent = 
                stats.data.min_db !== null ? parseFloat(stats.data.min_db).toFixed(1) : '--';
            document.getElementById('silence-pct').textContent = 
                stats.data.avg_silence !== null ? parseFloat(stats.data.avg_silence).toFixed(0) : '--';
            document.getElementById('centroid-hz').textContent = 
                stats.data.avg_centroid !== null ? Math.round(parseFloat(stats.data.avg_centroid)) : '--';
            document.getElementById('measurement-count').textContent = stats.data.count || 0;
        }
        
        const anomalyCount = anomalies.count || 0;
        document.getElementById('anomaly-count').textContent = anomalyCount;
        
        const anomalyCard = document.querySelector('.anomaly-card');
        if (anomalyCard) {
            anomalyCard.classList.toggle('has-anomalies', anomalyCount > 0);
        }
    } catch (err) {
        console.error('Error loading stats:', err);
    }
}

// Load chart data
async function loadChartData(limit) {
    try {
        const res = await fetch(`api.php?action=recent&limit=${limit}`);
        const json = await res.json();
        
        if (!json.data || json.data.length === 0) {
            return;
        }
        
        currentData = json.data;
        
        chartManager.updateLevelsChart(currentData);
        chartManager.updateAnomalyChart(currentData);
        heatmapRenderer.render(currentData);
    } catch (err) {
        console.error('Error loading chart data:', err);
    }
}

// Load recent measurements table
async function loadRecentData() {
    try {
        const res = await fetch('api.php?action=recent&limit=25');
        const json = await res.json();
        
        const tbody = document.getElementById('recent-tbody');
        
        if (!json.data || json.data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="no-data">No data yet. Waiting for measurements...</td></tr>';
            return;
        }
        
        tbody.innerHTML = json.data.map(row => {
            // Calculate 3-band simplified view from 7 bands
            const bandLow = avgBands(row.band_0_200, row.band_200_500);
            const bandMid = avgBands(row.band_500_1k, row.band_1k_2k, row.band_2k_4k);
            const bandHigh = avgBands(row.band_4k_8k, row.band_8k_24k);
            
            return `
                <tr class="${parseFloat(row.anomaly_score) >= 2.5 ? 'anomaly-row' : ''}" data-id="${row.id}">
                    <td>${formatDateTime(row.timestamp)}</td>
                    <td><strong>${formatDb(row.mean_db)}</strong></td>
                    <td>${formatDb(row.max_db)}</td>
                    <td>${formatHz(row.spectral_centroid)}</td>
                    <td>${row.silence_pct !== null ? parseFloat(row.silence_pct).toFixed(0) + '%' : '-'}</td>
                    <td>${getAnomalyBadge(row.anomaly_score)}</td>
                    <td>
                        <input type="text" class="annotation-input" 
                               value="${escapeHtml(row.annotation || '')}" 
                               data-id="${row.id}"
                               placeholder="Add note..."
                               onchange="saveAnnotation(${row.id}, this.value)">
                    </td>
                    <td>
                        <button class="btn-small" onclick="viewDetail(${row.id})" title="View Details">🔍</button>
                        <button class="btn-small" onclick="openAnnotationModal(${row.id}, '${escapeHtml(row.annotation || '')}', '${row.timestamp}')" title="Edit Annotation">✏️</button>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        console.error('Error loading recent data:', err);
    }
}

// Load hourly statistics
async function loadHourlyStats() {
    try {
        const res = await fetch('api.php?action=hourly_stats');
        const json = await res.json();
        
        if (json.data && json.data.length > 0) {
            chartManager.updateHourlyChart(json.data);
        }
    } catch (err) {
        console.error('Error loading hourly stats:', err);
    }
}

// Load anomaly snippets
async function loadSnippets() {
    try {
        const res = await fetch('api.php?action=snippets');
        const json = await res.json();
        
        const section = document.getElementById('anomalies-section');
        const list = document.getElementById('snippets-list');
        
        if (!json.data || json.data.length === 0) {
            section.style.display = 'none';
            return;
        }
        
        section.style.display = 'block';
        list.innerHTML = json.data.map(snippet => `
            <div class="snippet-card">
                <div class="snippet-header">
                    <span class="timestamp">${formatDateTime(snippet.timestamp)}</span>
                    <span class="anomaly-badge anomaly-high">${parseFloat(snippet.anomaly_score).toFixed(1)}</span>
                </div>
                <audio controls src="${snippet.url}" preload="none"></audio>
                <button class="btn-delete" onclick="deleteSnippet(${snippet.id})">Delete</button>
            </div>
        `).join('');
    } catch (err) {
        console.error('Error loading snippets:', err);
    }
}

// Load spectrogram data
async function loadSpectrogramData() {
    const range = document.getElementById('spectrogram-range')?.value || '3h';
    const limit = range === '1h' ? 120 : range === '3h' ? 360 : 720;
    
    try {
        const res = await fetch(`api.php?action=recent&limit=${limit}`);
        const json = await res.json();
        
        if (json.data && json.data.length > 0) {
            spectrogramRenderer.renderFull(json.data);
        }
    } catch (err) {
        console.error('Error loading spectrogram data:', err);
    }
}

// Load statistics for period
async function loadStatistics(period) {
    let periodParam;
    switch (period) {
        case 'today': periodParam = '24h'; break;
        case 'week': periodParam = '7d'; break;
        case 'month': periodParam = '30d'; break;
        case 'all': periodParam = 'all'; break;
        default: periodParam = '24h';
    }
    
    try {
        const res = await fetch(`api.php?action=stats&period=${periodParam}`);
        const json = await res.json();
        
        if (json.data) {
            const d = json.data;
            document.getElementById('stats-cards').innerHTML = `
                <div class="stat-card">
                    <span class="stat-label">Average Level</span>
                    <span class="stat-value">${d.avg_db ? parseFloat(d.avg_db).toFixed(1) : '--'}</span>
                    <span class="stat-unit">dB</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Max Level</span>
                    <span class="stat-value">${d.max_db ? parseFloat(d.max_db).toFixed(1) : '--'}</span>
                    <span class="stat-unit">dB</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Min Level</span>
                    <span class="stat-value">${d.min_db ? parseFloat(d.min_db).toFixed(1) : '--'}</span>
                    <span class="stat-unit">dB</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Avg Centroid</span>
                    <span class="stat-value">${d.avg_centroid ? Math.round(parseFloat(d.avg_centroid)) : '--'}</span>
                    <span class="stat-unit">Hz</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Measurements</span>
                    <span class="stat-value">${d.count || 0}</span>
                    <span class="stat-unit">samples</span>
                </div>
                <div class="stat-card anomaly-card ${(d.anomalies || 0) > 0 ? 'has-anomalies' : ''}">
                    <span class="stat-label">Anomalies</span>
                    <span class="stat-value">${d.anomalies || 0}</span>
                    <span class="stat-unit">detected</span>
                </div>
            `;
        }
    } catch (err) {
        console.error('Error loading statistics:', err);
    }
}

// Load baseline data
async function loadBaseline() {
    try {
        const res = await fetch('api.php?action=baseline');
        const json = await res.json();
        
        if (json.data && json.data.length > 0) {
            baselineRenderer.render(json.data);
        }
    } catch (err) {
        console.error('Error loading baseline:', err);
    }
}

// Load history data
async function loadHistoryData() {
    const start = document.getElementById('history-start').value;
    const end = document.getElementById('history-end').value;
    
    if (!start || !end) {
        alert('Please select date range');
        return;
    }
    
    try {
        const res = await fetch(`api.php?action=range&start=${start}&end=${end}`);
        const json = await res.json();
        
        if (json.data && json.data.length > 0) {
            chartManager.updateHistoryChart(json.data);
            
            const tbody = document.getElementById('history-tbody');
            tbody.innerHTML = json.data.slice(0, 100).map(row => `
                <tr class="${parseFloat(row.anomaly_score) >= 2.5 ? 'anomaly-row' : ''}">
                    <td>${formatDateTime(row.timestamp)}</td>
                    <td>${formatDb(row.mean_db)}</td>
                    <td>${formatDb(row.max_db)}</td>
                    <td>${formatDb(row.band_0_200)}</td>
                    <td>${formatDb(row.band_200_500)}</td>
                    <td>${formatDb(row.band_500_1k)}</td>
                    <td>${formatDb(row.band_1k_2k)}</td>
                    <td>${formatDb(row.band_2k_4k)}</td>
                    <td>${formatDb(row.band_4k_8k)}</td>
                    <td>${formatDb(row.band_8k_24k)}</td>
                    <td>${getAnomalyBadge(row.anomaly_score)}</td>
                    <td>${escapeHtml(row.annotation || '-')}</td>
                </tr>
            `).join('');
        } else {
            alert('No data found for selected range');
        }
    } catch (err) {
        console.error('Error loading history:', err);
    }
}

// View measurement detail
async function viewDetail(id) {
    switchTab('spectrogram');
    
    try {
        const res = await fetch(`api.php?action=spectrogram&id=${id}`);
        const json = await res.json();
        
        if (json.data) {
            selectedMeasurement = { id, ...json };
            
            document.getElementById('detail-section').style.display = 'block';
            document.getElementById('detail-timestamp').textContent = formatDateTime(json.timestamp);
            
            // Render spectrum
            const canvas = document.getElementById('detail-spectrum-canvas');
            renderSpectrumBar(canvas, json.data);
            
            // Get full measurement data
            const measureRes = await fetch(`api.php?action=recent&limit=1000`);
            const measureJson = await measureRes.json();
            const measurement = measureJson.data.find(m => m.id === id);
            
            if (measurement) {
                document.getElementById('detail-mean').textContent = formatDb(measurement.mean_db) + ' dB';
                document.getElementById('detail-max').textContent = formatDb(measurement.max_db) + ' dB';
                document.getElementById('detail-centroid').textContent = formatHz(measurement.spectral_centroid);
                document.getElementById('detail-flatness').textContent = measurement.spectral_flatness ? parseFloat(measurement.spectral_flatness).toFixed(3) : '-';
                document.getElementById('detail-dominant').textContent = formatHz(measurement.dominant_freq);
                document.getElementById('detail-anomaly').textContent = measurement.anomaly_score ? parseFloat(measurement.anomaly_score).toFixed(2) : '-';
                document.getElementById('detail-annotation').value = measurement.annotation || '';
            }
        }
    } catch (err) {
        console.error('Error loading detail:', err);
    }
}

// Render spectrum bar chart
function renderSpectrumBar(canvas, data) {
    const ctx = canvas.getContext('2d');
    const width = canvas.width = canvas.parentElement.clientWidth;
    const height = canvas.height = 200;
    
    ctx.fillStyle = '#0a0e14';
    ctx.fillRect(0, 0, width, height);
    
    if (!data || data.length === 0) return;
    
    // Average all snapshots
    const avgSpectrum = data[0].map((_, i) => {
        const sum = data.reduce((acc, snapshot) => acc + (snapshot[i] || -90), 0);
        return sum / data.length;
    });
    
    const barWidth = width / avgSpectrum.length;
    const maxDb = 0;
    const minDb = -90;
    
    avgSpectrum.forEach((db, i) => {
        const normalized = (db - minDb) / (maxDb - minDb);
        const barHeight = normalized * height;
        
        // Color based on frequency
        const hue = (i / avgSpectrum.length) * 240;
        ctx.fillStyle = `hsl(${hue}, 70%, 50%)`;
        ctx.fillRect(i * barWidth, height - barHeight, barWidth - 1, barHeight);
    });
}

// Save annotation
async function saveAnnotation(id, text) {
    try {
        await fetch('api.php?action=annotate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, annotation: text })
        });
    } catch (err) {
        console.error('Error saving annotation:', err);
    }
}

// Save detail annotation
async function saveDetailAnnotation() {
    if (!selectedMeasurement) return;
    
    const text = document.getElementById('detail-annotation').value;
    await saveAnnotation(selectedMeasurement.id, text);
    alert('Annotation saved');
}

// Delete snippet
async function deleteSnippet(id) {
    if (!confirm('Delete this audio snippet?')) return;
    
    try {
        await fetch('api.php?action=delete_snippet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        loadSnippets();
    } catch (err) {
        console.error('Error deleting snippet:', err);
    }
}

// Export data
async function exportData(format) {
    const timeRange = document.getElementById('time-range').value;
    const limit = getLimit(timeRange);
    
    try {
        const res = await fetch(`api.php?action=recent&limit=${limit}`);
        const json = await res.json();
        
        if (json.data && json.data.length > 0) {
            downloadCSV(json.data, `noisy_pi_${timeRange}.csv`);
        }
    } catch (err) {
        console.error('Error exporting data:', err);
    }
}

// Export history data
async function exportHistoryData() {
    const start = document.getElementById('history-start').value;
    const end = document.getElementById('history-end').value;
    
    try {
        const res = await fetch(`api.php?action=range&start=${start}&end=${end}`);
        const json = await res.json();
        
        if (json.data && json.data.length > 0) {
            downloadCSV(json.data, `noisy_pi_${start}_${end}.csv`);
        }
    } catch (err) {
        console.error('Error exporting history:', err);
    }
}

// Download CSV helper
function downloadCSV(data, filename) {
    const headers = Object.keys(data[0]).filter(k => k !== 'spectrogram');
    const csv = [
        headers.join(','),
        ...data.map(row => headers.map(h => JSON.stringify(row[h] ?? '')).join(','))
    ].join('\n');
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

// Update colormap
function updateColormap() {
    const colormap = document.getElementById('colormap-select').value;
    spectrogramRenderer.setColormap(colormap);
    heatmapRenderer.setColormap(colormap);
    loadSpectrogramData();
}

// Settings modal
function openSettings() {
    document.getElementById('setting-threshold').value = config.anomaly_threshold || 2.5;
    document.getElementById('setting-snippets').checked = config.snippet_enabled || false;
    document.getElementById('setting-snippet-duration').value = config.snippet_duration || 5;
    document.getElementById('setting-refresh').value = config.refresh_interval || 30;
    document.getElementById('settings-modal').classList.add('open');
}

function closeSettings() {
    document.getElementById('settings-modal').classList.remove('open');
}

async function saveSettings() {
    const newConfig = {
        anomaly_threshold: parseFloat(document.getElementById('setting-threshold').value),
        snippet_enabled: document.getElementById('setting-snippets').checked,
        snippet_duration: parseInt(document.getElementById('setting-snippet-duration').value),
        refresh_interval: parseInt(document.getElementById('setting-refresh').value)
    };
    
    try {
        await fetch('api.php?action=save_config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newConfig)
        });
        
        config = { ...config, ...newConfig };
        setupRefresh();
        closeSettings();
        alert('Settings saved. Restart capture daemon for changes to take effect.');
    } catch (err) {
        console.error('Error saving settings:', err);
        alert('Failed to save settings');
    }
}

// Annotation modal
let annotationId = null;

function openAnnotationModal(id, text, timestamp) {
    annotationId = id;
    document.getElementById('annotation-timestamp').textContent = formatDateTime(timestamp);
    document.getElementById('annotation-text').value = text;
    document.getElementById('annotation-modal').classList.add('open');
}

function closeAnnotation() {
    document.getElementById('annotation-modal').classList.remove('open');
    annotationId = null;
}

async function saveAnnotationModal() {
    if (!annotationId) return;
    
    const text = document.getElementById('annotation-text').value;
    await saveAnnotation(annotationId, text);
    closeAnnotation();
    loadRecentData();
}

// Utility functions
function formatDb(value) {
    if (value === null || value === undefined) return '-';
    return parseFloat(value).toFixed(1);
}

function formatHz(value) {
    if (value === null || value === undefined) return '-';
    const hz = parseFloat(value);
    if (hz >= 1000) return (hz / 1000).toFixed(1) + 'k';
    return Math.round(hz) + ' Hz';
}

function formatDateTime(timestamp) {
    if (!timestamp) return '-';
    
    // Handle format like "20251230_165954" (YYYYMMDD_HHMMSS)
    if (/^\d{8}_\d{6}$/.test(timestamp)) {
        const year = timestamp.substring(0, 4);
        const month = timestamp.substring(4, 6);
        const day = timestamp.substring(6, 8);
        const hour = timestamp.substring(9, 11);
        const minute = timestamp.substring(11, 13);
        const second = timestamp.substring(13, 15);
        timestamp = `${year}-${month}-${day}T${hour}:${minute}:${second}`;
    }
    
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return timestamp; // Return original if parsing fails
    
    return date.toLocaleString([], { 
        month: 'short', 
        day: 'numeric', 
        hour: '2-digit', 
        minute: '2-digit' 
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getAnomalyBadge(score) {
    if (score === null || score === undefined) return '-';
    
    const s = parseFloat(score);
    let cls = 'anomaly-low';
    if (s >= 2.5) cls = 'anomaly-high';
    else if (s >= 1.5) cls = 'anomaly-medium';
    
    return `<span class="anomaly-badge ${cls}">${s.toFixed(2)}</span>`;
}

// Average multiple band values (for simplified 3-band view)
function avgBands(...values) {
    const valid = values.filter(v => v !== null && v !== undefined && !isNaN(parseFloat(v)));
    if (valid.length === 0) return null;
    return valid.reduce((a, b) => parseFloat(a) + parseFloat(b), 0) / valid.length;
}
