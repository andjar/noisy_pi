/**
 * Noisy Pi - Spectrogram Visualization
 * Canvas-based heatmap for frequency vs time
 */

class SpectrogramRenderer {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) {
            console.warn(`Canvas ${canvasId} not found`);
            return;
        }
        
        this.ctx = this.canvas.getContext('2d');
        
        // Options
        this.options = {
            colormap: options.colormap || 'viridis',
            minDb: options.minDb || -90,
            maxDb: options.maxDb || 10,
            freqMin: options.freqMin || 0,
            freqMax: options.freqMax || 24000,
            ...options
        };
        
        // Color maps
        this.colormaps = {
            viridis: [
                [68, 1, 84],
                [72, 40, 120],
                [62, 74, 137],
                [49, 104, 142],
                [38, 130, 142],
                [31, 158, 137],
                [53, 183, 121],
                [109, 205, 89],
                [180, 222, 44],
                [253, 231, 37]
            ],
            plasma: [
                [13, 8, 135],
                [75, 3, 161],
                [125, 3, 168],
                [168, 34, 150],
                [203, 70, 121],
                [229, 107, 93],
                [248, 148, 65],
                [253, 195, 40],
                [240, 249, 33]
            ],
            inferno: [
                [0, 0, 4],
                [40, 11, 84],
                [101, 21, 110],
                [159, 42, 99],
                [212, 72, 66],
                [245, 125, 21],
                [250, 193, 39],
                [252, 255, 164]
            ]
        };
        
        this.resize();
        window.addEventListener('resize', () => this.resize());
    }
    
    resize() {
        if (!this.canvas) return;
        
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width;
        this.canvas.height = rect.height || 200;
    }
    
    /**
     * Get color for a dB value
     */
    getColor(db) {
        const colors = this.colormaps[this.options.colormap] || this.colormaps.viridis;
        
        // Normalize to 0-1
        let normalized = (db - this.options.minDb) / (this.options.maxDb - this.options.minDb);
        normalized = Math.max(0, Math.min(1, normalized));
        
        // Map to color index
        const index = normalized * (colors.length - 1);
        const lower = Math.floor(index);
        const upper = Math.ceil(index);
        const t = index - lower;
        
        // Interpolate between colors
        const c1 = colors[lower];
        const c2 = colors[upper];
        
        const r = Math.round(c1[0] + t * (c2[0] - c1[0]));
        const g = Math.round(c1[1] + t * (c2[1] - c1[1]));
        const b = Math.round(c1[2] + t * (c2[2] - c1[2]));
        
        return `rgb(${r},${g},${b})`;
    }
    
    /**
     * Render spectrogram from band data over time
     */
    renderBands(data) {
        if (!this.canvas || !this.ctx) return;
        if (!data || data.length === 0) return;
        
        const width = this.canvas.width;
        const height = this.canvas.height;
        
        // Clear
        this.ctx.fillStyle = '#0d1117';
        this.ctx.fillRect(0, 0, width, height);
        
        // We have 3 bands: low, mid, high
        const bandHeight = height / 3;
        const columnWidth = Math.max(2, width / data.length);
        
        // Reverse to get chronological order
        const chronological = [...data].reverse();
        
        chronological.forEach((d, i) => {
            const x = i * columnWidth;
            
            // High band (top)
            this.ctx.fillStyle = this.getColor(d.band_high_db || -90);
            this.ctx.fillRect(x, 0, columnWidth + 1, bandHeight);
            
            // Mid band (middle)
            this.ctx.fillStyle = this.getColor(d.band_mid_db || -90);
            this.ctx.fillRect(x, bandHeight, columnWidth + 1, bandHeight);
            
            // Low band (bottom)
            this.ctx.fillStyle = this.getColor(d.band_low_db || -90);
            this.ctx.fillRect(x, bandHeight * 2, columnWidth + 1, bandHeight);
        });
        
        // Draw frequency labels
        this.ctx.fillStyle = '#8b949e';
        this.ctx.font = '10px sans-serif';
        this.ctx.textAlign = 'left';
        this.ctx.fillText('2kHz+', 5, 15);
        this.ctx.fillText('200-2kHz', 5, bandHeight + 15);
        this.ctx.fillText('0-200Hz', 5, bandHeight * 2 + 15);
    }
    
    /**
     * Render full spectrogram from raw spectrum data
     */
    renderSpectrum(spectrumData, timestamps) {
        if (!this.canvas || !this.ctx) return;
        if (!spectrumData || spectrumData.length === 0) return;
        
        const width = this.canvas.width;
        const height = this.canvas.height;
        
        // Clear
        this.ctx.fillStyle = '#0d1117';
        this.ctx.fillRect(0, 0, width, height);
        
        const numBins = spectrumData[0].length;
        const binHeight = height / numBins;
        const columnWidth = Math.max(1, width / spectrumData.length);
        
        spectrumData.forEach((spectrum, timeIdx) => {
            const x = timeIdx * columnWidth;
            
            spectrum.forEach((db, freqIdx) => {
                // Frequency increases upward
                const y = height - (freqIdx + 1) * binHeight;
                
                this.ctx.fillStyle = this.getColor(db);
                this.ctx.fillRect(x, y, columnWidth + 1, binHeight + 1);
            });
        });
        
        // Draw axis labels
        this.drawAxisLabels(timestamps);
    }
    
    drawAxisLabels(timestamps) {
        if (!timestamps || timestamps.length === 0) return;
        
        const width = this.canvas.width;
        const height = this.canvas.height;
        
        // Frequency axis (left)
        this.ctx.fillStyle = '#8b949e';
        this.ctx.font = '10px sans-serif';
        this.ctx.textAlign = 'left';
        
        const freqLabels = ['24kHz', '12kHz', '6kHz', '0Hz'];
        freqLabels.forEach((label, i) => {
            const y = (i / (freqLabels.length - 1)) * height;
            this.ctx.fillText(label, 5, y + 12);
        });
    }
    
    /**
     * Draw color scale legend
     */
    drawLegend() {
        if (!this.canvas || !this.ctx) return;
        
        const width = 20;
        const height = this.canvas.height - 40;
        const x = this.canvas.width - 30;
        const y = 20;
        
        // Draw gradient
        for (let i = 0; i < height; i++) {
            const db = this.options.maxDb - (i / height) * (this.options.maxDb - this.options.minDb);
            this.ctx.fillStyle = this.getColor(db);
            this.ctx.fillRect(x, y + i, width, 1);
        }
        
        // Draw border
        this.ctx.strokeStyle = '#30363d';
        this.ctx.strokeRect(x, y, width, height);
        
        // Draw labels
        this.ctx.fillStyle = '#8b949e';
        this.ctx.font = '10px sans-serif';
        this.ctx.textAlign = 'right';
        this.ctx.fillText(`${this.options.maxDb}dB`, x - 5, y + 10);
        this.ctx.fillText(`${this.options.minDb}dB`, x - 5, y + height);
    }
}

// Export
window.SpectrogramRenderer = SpectrogramRenderer;

