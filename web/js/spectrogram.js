/**
 * Noisy Pi - Spectrogram Visualization
 * Canvas-based heatmap spectrogram with hover details
 */

class SpectrogramViewer {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.options = {
            colorScale: options.colorScale || 'viridis',
            dbMin: options.dbMin || -90,
            dbMax: options.dbMax || 10,
            ...options
        };
        
        this.data = null;
        this.timestamps = null;
        this.frequencies = null;
        
        this.setupCanvas();
        this.setupColorScale();
        this.setupEventListeners();
    }
    
    setupCanvas() {
        // Set canvas size to match container
        const container = this.canvas.parentElement;
        const width = container.clientWidth - 60; // Account for freq axis
        const height = 400;
        
        this.canvas.width = width;
        this.canvas.height = height;
        this.canvas.style.width = width + 'px';
        this.canvas.style.height = height + 'px';
    }
    
    setupColorScale() {
        // Define color scales
        this.colorScales = {
            viridis: [
                [68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142],
                [38, 130, 142], [31, 158, 137], [53, 183, 121], [109, 205, 89],
                [180, 222, 44], [253, 231, 37]
            ],
            inferno: [
                [0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99],
                [212, 72, 66], [245, 125, 21], [250, 193, 39], [252, 255, 164]
            ],
            grayscale: [
                [0, 0, 0], [28, 28, 28], [57, 57, 57], [85, 85, 85],
                [113, 113, 113], [142, 142, 142], [170, 170, 170], [198, 198, 198],
                [227, 227, 227], [255, 255, 255]
            ]
        };
    }
    
    setupEventListeners() {
        this.canvas.addEventListener('mousemove', (e) => this.handleMouseMove(e));
        this.canvas.addEventListener('mouseout', () => this.hideTooltip());
        this.canvas.addEventListener('click', (e) => this.handleClick(e));
    }
    
    setColorScale(scale) {
        if (this.colorScales[scale]) {
            this.options.colorScale = scale;
            if (this.data) {
                this.render();
            }
        }
    }
    
    /**
     * Convert dB value to color
     */
    dbToColor(db) {
        const scale = this.colorScales[this.options.colorScale];
        const normalized = Math.max(0, Math.min(1, 
            (db - this.options.dbMin) / (this.options.dbMax - this.options.dbMin)
        ));
        
        const index = normalized * (scale.length - 1);
        const lower = Math.floor(index);
        const upper = Math.min(lower + 1, scale.length - 1);
        const t = index - lower;
        
        const r = Math.round(scale[lower][0] * (1 - t) + scale[upper][0] * t);
        const g = Math.round(scale[lower][1] * (1 - t) + scale[upper][1] * t);
        const b = Math.round(scale[lower][2] * (1 - t) + scale[upper][2] * t);
        
        return `rgb(${r},${g},${b})`;
    }
    
    /**
     * Load and display spectrogram data
     */
    async loadData(startTime, endTime) {
        try {
            const response = await fetch(
                `api.php?action=spectrogram&start=${startTime}&end=${endTime}&max=300`
            );
            const result = await response.json();
            
            if (result.error) {
                console.error('API error:', result.error);
                return;
            }
            
            this.data = result.data;
            this.timestamps = result.timestamps;
            this.frequencies = result.frequencies;
            this.snapshotsPerInterval = result.snapshots_per_interval || 10;
            
            this.render();
            this.updateAxes();
            this.renderColorLegend();
            
        } catch (error) {
            console.error('Failed to load spectrogram:', error);
        }
    }
    
    /**
     * Render the spectrogram
     */
    render() {
        if (!this.data || this.data.length === 0) {
            this.ctx.fillStyle = '#1c2128';
            this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
            this.ctx.fillStyle = '#8b949e';
            this.ctx.font = '14px Inter, sans-serif';
            this.ctx.textAlign = 'center';
            this.ctx.fillText('No data available', this.canvas.width / 2, this.canvas.height / 2);
            return;
        }
        
        const numBins = this.frequencies ? this.frequencies.length : 256;
        const numTimeSlots = this.data.length * this.snapshotsPerInterval;
        
        const pixelWidth = this.canvas.width / numTimeSlots;
        const pixelHeight = this.canvas.height / numBins;
        
        // Clear canvas
        this.ctx.fillStyle = '#0d1117';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        // Draw spectrogram
        let x = 0;
        for (let i = 0; i < this.data.length; i++) {
            const intervalData = this.data[i];
            if (!intervalData) continue;
            
            for (let s = 0; s < intervalData.length; s++) {
                const spectrum = intervalData[s];
                if (!spectrum) continue;
                
                for (let f = 0; f < spectrum.length; f++) {
                    const db = spectrum[f];
                    const color = this.dbToColor(db);
                    
                    this.ctx.fillStyle = color;
                    // Y axis is inverted (high freq at top)
                    const y = this.canvas.height - (f + 1) * pixelHeight;
                    this.ctx.fillRect(x, y, Math.ceil(pixelWidth) + 1, Math.ceil(pixelHeight) + 1);
                }
                x += pixelWidth;
            }
        }
    }
    
    /**
     * Update frequency and time axes
     */
    updateAxes() {
        // Frequency axis
        const freqAxis = document.getElementById('freqAxis');
        if (freqAxis && this.frequencies) {
            const labels = [
                this.frequencies[this.frequencies.length - 1], // Top
                this.frequencies[Math.floor(this.frequencies.length * 0.75)],
                this.frequencies[Math.floor(this.frequencies.length * 0.5)],
                this.frequencies[Math.floor(this.frequencies.length * 0.25)],
                this.frequencies[0] // Bottom
            ];
            
            freqAxis.innerHTML = labels.map(f => {
                if (f >= 1000) {
                    return `<span>${(f/1000).toFixed(1)}k</span>`;
                }
                return `<span>${f}</span>`;
            }).join('');
        }
        
        // Time axis
        const timeAxis = document.getElementById('timeAxis');
        if (timeAxis && this.timestamps && this.timestamps.length > 0) {
            const numLabels = 6;
            const step = Math.floor(this.timestamps.length / (numLabels - 1));
            
            const labels = [];
            for (let i = 0; i < numLabels; i++) {
                const idx = Math.min(i * step, this.timestamps.length - 1);
                const date = new Date(this.timestamps[idx] * 1000);
                labels.push(date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
            }
            
            timeAxis.innerHTML = labels.map(l => `<span>${l}</span>`).join('');
        }
    }
    
    /**
     * Render color legend
     */
    renderColorLegend() {
        const legend = document.getElementById('colorLegend');
        if (!legend) return;
        
        const canvas = document.createElement('canvas');
        canvas.width = 200;
        canvas.height = 20;
        const ctx = canvas.getContext('2d');
        
        // Draw gradient
        for (let x = 0; x < canvas.width; x++) {
            const db = this.options.dbMin + (x / canvas.width) * (this.options.dbMax - this.options.dbMin);
            ctx.fillStyle = this.dbToColor(db);
            ctx.fillRect(x, 0, 1, canvas.height);
        }
        
        legend.innerHTML = `
            <span>${this.options.dbMin} dB</span>
            ${canvas.outerHTML}
            <span>${this.options.dbMax} dB</span>
        `;
        legend.querySelector('canvas').replaceWith(canvas);
    }
    
    /**
     * Handle mouse move for tooltip
     */
    handleMouseMove(e) {
        if (!this.data || this.data.length === 0) return;
        
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        // Calculate which data point
        const numTimeSlots = this.data.length * this.snapshotsPerInterval;
        const timeSlot = Math.floor(x / this.canvas.width * numTimeSlots);
        const intervalIdx = Math.floor(timeSlot / this.snapshotsPerInterval);
        const snapshotIdx = timeSlot % this.snapshotsPerInterval;
        
        const freqIdx = Math.floor((1 - y / this.canvas.height) * this.frequencies.length);
        
        if (intervalIdx >= 0 && intervalIdx < this.data.length &&
            this.data[intervalIdx] && this.data[intervalIdx][snapshotIdx]) {
            
            const db = this.data[intervalIdx][snapshotIdx][freqIdx];
            const freq = this.frequencies[freqIdx];
            const timestamp = this.timestamps[intervalIdx];
            const date = new Date((timestamp + snapshotIdx * 3) * 1000);
            
            this.showTooltip(e.clientX, e.clientY, {
                time: date.toLocaleString(),
                freq: freq >= 1000 ? `${(freq/1000).toFixed(1)} kHz` : `${freq} Hz`,
                level: `${db.toFixed(1)} dB`
            });
        }
    }
    
    /**
     * Show tooltip
     */
    showTooltip(x, y, data) {
        const tooltip = document.getElementById('spectrogramTooltip');
        if (!tooltip) return;
        
        tooltip.innerHTML = `
            <div>Time: ${data.time}</div>
            <div>Freq: ${data.freq}</div>
            <div>Level: ${data.level}</div>
        `;
        
        tooltip.style.left = (x + 15) + 'px';
        tooltip.style.top = (y + 15) + 'px';
        tooltip.classList.add('visible');
    }
    
    /**
     * Hide tooltip
     */
    hideTooltip() {
        const tooltip = document.getElementById('spectrogramTooltip');
        if (tooltip) {
            tooltip.classList.remove('visible');
        }
    }
    
    /**
     * Handle click for annotation
     */
    handleClick(e) {
        if (!this.data || this.data.length === 0) return;
        
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        
        const numTimeSlots = this.data.length * this.snapshotsPerInterval;
        const timeSlot = Math.floor(x / this.canvas.width * numTimeSlots);
        const intervalIdx = Math.floor(timeSlot / this.snapshotsPerInterval);
        
        if (intervalIdx >= 0 && intervalIdx < this.timestamps.length) {
            const timestamp = this.timestamps[intervalIdx];
            // Dispatch custom event for annotation
            this.canvas.dispatchEvent(new CustomEvent('spectrogram-click', {
                detail: { timestamp, intervalIdx }
            }));
        }
    }
    
    /**
     * Resize handler
     */
    resize() {
        this.setupCanvas();
        if (this.data) {
            this.render();
        }
    }
}

// Export for use in app.js
window.SpectrogramViewer = SpectrogramViewer;

