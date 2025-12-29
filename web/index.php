<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Noisy Pi - Ambient Noise Monitor</title>
    <link rel="stylesheet" href="css/style.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
</head>
<body>
    <header class="main-header">
        <div class="header-content">
            <h1 class="logo">
                <span class="logo-icon">📊</span>
                Noisy Pi
            </h1>
            <nav class="main-nav">
                <a href="#" class="nav-link active" data-view="dashboard">Dashboard</a>
                <a href="#" class="nav-link" data-view="spectrogram">Spectrogram</a>
                <a href="#" class="nav-link" data-view="anomalies">Anomalies</a>
                <a href="#" class="nav-link" data-view="settings">Settings</a>
            </nav>
            <div class="status-indicator">
                <span class="status-dot" id="statusDot"></span>
                <span class="status-text" id="statusText">Checking...</span>
            </div>
        </div>
    </header>

    <main class="main-content">
        <!-- Dashboard View -->
        <section class="view active" id="dashboardView">
            <div class="controls-bar">
                <div class="time-controls">
                    <button class="time-btn active" data-hours="1">1h</button>
                    <button class="time-btn" data-hours="6">6h</button>
                    <button class="time-btn" data-hours="24">24h</button>
                    <button class="time-btn" data-hours="168">7d</button>
                </div>
                <div class="date-picker">
                    <input type="datetime-local" id="startTime">
                    <span>to</span>
                    <input type="datetime-local" id="endTime">
                    <button class="btn" id="applyDateRange">Apply</button>
                </div>
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Average Level</div>
                    <div class="stat-value" id="statAvgLevel">-- dB</div>
                    <div class="stat-sublabel">LAeq</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Maximum</div>
                    <div class="stat-value" id="statMaxLevel">-- dB</div>
                    <div class="stat-sublabel">Peak level</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Background</div>
                    <div class="stat-value" id="statL90">-- dB</div>
                    <div class="stat-sublabel">L90</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Events</div>
                    <div class="stat-value" id="statEvents">--</div>
                    <div class="stat-sublabel">Sound events</div>
                </div>
                <div class="stat-card highlight">
                    <div class="stat-label">Anomalies</div>
                    <div class="stat-value" id="statAnomalies">--</div>
                    <div class="stat-sublabel">Unusual sounds</div>
                </div>
            </div>

            <div class="chart-container">
                <h3>Sound Levels Over Time</h3>
                <canvas id="levelsChart"></canvas>
            </div>

            <div class="chart-row">
                <div class="chart-container half">
                    <h3>Spectral Centroid (Brightness)</h3>
                    <canvas id="centroidChart"></canvas>
                </div>
                <div class="chart-container half">
                    <h3>Hourly Statistics</h3>
                    <canvas id="hourlyChart"></canvas>
                </div>
            </div>
        </section>

        <!-- Spectrogram View -->
        <section class="view" id="spectrogramView">
            <div class="controls-bar">
                <div class="time-controls">
                    <button class="time-btn spec-time active" data-hours="1">1h</button>
                    <button class="time-btn spec-time" data-hours="3">3h</button>
                    <button class="time-btn spec-time" data-hours="6">6h</button>
                    <button class="time-btn spec-time" data-hours="12">12h</button>
                </div>
                <div class="spec-controls">
                    <label>
                        Color Scale:
                        <select id="colorScale">
                            <option value="viridis">Viridis</option>
                            <option value="inferno">Inferno</option>
                            <option value="grayscale">Grayscale</option>
                        </select>
                    </label>
                </div>
            </div>

            <div class="spectrogram-container">
                <div class="spectrogram-wrapper">
                    <div class="freq-axis" id="freqAxis"></div>
                    <canvas id="spectrogramCanvas"></canvas>
                </div>
                <div class="time-axis" id="timeAxis"></div>
                <div class="color-legend" id="colorLegend"></div>
            </div>

            <div class="spectrogram-info">
                <p>Hover over the spectrogram to see details. Click to annotate.</p>
                <div id="spectrogramTooltip" class="tooltip"></div>
            </div>
        </section>

        <!-- Anomalies View -->
        <section class="view" id="anomaliesView">
            <div class="controls-bar">
                <div class="anomaly-controls">
                    <label>
                        Threshold:
                        <input type="number" id="anomalyThreshold" value="2.0" step="0.1" min="0.5" max="10">
                    </label>
                    <button class="btn" id="refreshAnomalies">Refresh</button>
                </div>
            </div>

            <div class="anomaly-list" id="anomalyList">
                <p class="loading">Loading anomalies...</p>
            </div>
        </section>

        <!-- Settings View -->
        <section class="view" id="settingsView">
            <div class="settings-container">
                <h2>Settings</h2>
                
                <div class="settings-section">
                    <h3>Anomaly Audio Snippets</h3>
                    <p class="settings-description">
                        When enabled, short audio clips are saved when anomalies are detected.
                        This helps identify what caused the anomaly.
                    </p>
                    
                    <div class="setting-row">
                        <label class="toggle-label">
                            <input type="checkbox" id="enableSnippets">
                            <span class="toggle-switch"></span>
                            Enable audio snippets
                        </label>
                    </div>
                    
                    <div class="setting-row">
                        <label>
                            Snippet threshold (anomaly score):
                            <input type="number" id="snippetThreshold" value="2.5" step="0.1" min="1.0" max="5.0">
                        </label>
                        <span class="setting-hint">Only save snippets for anomalies above this score</span>
                    </div>
                    
                    <div class="setting-row">
                        <label>
                            Snippet duration (seconds):
                            <select id="snippetDuration">
                                <option value="3">3 seconds</option>
                                <option value="5" selected>5 seconds</option>
                                <option value="10">10 seconds</option>
                            </select>
                        </label>
                    </div>
                    
                    <button class="btn btn-primary" id="saveSettings">Save Settings</button>
                    <span class="settings-note" id="settingsNote"></span>
                </div>
                
                <div class="settings-section">
                    <h3>Saved Snippets</h3>
                    <div class="snippet-stats">
                        <span id="snippetCount">-- snippets</span>
                        <span id="snippetSize">-- MB</span>
                    </div>
                    <div class="snippet-list" id="snippetList">
                        <p class="loading">Loading snippets...</p>
                    </div>
                </div>
            </div>
        </section>
    </main>

    <!-- Annotation Modal -->
    <div class="modal" id="annotationModal">
        <div class="modal-content">
            <h3>Annotate Measurement</h3>
            <p class="modal-info" id="annotationInfo"></p>
            <textarea id="annotationText" placeholder="Enter annotation..."></textarea>
            <div class="modal-buttons">
                <button class="btn btn-secondary" id="cancelAnnotation">Cancel</button>
                <button class="btn btn-primary" id="saveAnnotation">Save</button>
            </div>
        </div>
    </div>

    <script src="js/spectrogram.js"></script>
    <script src="js/charts.js"></script>
    <script src="js/app.js"></script>
</body>
</html>

