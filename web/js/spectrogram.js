/**
 * Noisy Pi - Spectrogram and Heatmap Visualization
 */

// Colormaps
const COLORMAPS = {
    viridis: [
        [68, 1, 84], [72, 35, 116], [64, 67, 135], [52, 94, 141],
        [41, 120, 142], [32, 144, 140], [34, 167, 132], [68, 190, 112],
        [121, 209, 81], [189, 222, 38], [253, 231, 37]
    ],
    plasma: [
        [13, 8, 135], [75, 3, 161], [125, 3, 168], [168, 34, 150],
        [203, 70, 121], [229, 107, 93], [248, 148, 65], [253, 195, 40],
        [240, 249, 33]
    ],
    inferno: [
        [0, 0, 4], [22, 11, 57], [66, 10, 104], [106, 23, 110],
        [147, 38, 103], [188, 55, 84], [221, 81, 58], [243, 118, 27],
        [252, 165, 10], [246, 215, 70], [252, 255, 164]
    ],
    magma: [
        [0, 0, 4], [18, 14, 54], [51, 16, 101], [90, 18, 126],
        [130, 29, 140], [169, 46, 143], [209, 70, 134], [239, 101, 118],
        [253, 143, 119], [254, 196, 149], [252, 253, 191]
    ]
};

// Get color from value (0-1)
function getColor(value, colormap = 'viridis') {
    const colors = COLORMAPS[colormap] || COLORMAPS.viridis;
    const idx = Math.min(colors.length - 1, Math.max(0, Math.floor(value * (colors.length - 1))));
    const nextIdx = Math.min(colors.length - 1, idx + 1);
    const t = (value * (colors.length - 1)) - idx;
    
    const c1 = colors[idx];
    const c2 = colors[nextIdx];
    
    return [
        Math.round(c1[0] + (c2[0] - c1[0]) * t),
        Math.round(c1[1] + (c2[1] - c1[1]) * t),
        Math.round(c1[2] + (c2[2] - c1[2]) * t)
    ];
}

/**
 * 7-Band Heatmap Renderer (Dashboard)
 */
class HeatmapRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.colormap = 'viridis';
        this.minDb = -90;
        this.maxDb = 0;
        this.bands = ['band_0_200', 'band_200_500', 'band_500_1k', 'band_1k_2k', 'band_2k_4k', 'band_4k_8k', 'band_8k_24k'];
        this.bandLabels = ['0-200', '200-500', '500-1k', '1k-2k', '2k-4k', '4k-8k', '8k-24k'];
        
        // Click handler
        this.canvas.addEventListener('click', (e) => this.handleClick(e));
    }

    setColormap(cm) {
        this.colormap = cm;
    }

    render(data) {
        if (!this.canvas || !data || data.length === 0) return;
        
        const rect = this.canvas.parentElement.getBoundingClientRect();
        const width = this.canvas.width = rect.width - 70;
        const height = this.canvas.height = 180;
        
        const numBands = this.bands.length;
        const numSamples = data.length;
        
        const cellWidth = width / numSamples;
        const cellHeight = height / numBands;
        
        // Clear
        this.ctx.fillStyle = '#0a0e14';
        this.ctx.fillRect(0, 0, width, height);
        
        // Draw heatmap
        data.forEach((sample, x) => {
            this.bands.forEach((band, y) => {
                const db = parseFloat(sample[band]) || this.minDb;
                const normalized = (db - this.minDb) / (this.maxDb - this.minDb);
                const color = getColor(Math.max(0, Math.min(1, normalized)), this.colormap);
                
                this.ctx.fillStyle = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
                // Invert y so low frequencies are at bottom
                const invertedY = numBands - 1 - y;
                this.ctx.fillRect(x * cellWidth, invertedY * cellHeight, cellWidth + 0.5, cellHeight + 0.5);
            });
        });
        
        this.currentData = data;
    }

    handleClick(e) {
        if (!this.currentData) return;
        
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const sampleIdx = Math.floor((x / this.canvas.width) * this.currentData.length);
        
        if (sampleIdx >= 0 && sampleIdx < this.currentData.length) {
            const sample = this.currentData[sampleIdx];
            if (sample && sample.id) {
                viewDetail(sample.id);
            }
        }
    }
}

/**
 * Full Spectrogram Renderer (Spectrogram Tab)
 */
class SpectrogramRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.colormap = 'viridis';
        this.minDb = -90;
        this.maxDb = 0;
    }

    setColormap(cm) {
        this.colormap = cm;
    }

    renderFull(data) {
        if (!this.canvas || !data || data.length === 0) return;
        
        const container = this.canvas.parentElement;
        const width = this.canvas.width = container.clientWidth;
        const height = this.canvas.height = container.clientHeight || 250;
        
        // Clear
        this.ctx.fillStyle = '#0a0e14';
        this.ctx.fillRect(0, 0, width, height);
        
        const bands = ['band_0_200', 'band_200_500', 'band_500_1k', 'band_1k_2k', 'band_2k_4k', 'band_4k_8k', 'band_8k_24k'];
        const numBands = bands.length;
        const numSamples = data.length;
        
        const cellWidth = width / numSamples;
        const cellHeight = height / numBands;
        
        // Draw from oldest to newest (left to right)
        const sortedData = [...data].reverse();
        
        sortedData.forEach((sample, x) => {
            bands.forEach((band, y) => {
                const db = parseFloat(sample[band]) || this.minDb;
                const normalized = (db - this.minDb) / (this.maxDb - this.minDb);
                const color = getColor(Math.max(0, Math.min(1, normalized)), this.colormap);
                
                this.ctx.fillStyle = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
                // Invert y so low frequencies are at bottom
                const invertedY = numBands - 1 - y;
                this.ctx.fillRect(x * cellWidth, invertedY * cellHeight, cellWidth + 0.5, cellHeight + 0.5);
            });
        });
        
        // Draw time labels
        this.ctx.fillStyle = '#5c6370';
        this.ctx.font = '10px JetBrains Mono, monospace';
        this.ctx.textAlign = 'center';
        
        const labelInterval = Math.ceil(numSamples / 8);
        for (let i = 0; i < numSamples; i += labelInterval) {
            const sample = sortedData[i];
            if (sample && sample.timestamp) {
                const time = new Date(sample.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                this.ctx.fillText(time, i * cellWidth + cellWidth / 2, height - 5);
            }
        }
        
        // Draw frequency labels
        this.ctx.textAlign = 'right';
        const freqLabels = ['8k+', '4-8k', '2-4k', '1-2k', '.5-1k', '200-500', '0-200'];
        freqLabels.forEach((label, y) => {
            this.ctx.fillText(label, 45, y * cellHeight + cellHeight / 2 + 4);
        });
    }

    // Render band-based spectrogram from data with 7 bands
    renderBands(data) {
        if (!this.canvas || !data || data.length === 0) return;
        
        const container = this.canvas.parentElement;
        const width = this.canvas.width = container.clientWidth;
        const height = this.canvas.height = container.clientHeight || 180;
        
        this.ctx.fillStyle = '#0a0e14';
        this.ctx.fillRect(0, 0, width, height);
        
        const bands = ['band_low_db', 'band_mid_db', 'band_high_db'];
        const numBands = bands.length;
        const numSamples = Math.min(data.length, 200);
        
        const cellWidth = width / numSamples;
        const cellHeight = height / numBands;
        
        // Use most recent data
        const recentData = data.slice(0, numSamples).reverse();
        
        recentData.forEach((sample, x) => {
            bands.forEach((band, y) => {
                const db = parseFloat(sample[band]) || this.minDb;
                const normalized = (db - this.minDb) / (this.maxDb - this.minDb);
                const color = getColor(Math.max(0, Math.min(1, normalized)), this.colormap);
                
                this.ctx.fillStyle = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
                const invertedY = numBands - 1 - y;
                this.ctx.fillRect(x * cellWidth, invertedY * cellHeight, cellWidth + 0.5, cellHeight + 0.5);
            });
        });
    }
}

/**
 * Baseline Weekly Heatmap Renderer
 */
class BaselineRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.colormap = 'viridis';
    }

    render(data) {
        if (!this.canvas || !data || data.length === 0) return;
        
        const container = this.canvas.parentElement;
        const width = this.canvas.width = container.clientWidth;
        const height = this.canvas.height = container.clientHeight || 200;
        
        this.ctx.fillStyle = '#0a0e14';
        this.ctx.fillRect(0, 0, width, height);
        
        // Create matrix: 7 days x 24 hours
        const matrix = Array(7).fill(null).map(() => Array(24).fill(null));
        let minDb = Infinity, maxDb = -Infinity;
        
        data.forEach(d => {
            const dow = parseInt(d.day_of_week);
            const hour = parseInt(d.hour);
            const db = parseFloat(d.mean_db_avg);
            
            if (!isNaN(dow) && !isNaN(hour) && !isNaN(db)) {
                matrix[dow][hour] = db;
                minDb = Math.min(minDb, db);
                maxDb = Math.max(maxDb, db);
            }
        });
        
        if (minDb === Infinity) return;
        
        const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        const marginLeft = 40;
        const marginTop = 20;
        const marginBottom = 25;
        
        const cellWidth = (width - marginLeft) / 24;
        const cellHeight = (height - marginTop - marginBottom) / 7;
        
        // Draw cells
        matrix.forEach((dayData, day) => {
            dayData.forEach((db, hour) => {
                if (db !== null) {
                    const normalized = (db - minDb) / (maxDb - minDb);
                    const color = getColor(normalized, this.colormap);
                    
                    this.ctx.fillStyle = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
                    this.ctx.fillRect(
                        marginLeft + hour * cellWidth,
                        marginTop + day * cellHeight,
                        cellWidth - 1,
                        cellHeight - 1
                    );
                }
            });
        });
        
        // Draw labels
        this.ctx.fillStyle = '#5c6370';
        this.ctx.font = '9px JetBrains Mono, monospace';
        
        // Day labels
        this.ctx.textAlign = 'right';
        days.forEach((day, i) => {
            this.ctx.fillText(day, marginLeft - 5, marginTop + i * cellHeight + cellHeight / 2 + 3);
        });
        
        // Hour labels
        this.ctx.textAlign = 'center';
        for (let h = 0; h < 24; h += 4) {
            this.ctx.fillText(String(h).padStart(2, '0'), marginLeft + h * cellWidth + cellWidth / 2, height - 8);
        }
        
        // Title
        this.ctx.textAlign = 'left';
        this.ctx.fillText(`Range: ${minDb.toFixed(1)} - ${maxDb.toFixed(1)} dB`, marginLeft, 12);
    }
}
