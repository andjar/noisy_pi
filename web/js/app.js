/**
 * Noisy Pi Dashboard Application
 */

// State
let chartManager = null;
let spectrogramRenderer = null;
let refreshInterval = null;
let currentData = [];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    chartManager = new ChartManager();
    spectrogramRenderer = new SpectrogramRenderer('spectrogram-canvas');
    
    // Setup event listeners
    document.getElementById('time-range').addEventListener('change', loadData);
    
    // Initial load
    loadData();
    
    // Refresh every 30 seconds
    refreshInterval = setInterval(loadData, 30000);
    
    updateStatus('connected');
});

// Update connection status
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
        case '1h': return 120;   // ~2 per minute
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
        }
        
        const anomalyCount = anomalies.count || 0;
        document.getElementById('anomaly-count').textContent = anomalyCount;
        
        // Highlight if anomalies detected
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
        
        // Update all charts
        chartManager.updateLevelsChart(currentData);
        chartManager.updateBandsChart(currentData);
        chartManager.updateAnomalyChart(currentData);
        
        // Update spectrogram
        spectrogramRenderer.renderBands(currentData);
    } catch (err) {
        console.error('Error loading chart data:', err);
    }
}

// Load recent measurements table
async function loadRecentData() {
    try {
        const res = await fetch('api.php?action=recent&limit=20');
        const json = await res.json();
        
        const tbody = document.getElementById('recent-tbody');
        
        if (!json.data || json.data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="no-data">No data yet. Waiting for measurements...</td></tr>';
            return;
        }
        
        tbody.innerHTML = json.data.map(row => `
            <tr class="${row.anomaly_score >= 2.5 ? 'anomaly-row' : ''}">
                <td>${formatDateTime(row.timestamp)}</td>
                <td>${formatDb(row.mean_db)}</td>
                <td>${formatDb(row.max_db)}</td>
                <td>${formatDb(row.band_low_db)}</td>
                <td>${formatDb(row.band_mid_db)}</td>
                <td>${formatDb(row.band_high_db)}</td>
                <td>${row.silence_pct !== null ? parseFloat(row.silence_pct).toFixed(0) + '%' : '-'}</td>
                <td>${getAnomalyBadge(row.anomaly_score)}</td>
                <td>
                    <input type="text" class="annotation-input" 
                           value="${escapeHtml(row.annotation || '')}" 
                           data-id="${row.id}"
                           placeholder="Add note..."
                           onchange="saveAnnotation(${row.id}, this.value)">
                </td>
            </tr>
        `).join('');
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
                    <span class="anomaly-badge anomaly-high">Score: ${parseFloat(snippet.anomaly_score).toFixed(1)}</span>
                </div>
                <audio controls src="${snippet.url}" preload="none"></audio>
                <button class="btn-delete" onclick="deleteSnippet(${snippet.id})">Delete</button>
            </div>
        `).join('');
    } catch (err) {
        console.error('Error loading snippets:', err);
    }
}

// Save annotation
async function saveAnnotation(id, text) {
    try {
        const res = await fetch('api.php?action=annotate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, annotation: text })
        });
        const json = await res.json();
        if (!json.success) {
            console.error('Failed to save annotation');
        }
    } catch (err) {
        console.error('Error saving annotation:', err);
    }
}

// Delete snippet
async function deleteSnippet(id) {
    if (!confirm('Delete this audio snippet?')) return;
    
    try {
        const res = await fetch('api.php?action=delete_snippet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        const json = await res.json();
        if (json.success) {
            loadSnippets();
        }
    } catch (err) {
        console.error('Error deleting snippet:', err);
    }
}

// Utility functions
function formatDb(value) {
    if (value === null || value === undefined) return '-';
    return parseFloat(value).toFixed(1);
}

function formatDateTime(timestamp) {
    const date = new Date(timestamp);
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
