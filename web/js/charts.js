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
            laeq: '#58a6ff',
            lmax: '#f85149',
            lmin: '#3fb950',
            l50: '#d29922'
        };
        
        this.setupChartDefaults();
    }
    
    setupChartDefaults() {
        Chart.defaults.color = '#8b949e';
        Chart.defaults.borderColor = '#30363d';
        Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";
        Chart.defaults.plugins.legend.labels.boxWidth = 12;
        Chart.defaults.plugins.legend.labels.padding = 15;
    }
    
    /**
     * Create or update levels chart
     */
    updateLevelsChart(data) {
        const ctx = document.getElementById('levelsChart');
        if (!ctx) return;
        
        if (this.charts.levels) {
            this.charts.levels.destroy();
        }
        
        const labels = data.map(d => new Date(d.timestamp * 1000));
        
        this.charts.levels = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'LAeq',
                        data: data.map(d => d.laeq),
                        borderColor: this.chartColors.laeq,
                        backgroundColor: this.chartColors.laeq + '20',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 2
                    },
                    {
                        label: 'Lmax',
                        data: data.map(d => d.lmax),
                        borderColor: this.chartColors.lmax,
                        backgroundColor: 'transparent',
                        borderWidth: 1,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        tension: 0.3
                    },
                    {
                        label: 'L50 (Median)',
                        data: data.map(d => d.l50),
                        borderColor: this.chartColors.l50,
                        backgroundColor: 'transparent',
                        borderWidth: 1.5,
                        pointRadius: 0,
                        tension: 0.3
                    },
                    {
                        label: 'L90 (Background)',
                        data: data.map(d => d.l90),
                        borderColor: this.chartColors.lmin,
                        backgroundColor: 'transparent',
                        borderWidth: 1,
                        borderDash: [2, 2],
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
     * Create or update spectral centroid chart
     */
    updateCentroidChart(data) {
        const ctx = document.getElementById('centroidChart');
        if (!ctx) return;
        
        if (this.charts.centroid) {
            this.charts.centroid.destroy();
        }
        
        const labels = data.map(d => new Date(d.timestamp * 1000));
        
        this.charts.centroid = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Spectral Centroid',
                        data: data.map(d => d.spectral_centroid),
                        borderColor: '#a371f7',
                        backgroundColor: '#a371f720',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 2
                    }
                ]
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
                            text: 'Frequency (Hz)'
                        },
                        grid: {
                            color: '#21262d'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: '#161b22',
                        borderColor: '#30363d',
                        borderWidth: 1,
                        callbacks: {
                            label: function(context) {
                                const freq = context.parsed.y;
                                if (freq >= 1000) {
                                    return `${(freq/1000).toFixed(2)} kHz`;
                                }
                                return `${freq?.toFixed(0)} Hz`;
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
        const ctx = document.getElementById('hourlyChart');
        if (!ctx) return;
        
        if (this.charts.hourly) {
            this.charts.hourly.destroy();
        }
        
        const labels = data.map(d => {
            const date = new Date(d.hour_start * 1000);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        });
        
        this.charts.hourly = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Avg LAeq',
                        data: data.map(d => d.avg_laeq),
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

