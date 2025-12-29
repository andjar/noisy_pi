/**
 * Noisy Pi - Chart Management
 * Chart.js-based visualizations for noise data
 */

class ChartManager {
    constructor() {
        this.charts = {};
        this.chartColors = {
            primary: '#58a6ff',
            secondary: '#8b949e',
            success: '#3fb950',
            warning: '#d29922',
            danger: '#f85149',
            mean: '#58a6ff',
            max: '#f85149',
            min: '#3fb950',
            bandLow: '#f85149',
            bandMid: '#d29922',
            bandHigh: '#3fb950'
        };
        
        this.setupChartDefaults();
    }
    
    setupChartDefaults() {
        Chart.defaults.color = '#8b949e';
        Chart.defaults.borderColor = '#30363d';
        Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
        Chart.defaults.plugins.legend.labels.boxWidth = 12;
        Chart.defaults.plugins.legend.labels.padding = 15;
    }
    
    /**
     * Create or update levels chart
     */
    updateLevelsChart(data) {
        const ctx = document.getElementById('levels-chart');
        if (!ctx) return;
        
        if (this.charts.levels) {
            this.charts.levels.destroy();
        }
        
        // Data comes in reverse chronological, so reverse it
        const chronological = [...data].reverse();
        const labels = chronological.map(d => new Date(d.timestamp));
        
        this.charts.levels = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Mean dB',
                        data: chronological.map(d => d.mean_db),
                        borderColor: this.chartColors.mean,
                        backgroundColor: this.chartColors.mean + '20',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 2
                    },
                    {
                        label: 'Max dB',
                        data: chronological.map(d => d.max_db),
                        borderColor: this.chartColors.max,
                        backgroundColor: 'transparent',
                        borderWidth: 1,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        tension: 0.3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            displayFormats: {
                                hour: 'HH:mm',
                                minute: 'HH:mm',
                                day: 'MMM d'
                            }
                        },
                        grid: {
                            color: '#21262d'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Level (dB)'
                        },
                        grid: {
                            color: '#21262d'
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top'
                    },
                    tooltip: {
                        backgroundColor: '#161b22',
                        titleColor: '#e6edf3',
                        bodyColor: '#8b949e',
                        borderColor: '#30363d',
                        borderWidth: 1,
                        padding: 12,
                        callbacks: {
                            label: function(context) {
                                return `${context.dataset.label}: ${context.parsed.y?.toFixed(1)} dB`;
                            }
                        }
                    }
                }
            }
        });
    }
    
    /**
     * Create or update frequency bands chart
     */
    updateBandsChart(data) {
        const ctx = document.getElementById('bands-chart');
        if (!ctx) return;
        
        if (this.charts.bands) {
            this.charts.bands.destroy();
        }
        
        const chronological = [...data].reverse();
        const labels = chronological.map(d => new Date(d.timestamp));
        
        this.charts.bands = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Low (0-200 Hz)',
                        data: chronological.map(d => d.band_low_db),
                        borderColor: this.chartColors.bandLow,
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3
                    },
                    {
                        label: 'Mid (200-2000 Hz)',
                        data: chronological.map(d => d.band_mid_db),
                        borderColor: this.chartColors.bandMid,
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3
                    },
                    {
                        label: 'High (2000+ Hz)',
                        data: chronological.map(d => d.band_high_db),
                        borderColor: this.chartColors.bandHigh,
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            displayFormats: {
                                hour: 'HH:mm',
                                minute: 'HH:mm'
                            }
                        },
                        grid: {
                            color: '#21262d'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Level (dB)'
                        },
                        grid: {
                            color: '#21262d'
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top'
                    },
                    tooltip: {
                        backgroundColor: '#161b22',
                        borderColor: '#30363d',
                        borderWidth: 1,
                        callbacks: {
                            label: function(context) {
                                return `${context.dataset.label}: ${context.parsed.y?.toFixed(1)} dB`;
                            }
                        }
                    }
                }
            }
        });
    }
    
    /**
     * Create or update anomaly chart
     */
    updateAnomalyChart(data) {
        const ctx = document.getElementById('anomaly-chart');
        if (!ctx) return;
        
        if (this.charts.anomaly) {
            this.charts.anomaly.destroy();
        }
        
        const chronological = [...data].reverse();
        const labels = chronological.map(d => new Date(d.timestamp));
        
        // Color points based on anomaly score
        const pointColors = chronological.map(d => {
            const score = d.anomaly_score || 0;
            if (score >= 2.5) return this.chartColors.danger;
            if (score >= 1.5) return this.chartColors.warning;
            return this.chartColors.success;
        });
        
        this.charts.anomaly = new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Anomaly Score',
                    data: chronological.map((d, i) => ({
                        x: labels[i],
                        y: d.anomaly_score || 0
                    })),
                    backgroundColor: pointColors,
                    borderColor: pointColors,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            displayFormats: {
                                hour: 'HH:mm'
                            }
                        },
                        grid: {
                            color: '#21262d'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Anomaly Score'
                        },
                        min: 0,
                        grid: {
                            color: '#21262d'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    annotation: {
                        annotations: {
                            threshold: {
                                type: 'line',
                                yMin: 2.5,
                                yMax: 2.5,
                                borderColor: this.chartColors.danger,
                                borderWidth: 1,
                                borderDash: [5, 5],
                                label: {
                                    display: true,
                                    content: 'Threshold',
                                    position: 'end'
                                }
                            }
                        }
                    },
                    tooltip: {
                        backgroundColor: '#161b22',
                        borderColor: '#30363d',
                        borderWidth: 1,
                        callbacks: {
                            label: function(context) {
                                return `Score: ${context.parsed.y?.toFixed(2)}`;
                            }
                        }
                    }
                }
            }
        });
    }
    
    /**
     * Create or update hourly statistics chart
     */
    updateHourlyChart(data) {
        const ctx = document.getElementById('hourly-chart');
        if (!ctx) return;
        
        if (this.charts.hourly) {
            this.charts.hourly.destroy();
        }
        
        this.charts.hourly = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(d => d.hour + ':00'),
                datasets: [
                    {
                        label: 'Avg dB',
                        data: data.map(d => d.avg_db),
                        backgroundColor: this.chartColors.primary + 'aa',
                        borderColor: this.chartColors.primary,
                        borderWidth: 1,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Anomalies',
                        data: data.map(d => d.anomaly_count),
                        backgroundColor: this.chartColors.warning + 'aa',
                        borderColor: this.chartColors.warning,
                        borderWidth: 1,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                scales: {
                    x: {
                        grid: {
                            color: '#21262d'
                        }
                    },
                    y: {
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Level (dB)'
                        },
                        grid: {
                            color: '#21262d'
                        }
                    },
                    y1: {
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Anomalies'
                        },
                        grid: {
                            drawOnChartArea: false
                        },
                        min: 0
                    }
                },
                plugins: {
                    legend: {
                        position: 'top'
                    },
                    tooltip: {
                        backgroundColor: '#161b22',
                        borderColor: '#30363d',
                        borderWidth: 1
                    }
                }
            }
        });
    }
    
    /**
     * Destroy all charts
     */
    destroyAll() {
        Object.values(this.charts).forEach(chart => {
            if (chart) chart.destroy();
        });
        this.charts = {};
    }
}

// Export for use in app.js
window.ChartManager = ChartManager;

