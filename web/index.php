<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Noisy Pi - Ambient Noise Monitor</title>
    <link rel="stylesheet" href="css/style.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
</head>
<body>
    <header>
        <div class="header-left">
            <h1>Noisy Pi</h1>
            <span class="subtitle">Ambient Noise Monitor</span>
        </div>
        <div class="header-right">
            <span class="status-badge" id="status-badge">Connecting...</span>
            <button class="btn-icon" onclick="openSettings()" title="Settings">⚙️</button>
        </div>
    </header>
    
    <nav class="tabs">
        <button class="tab active" data-tab="dashboard">Dashboard</button>
        <button class="tab" data-tab="spectrogram">Spectrogram</button>
        <button class="tab" data-tab="statistics">Statistics</button>
        <button class="tab" data-tab="history">History</button>
    </nav>
    
    <main>
        <!-- Dashboard Tab -->
        <div id="tab-dashboard" class="tab-content active">
            <!-- Stats Overview -->
            <section class="stats-grid">
                <div class="stat-card">
                    <span class="stat-label">Current Level</span>
                    <span class="stat-value" id="current-level">--</span>
                    <span class="stat-unit">dB</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Max (1h)</span>
                    <span class="stat-value" id="max-level">--</span>
                    <span class="stat-unit">dB</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Min (1h)</span>
                    <span class="stat-value" id="min-level">--</span>
                    <span class="stat-unit">dB</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Centroid</span>
                    <span class="stat-value" id="centroid-hz">--</span>
                    <span class="stat-unit">Hz</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Silence</span>
                    <span class="stat-value" id="silence-pct">--</span>
                    <span class="stat-unit">%</span>
                </div>
                <div class="stat-card anomaly-card">
                    <span class="stat-label">Anomalies</span>
                    <span class="stat-value" id="anomaly-count">--</span>
                    <span class="stat-unit">today</span>
                </div>
            </section>
            
            <!-- Sound Levels Chart -->
            <section class="chart-section">
                <div class="section-header">
                    <h2>Sound Levels</h2>
                    <div class="controls">
                        <select id="time-range" class="time-select">
                            <option value="1h">Last Hour</option>
                            <option value="6h">Last 6 Hours</option>
                            <option value="24h" selected>Last 24 Hours</option>
                            <option value="7d">Last 7 Days</option>
                        </select>
                        <button class="btn-small" onclick="exportData('csv')" title="Export CSV">📥</button>
                    </div>
                </div>
                <div class="chart-container">
                    <canvas id="levels-chart"></canvas>
                </div>
            </section>
            
            <!-- 7-Band Heatmap -->
            <section class="chart-section">
                <div class="section-header">
                    <h2>Frequency Bands Heatmap</h2>
                    <span class="legend-hint">Click a cell to view details</span>
                </div>
                <div class="heatmap-container">
                    <canvas id="heatmap-canvas"></canvas>
                    <div class="heatmap-labels">
                        <span>12-24k</span>
                        <span>6-12k</span>
                        <span>3-6k</span>
                        <span>1.5-3k</span>
                        <span>800-1.5k</span>
                        <span>300-800</span>
                        <span>100-300</span>
                        <span>0-100 Hz</span>
                    </div>
                </div>
                <div class="heatmap-colorbar">
                    <span>-90 dB</span>
                    <div class="colorbar-gradient"></div>
                    <span>0 dB</span>
                </div>
            </section>
            
            <!-- Anomaly Chart -->
            <section class="chart-section">
                <h2>Anomaly Detection</h2>
                <div class="chart-container">
                    <canvas id="anomaly-chart"></canvas>
                </div>
            </section>
            
            <!-- Recent Measurements -->
            <section class="recent-section">
                <div class="section-header">
                    <h2>Recent Measurements</h2>
                    <button class="btn-small" onclick="loadRecentData()">Refresh</button>
                </div>
                <div class="table-container">
                    <table id="recent-table">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Mean dB</th>
                                <th>Max</th>
                                <th>Centroid</th>
                                <th>Silence</th>
                                <th>Anomaly</th>
                                <th>Annotation</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="recent-tbody"></tbody>
                    </table>
                </div>
            </section>
            
            <!-- Anomaly Snippets -->
            <section class="anomalies-section" id="anomalies-section" style="display: none;">
                <h2>Anomaly Audio Snippets</h2>
                <p class="section-desc">Audio recordings captured when anomalies were detected</p>
                <div id="snippets-list" class="snippets-grid"></div>
            </section>
        </div>
        
        <!-- Spectrogram Tab -->
        <div id="tab-spectrogram" class="tab-content">
            <section class="chart-section full-width">
                <div class="section-header">
                    <h2>Full Spectrogram View</h2>
                    <div class="controls">
                        <select id="spectrogram-range" class="time-select">
                            <option value="1h">Last Hour</option>
                            <option value="3h" selected>Last 3 Hours</option>
                            <option value="6h">Last 6 Hours</option>
                        </select>
                        <select id="colormap-select" class="time-select">
                            <option value="viridis">Viridis</option>
                            <option value="plasma">Plasma</option>
                            <option value="inferno">Inferno</option>
                            <option value="magma">Magma</option>
                        </select>
                    </div>
                </div>
                <div class="spectrogram-full">
                    <canvas id="spectrogram-full-canvas"></canvas>
                </div>
                <div class="spectrogram-colorbar">
                    <span>-90 dB</span>
                    <div class="colorbar-gradient" id="colorbar"></div>
                    <span>0 dB</span>
                </div>
            </section>
            
            <!-- Selected Measurement Detail -->
            <section class="chart-section" id="detail-section" style="display: none;">
                <h2>Measurement Detail: <span id="detail-timestamp"></span></h2>
                <div class="detail-grid">
                    <div class="detail-spectrum">
                        <canvas id="detail-spectrum-canvas"></canvas>
                    </div>
                    <div class="detail-info">
                        <div class="detail-row"><span>Mean Level:</span><span id="detail-mean">--</span></div>
                        <div class="detail-row"><span>Max Level:</span><span id="detail-max">--</span></div>
                        <div class="detail-row"><span>Centroid:</span><span id="detail-centroid">--</span></div>
                        <div class="detail-row"><span>Flatness:</span><span id="detail-flatness">--</span></div>
                        <div class="detail-row"><span>Dominant Freq:</span><span id="detail-dominant">--</span></div>
                        <div class="detail-row"><span>Anomaly Score:</span><span id="detail-anomaly">--</span></div>
                        <textarea id="detail-annotation" placeholder="Add annotation..." rows="3"></textarea>
                        <button class="btn-primary" onclick="saveDetailAnnotation()">Save Annotation</button>
                    </div>
                </div>
            </section>
        </div>
        
        <!-- Statistics Tab -->
        <div id="tab-statistics" class="tab-content">
            <section class="stats-overview">
                <h2>Statistics Overview</h2>
                <div class="stats-period-select">
                    <button class="btn-period active" data-period="today">Today</button>
                    <button class="btn-period" data-period="week">This Week</button>
                    <button class="btn-period" data-period="month">This Month</button>
                    <button class="btn-period" data-period="all">All Time</button>
                </div>
                <div class="stats-cards" id="stats-cards">
                    <!-- Filled by JS -->
                </div>
            </section>
            
            <section class="chart-section">
                <h2>Hourly Pattern (Today)</h2>
                <div class="chart-container">
                    <canvas id="hourly-chart"></canvas>
                </div>
            </section>
            
            <section class="chart-section">
                <h2>Weekly Baseline Pattern</h2>
                <p class="section-desc">Average sound level by hour and day of week</p>
                <div class="baseline-heatmap">
                    <canvas id="baseline-canvas"></canvas>
                </div>
            </section>
        </div>
        
        <!-- History Tab -->
        <div id="tab-history" class="tab-content">
            <section class="history-controls">
                <h2>Historical Data</h2>
                <div class="date-range-picker">
                    <label>From: <input type="date" id="history-start"></label>
                    <label>To: <input type="date" id="history-end"></label>
                    <button class="btn-primary" onclick="loadHistoryData()">Load Data</button>
                    <button class="btn-secondary" onclick="exportHistoryData()">Export CSV</button>
                </div>
            </section>
            
            <section class="chart-section">
                <h2>Historical Sound Levels</h2>
                <div class="chart-container tall">
                    <canvas id="history-chart"></canvas>
                </div>
            </section>
            
            <section class="recent-section">
                <h2>Data Table</h2>
                <div class="table-container">
                    <table id="history-table">
                        <thead>
                            <tr>
                                <th>Timestamp</th>
                                <th>Mean dB</th>
                                <th>Max dB</th>
                                <th>0-200</th>
                                <th>200-500</th>
                                <th>500-1k</th>
                                <th>1k-2k</th>
                                <th>2k-4k</th>
                                <th>4k-8k</th>
                                <th>8k-24k</th>
                                <th>Anomaly</th>
                                <th>Annotation</th>
                            </tr>
                        </thead>
                        <tbody id="history-tbody"></tbody>
                    </table>
                </div>
            </section>
        </div>
    </main>
    
    <!-- Settings Modal -->
    <div id="settings-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Settings</h2>
                <button class="btn-close" onclick="closeSettings()">×</button>
            </div>
            <div class="modal-body">
                <div class="setting-group">
                    <h3>Anomaly Detection</h3>
                    <label>
                        Anomaly Threshold (Z-score):
                        <input type="number" id="setting-threshold" min="1" max="5" step="0.5" value="2.5">
                    </label>
                </div>
                <div class="setting-group">
                    <h3>Audio Snippets</h3>
                    <label class="checkbox-label">
                        <input type="checkbox" id="setting-snippets">
                        Enable anomaly audio recording
                    </label>
                    <label>
                        Snippet duration (seconds):
                        <input type="number" id="setting-snippet-duration" min="3" max="30" value="5">
                    </label>
                </div>
                <div class="setting-group">
                    <h3>Display</h3>
                    <label>
                        Auto-refresh interval:
                        <select id="setting-refresh">
                            <option value="10">10 seconds</option>
                            <option value="30" selected>30 seconds</option>
                            <option value="60">1 minute</option>
                            <option value="0">Manual only</option>
                        </select>
                    </label>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-secondary" onclick="closeSettings()">Cancel</button>
                <button class="btn-primary" onclick="saveSettings()">Save</button>
            </div>
        </div>
    </div>
    
    <!-- Annotation Modal -->
    <div id="annotation-modal" class="modal">
        <div class="modal-content modal-small">
            <div class="modal-header">
                <h2>Edit Annotation</h2>
                <button class="btn-close" onclick="closeAnnotation()">×</button>
            </div>
            <div class="modal-body">
                <p id="annotation-timestamp"></p>
                <textarea id="annotation-text" rows="4" placeholder="Enter your annotation..."></textarea>
            </div>
            <div class="modal-footer">
                <button class="btn-secondary" onclick="closeAnnotation()">Cancel</button>
                <button class="btn-primary" onclick="saveAnnotationModal()">Save</button>
            </div>
        </div>
    </div>
    
    <footer>
        <p>Noisy Pi &middot; <a href="https://github.com/andjar/noisy_pi" target="_blank">GitHub</a></p>
        <p class="footer-status">Last update: <span id="last-update">--</span> &middot; <span id="measurement-count">0</span> measurements</p>
    </footer>
    
    <script src="js/charts.js"></script>
    <script src="js/spectrogram.js"></script>
    <script src="js/app.js"></script>
</body>
</html>
