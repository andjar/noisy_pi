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
        <h1>Noisy Pi</h1>
        <p class="subtitle">Ambient Noise Monitor</p>
        <span class="status-badge" id="status-badge">Connecting...</span>
    </header>
    
    <main>
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
                <select id="time-range" class="time-select">
                    <option value="1h">Last Hour</option>
                    <option value="6h">Last 6 Hours</option>
                    <option value="24h" selected>Last 24 Hours</option>
                    <option value="7d">Last 7 Days</option>
                </select>
            </div>
            <div class="chart-container">
                <canvas id="levels-chart"></canvas>
            </div>
        </section>
        
        <!-- Frequency Bands Chart -->
        <section class="chart-section">
            <h2>Frequency Bands</h2>
            <div class="chart-container">
                <canvas id="bands-chart"></canvas>
            </div>
        </section>
        
        <!-- Spectrogram -->
        <section class="chart-section">
            <h2>Spectrogram (Band View)</h2>
            <div class="spectrogram-container">
                <canvas id="spectrogram-canvas"></canvas>
            </div>
        </section>
        
        <!-- Anomaly Chart -->
        <section class="chart-section">
            <h2>Anomaly Detection</h2>
            <div class="chart-container">
                <canvas id="anomaly-chart"></canvas>
            </div>
        </section>
        
        <!-- Recent Measurements Table -->
        <section class="recent-section">
            <h2>Recent Measurements</h2>
            <div class="table-container">
                <table id="recent-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Mean</th>
                            <th>Max</th>
                            <th>Low</th>
                            <th>Mid</th>
                            <th>High</th>
                            <th>Silence</th>
                            <th>Anomaly</th>
                            <th>Annotation</th>
                        </tr>
                    </thead>
                    <tbody id="recent-tbody">
                    </tbody>
                </table>
            </div>
        </section>
        
        <!-- Anomaly Snippets -->
        <section class="anomalies-section" id="anomalies-section" style="display: none;">
            <h2>Anomaly Audio Snippets</h2>
            <p class="section-desc">Short recordings captured when anomalies were detected</p>
            <div id="snippets-list" class="snippets-grid">
            </div>
        </section>
        
        <!-- Hourly Statistics -->
        <section class="chart-section">
            <h2>Hourly Statistics (Today)</h2>
            <div class="chart-container">
                <canvas id="hourly-chart"></canvas>
            </div>
        </section>
    </main>
    
    <footer>
        <p>Noisy Pi &middot; <a href="https://github.com/andjar/noisy_pi" target="_blank">GitHub</a></p>
        <p class="footer-status">Last update: <span id="last-update">--</span></p>
    </footer>
    
    <script src="js/charts.js"></script>
    <script src="js/spectrogram.js"></script>
    <script src="js/app.js"></script>
</body>
</html>
