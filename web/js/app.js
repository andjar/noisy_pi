/**
 * Noisy Pi - Main Application
 * Handles navigation, data loading, and UI interactions
 */

class NoisyPiApp {
    constructor() {
        this.chartManager = new ChartManager();
        this.spectrogramViewer = null;
        this.currentView = 'dashboard';
        this.timeRange = {
            start: Math.floor(Date.now() / 1000) - 3600, // Last hour
            end: Math.floor(Date.now() / 1000)
        };
        this.refreshInterval = null;
        this.annotationTarget = null;
        
        this.init();
    }
    
    async init() {
        this.setupNavigation();
        this.setupTimeControls();
        this.setupAnnotationModal();
        this.setupAnomalyControls();
        this.setupSettingsControls();
        
        // Check status
        await this.updateStatus();
        
        // Load initial data
        await this.loadDashboardData();
        
        // Start auto-refresh
        this.startAutoRefresh();
        
        // Handle window resize
        window.addEventListener('resize', () => this.handleResize());
    }
    
    /**
     * Setup navigation between views
     */
    setupNavigation() {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const view = link.dataset.view;
                this.switchView(view);
            });
        });
    }
    
    /**
     * Switch to a different view
     */
    async switchView(viewName) {
        // Update nav links
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        document.querySelector(`[data-view="${viewName}"]`)?.classList.add('active');
        
        // Update views
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById(`${viewName}View`)?.classList.add('active');
        
        this.currentView = viewName;
        
        // Load view-specific data
        switch (viewName) {
            case 'dashboard':
                await this.loadDashboardData();
                break;
            case 'spectrogram':
                await this.loadSpectrogramData();
                break;
            case 'anomalies':
                await this.loadAnomalies();
                break;
            case 'settings':
                await this.loadSettings();
                break;
        }
    }
    
    /**
     * Setup time range controls
     */
    setupTimeControls() {
        // Quick time buttons
        document.querySelectorAll('.time-btn:not(.spec-time)').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.time-btn:not(.spec-time)').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                const hours = parseInt(btn.dataset.hours);
                this.setTimeRange(hours);
            });
        });
        
        // Spectrogram time buttons
        document.querySelectorAll('.time-btn.spec-time').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.time-btn.spec-time').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                const hours = parseInt(btn.dataset.hours);
                this.setTimeRange(hours);
            });
        });
        
        // Date range picker
        const startInput = document.getElementById('startTime');
        const endInput = document.getElementById('endTime');
        const applyBtn = document.getElementById('applyDateRange');
        
        // Set initial values
        startInput.value = this.timestampToLocal(this.timeRange.start);
        endInput.value = this.timestampToLocal(this.timeRange.end);
        
        applyBtn?.addEventListener('click', () => {
            const start = new Date(startInput.value).getTime() / 1000;
            const end = new Date(endInput.value).getTime() / 1000;
            
            if (start && end && start < end) {
                this.timeRange.start = Math.floor(start);
                this.timeRange.end = Math.floor(end);
                this.loadCurrentViewData();
            }
        });
        
        // Color scale selector
        document.getElementById('colorScale')?.addEventListener('change', (e) => {
            if (this.spectrogramViewer) {
                this.spectrogramViewer.setColorScale(e.target.value);
            }
        });
    }
    
    /**
     * Set time range by hours from now
     */
    setTimeRange(hours) {
        const now = Math.floor(Date.now() / 1000);
        this.timeRange.end = now;
        this.timeRange.start = now - (hours * 3600);
        
        // Update date inputs
        document.getElementById('startTime').value = this.timestampToLocal(this.timeRange.start);
        document.getElementById('endTime').value = this.timestampToLocal(this.timeRange.end);
        
        this.loadCurrentViewData();
    }
    
    /**
     * Load data for current view
     */
    async loadCurrentViewData() {
        switch (this.currentView) {
            case 'dashboard':
                await this.loadDashboardData();
                break;
            case 'spectrogram':
                await this.loadSpectrogramData();
                break;
        }
    }
    
    /**
     * Load dashboard data
     */
    async loadDashboardData() {
        try {
            // Load measurements
            const response = await fetch(
                `api.php?action=measurements&start=${this.timeRange.start}&end=${this.timeRange.end}`
            );
            const result = await response.json();
            
            if (result.data && result.data.length > 0) {
                this.chartManager.updateLevelsChart(result.data);
                this.chartManager.updateCentroidChart(result.data);
            }
            
            // Load stats
            const statsResponse = await fetch(
                `api.php?action=stats&start=${this.timeRange.start}&end=${this.timeRange.end}`
            );
            const stats = await statsResponse.json();
            this.updateStats(stats);
            
            // Load hourly data
            const hourlyResponse = await fetch(
                `api.php?action=hourly&start=${this.timeRange.start}&end=${this.timeRange.end}`
            );
            const hourlyResult = await hourlyResponse.json();
            
            if (hourlyResult.data && hourlyResult.data.length > 0) {
                this.chartManager.updateHourlyChart(hourlyResult.data);
            }
            
        } catch (error) {
            console.error('Failed to load dashboard data:', error);
        }
    }
    
    /**
     * Update statistics display
     */
    updateStats(stats) {
        document.getElementById('statAvgLevel').textContent = 
            stats.avg_laeq ? `${stats.avg_laeq.toFixed(1)} dB` : '-- dB';
        document.getElementById('statMaxLevel').textContent = 
            stats.max_level ? `${stats.max_level.toFixed(1)} dB` : '-- dB';
        document.getElementById('statL90').textContent = 
            stats.avg_l50 ? `${stats.avg_l50.toFixed(1)} dB` : '-- dB';
        document.getElementById('statEvents').textContent = 
            stats.total_events ?? '--';
        document.getElementById('statAnomalies').textContent = 
            stats.anomaly_count ?? '--';
    }
    
    /**
     * Load spectrogram data
     */
    async loadSpectrogramData() {
        // Initialize viewer if needed
        if (!this.spectrogramViewer) {
            this.spectrogramViewer = new SpectrogramViewer('spectrogramCanvas');
            
            // Handle spectrogram clicks for annotation
            document.getElementById('spectrogramCanvas')?.addEventListener('spectrogram-click', async (e) => {
                const timestamp = e.detail.timestamp;
                await this.openAnnotationForTimestamp(timestamp);
            });
        }
        
        await this.spectrogramViewer.loadData(this.timeRange.start, this.timeRange.end);
    }
    
    /**
     * Load anomalies
     */
    async loadAnomalies() {
        const threshold = parseFloat(document.getElementById('anomalyThreshold')?.value || 2.0);
        const list = document.getElementById('anomalyList');
        
        list.innerHTML = '<p class="loading">Loading anomalies...</p>';
        
        try {
            const response = await fetch(
                `api.php?action=anomalies&threshold=${threshold}&limit=100`
            );
            const result = await response.json();
            
            if (!result.data || result.data.length === 0) {
                list.innerHTML = '<p class="loading">No anomalies found above threshold.</p>';
                return;
            }
            
            list.innerHTML = result.data.map(anomaly => {
                const date = new Date(anomaly.timestamp * 1000);
                const isHigh = anomaly.anomaly_score > 3.0;
                const hasSnippet = anomaly.snippet_path;
                
                return `
                    <div class="anomaly-item ${isHigh ? 'high-score' : ''}" data-id="${anomaly.id}">
                        <div class="anomaly-info">
                            <div class="anomaly-time">${date.toLocaleString()}</div>
                            <div class="anomaly-details">
                                LAeq: ${anomaly.laeq?.toFixed(1)} dB | 
                                Lmax: ${anomaly.lmax?.toFixed(1)} dB |
                                Centroid: ${anomaly.spectral_centroid?.toFixed(0)} Hz
                            </div>
                            ${anomaly.annotation ? `<div class="anomaly-annotation">${anomaly.annotation}</div>` : ''}
                            ${hasSnippet ? `
                                <div class="anomaly-audio">
                                    <div class="anomaly-audio-label">🔊 Audio snippet available</div>
                                    <audio controls preload="none">
                                        <source src="api.php?action=snippet&id=${anomaly.id}" type="audio/ogg">
                                    </audio>
                                </div>
                            ` : ''}
                        </div>
                        <div class="anomaly-score">${anomaly.anomaly_score?.toFixed(2)}</div>
                    </div>
                `;
            }).join('');
            
            // Add click handlers
            list.querySelectorAll('.anomaly-item').forEach(item => {
                item.addEventListener('click', () => {
                    const id = item.dataset.id;
                    this.openAnnotation(id);
                });
            });
            
        } catch (error) {
            console.error('Failed to load anomalies:', error);
            list.innerHTML = '<p class="loading">Failed to load anomalies.</p>';
        }
    }
    
    /**
     * Setup anomaly controls
     */
    setupAnomalyControls() {
        document.getElementById('refreshAnomalies')?.addEventListener('click', () => {
            this.loadAnomalies();
        });
    }
    
    /**
     * Setup settings controls
     */
    setupSettingsControls() {
        document.getElementById('saveSettings')?.addEventListener('click', async () => {
            await this.saveSettings();
        });
    }
    
    /**
     * Load settings and snippets
     */
    async loadSettings() {
        try {
            // Load config
            const configResponse = await fetch('api.php?action=config');
            const config = await configResponse.json();
            
            // Update form
            document.getElementById('enableSnippets').checked = config.save_anomaly_snippets || false;
            document.getElementById('snippetThreshold').value = config.snippet_threshold || 2.5;
            document.getElementById('snippetDuration').value = config.snippet_duration || 5;
            
            // Load status for snippet stats
            const statusResponse = await fetch('api.php?action=status');
            const status = await statusResponse.json();
            
            document.getElementById('snippetCount').textContent = `${status.snippet_count || 0} snippets`;
            document.getElementById('snippetSize').textContent = `${status.snippets_size_mb || 0} MB`;
            
            // Load snippet list
            await this.loadSnippetList();
            
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    }
    
    /**
     * Save settings
     */
    async saveSettings() {
        const note = document.getElementById('settingsNote');
        note.textContent = 'Saving...';
        note.style.color = 'var(--text-secondary)';
        
        try {
            const response = await fetch('api.php?action=save_config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    save_anomaly_snippets: document.getElementById('enableSnippets').checked,
                    snippet_threshold: parseFloat(document.getElementById('snippetThreshold').value),
                    snippet_duration: parseFloat(document.getElementById('snippetDuration').value)
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                note.textContent = 'Saved! Restart capture daemon for changes to take effect.';
                note.style.color = 'var(--accent-success)';
            } else {
                note.textContent = 'Failed to save: ' + (result.error || 'Unknown error');
                note.style.color = 'var(--accent-danger)';
            }
        } catch (error) {
            note.textContent = 'Failed to save settings';
            note.style.color = 'var(--accent-danger)';
        }
        
        // Clear note after 5 seconds
        setTimeout(() => { note.textContent = ''; }, 5000);
    }
    
    /**
     * Load snippet list
     */
    async loadSnippetList() {
        const list = document.getElementById('snippetList');
        
        try {
            const response = await fetch('api.php?action=snippets&limit=50');
            const result = await response.json();
            
            if (!result.data || result.data.length === 0) {
                list.innerHTML = '<p class="loading">No snippets saved yet.</p>';
                return;
            }
            
            list.innerHTML = result.data.map(snippet => {
                const date = new Date(snippet.timestamp * 1000);
                const sizeKB = snippet.file_size ? Math.round(snippet.file_size / 1024) : '?';
                
                return `
                    <div class="snippet-item" data-id="${snippet.id}">
                        <div class="snippet-info">
                            <div class="snippet-time">${date.toLocaleString()}</div>
                            <div class="snippet-details">
                                Score: ${snippet.anomaly_score?.toFixed(2)} | 
                                LAeq: ${snippet.laeq?.toFixed(1)} dB |
                                ${sizeKB} KB
                            </div>
                        </div>
                        <div class="snippet-audio">
                            <audio controls preload="none">
                                <source src="api.php?action=snippet&id=${snippet.id}" type="audio/ogg">
                            </audio>
                        </div>
                        <button class="snippet-delete" title="Delete snippet" onclick="app.deleteSnippet(${snippet.id})">🗑️</button>
                    </div>
                `;
            }).join('');
            
        } catch (error) {
            console.error('Failed to load snippets:', error);
            list.innerHTML = '<p class="loading">Failed to load snippets.</p>';
        }
    }
    
    /**
     * Delete a snippet
     */
    async deleteSnippet(id) {
        if (!confirm('Delete this audio snippet?')) return;
        
        try {
            const response = await fetch('api.php?action=delete_snippet', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id })
            });
            
            const result = await response.json();
            
            if (result.success) {
                await this.loadSnippetList();
                await this.loadSettings(); // Refresh stats
            }
        } catch (error) {
            console.error('Failed to delete snippet:', error);
        }
    }
    
    /**
     * Setup annotation modal
     */
    setupAnnotationModal() {
        const modal = document.getElementById('annotationModal');
        
        document.getElementById('cancelAnnotation')?.addEventListener('click', () => {
            modal.classList.remove('active');
            this.annotationTarget = null;
        });
        
        document.getElementById('saveAnnotation')?.addEventListener('click', async () => {
            await this.saveAnnotation();
        });
        
        // Close on outside click
        modal?.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
                this.annotationTarget = null;
            }
        });
    }
    
    /**
     * Open annotation modal for a measurement ID
     */
    async openAnnotation(measurementId) {
        try {
            const response = await fetch(`api.php?action=measurement&id=${measurementId}`);
            const data = await response.json();
            
            if (data.error) {
                console.error('Failed to load measurement:', data.error);
                return;
            }
            
            this.annotationTarget = measurementId;
            
            const date = new Date(data.timestamp * 1000);
            document.getElementById('annotationInfo').textContent = 
                `${date.toLocaleString()} | LAeq: ${data.laeq?.toFixed(1)} dB`;
            document.getElementById('annotationText').value = data.annotation || '';
            document.getElementById('annotationModal').classList.add('active');
            document.getElementById('annotationText').focus();
            
        } catch (error) {
            console.error('Failed to open annotation:', error);
        }
    }
    
    /**
     * Open annotation for a timestamp (find nearest measurement)
     */
    async openAnnotationForTimestamp(timestamp) {
        try {
            const response = await fetch(
                `api.php?action=measurements&start=${timestamp}&end=${timestamp + 30}`
            );
            const result = await response.json();
            
            if (result.data && result.data.length > 0) {
                await this.openAnnotation(result.data[0].id);
            }
        } catch (error) {
            console.error('Failed to find measurement for timestamp:', error);
        }
    }
    
    /**
     * Save annotation
     */
    async saveAnnotation() {
        if (!this.annotationTarget) return;
        
        const annotation = document.getElementById('annotationText').value;
        
        try {
            const response = await fetch('api.php?action=annotate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: this.annotationTarget,
                    annotation: annotation
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                document.getElementById('annotationModal').classList.remove('active');
                this.annotationTarget = null;
                
                // Refresh anomalies if in that view
                if (this.currentView === 'anomalies') {
                    await this.loadAnomalies();
                }
            }
        } catch (error) {
            console.error('Failed to save annotation:', error);
        }
    }
    
    /**
     * Update system status indicator
     */
    async updateStatus() {
        try {
            const response = await fetch('api.php?action=status');
            const status = await response.json();
            
            const dot = document.getElementById('statusDot');
            const text = document.getElementById('statusText');
            
            if (status.status === 'running') {
                dot.className = 'status-dot running';
                text.textContent = 'Capturing';
            } else {
                dot.className = 'status-dot stopped';
                const age = status.latest_age_seconds;
                if (age) {
                    const mins = Math.floor(age / 60);
                    text.textContent = `Stopped (${mins}m ago)`;
                } else {
                    text.textContent = 'No data';
                }
            }
        } catch (error) {
            document.getElementById('statusDot').className = 'status-dot';
            document.getElementById('statusText').textContent = 'Offline';
        }
    }
    
    /**
     * Start auto-refresh
     */
    startAutoRefresh() {
        // Refresh status every 30 seconds
        setInterval(() => this.updateStatus(), 30000);
        
        // Refresh data every 60 seconds if viewing recent data
        this.refreshInterval = setInterval(() => {
            const now = Math.floor(Date.now() / 1000);
            // Only auto-refresh if viewing recent data (within last 2 hours)
            if (this.timeRange.end > now - 7200) {
                this.timeRange.end = now;
                this.loadCurrentViewData();
            }
        }, 60000);
    }
    
    /**
     * Handle window resize
     */
    handleResize() {
        if (this.spectrogramViewer && this.currentView === 'spectrogram') {
            this.spectrogramViewer.resize();
        }
    }
    
    /**
     * Convert timestamp to local datetime string for input
     */
    timestampToLocal(timestamp) {
        const date = new Date(timestamp * 1000);
        const offset = date.getTimezoneOffset();
        const local = new Date(date.getTime() - offset * 60 * 1000);
        return local.toISOString().slice(0, 16);
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new NoisyPiApp();
});

