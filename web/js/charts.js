/**
 * Noisy Pi - Chart Manager (Enhanced)
 */

class ChartManager {
    constructor() {
        this.levelsChart = null;
        this.anomalyChart = null;
        this.hourlyChart = null;
        this.historyChart = null;
        
        this.chartDefaults = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#8b949e',
                        font: { size: 10, family: "'JetBrains Mono', monospace" },
                        boxWidth: 12,
                        padding: 8
                    }
                },
                tooltip: {
                    backgroundColor: '#1a1f2e',
                    titleColor: '#e6edf3',
                    bodyColor: '#8b949e',
                    borderColor: '#2d3548',
                    borderWidth: 1,
                    padding: 8,
                    titleFont: { size: 11 },
                    bodyFont: { size: 10 }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    grid: {
                        color: 'rgba(45, 53, 72, 0.5)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#5c6370',
                        font: { size: 9 },
                        maxTicksLimit: 8
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(45, 53, 72, 0.5)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#5c6370',
                        font: { size: 9 }
                    }
                }
            }
        };
    }

    // Sound levels chart
    updateLevelsChart(data) {
        const ctx = document.getElementById('levels-chart');
        if (!ctx) return;

        const labels = data.map(d => new Date(d.timestamp));
        const meanData = data.map(d => parseFloat(d.mean_db) || null);
        const maxData = data.map(d => parseFloat(d.max_db) || null);
        const l90Data = data.map(d => parseFloat(d.l90_db) || null);

        if (this.levelsChart) {
            this.levelsChart.data.labels = labels;
            this.levelsChart.data.datasets[0].data = meanData;
            this.levelsChart.data.datasets[1].data = maxData;
            this.levelsChart.data.datasets[2].data = l90Data;
            this.levelsChart.update('none');
            return;
        }

        this.levelsChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Mean dB',
                        data: meanData,
                        borderColor: '#61afef',
                        backgroundColor: 'rgba(97, 175, 239, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 1.5
                    },
                    {
                        label: 'Max dB',
                        data: maxData,
                        borderColor: '#e06c75',
                        backgroundColor: 'transparent',
                        fill: false,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 1
                    },
                    {
                        label: 'L90 (Background)',
                        data: l90Data,
                        borderColor: '#98c379',
                        backgroundColor: 'transparent',
                        fill: false,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 1,
                        borderDash: [3, 3]
                    }
                ]
            },
            options: {
                ...this.chartDefaults,
                scales: {
                    ...this.chartDefaults.scales,
                    y: {
                        ...this.chartDefaults.scales.y,
                        title: {
                            display: true,
                            text: 'dB',
                            color: '#5c6370',
                            font: { size: 10 }
                        }
                    }
                }
            }
        });
    }

    // Anomaly chart
    updateAnomalyChart(data) {
        const ctx = document.getElementById('anomaly-chart');
        if (!ctx) return;

        const labels = data.map(d => new Date(d.timestamp));
        const anomalyData = data.map(d => parseFloat(d.anomaly_score) || 0);

        if (this.anomalyChart) {
            this.anomalyChart.data.labels = labels;
            this.anomalyChart.data.datasets[0].data = anomalyData;
            this.anomalyChart.update('none');
            return;
        }

        this.anomalyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Anomaly Score (Z-score)',
                    data: anomalyData,
                    borderColor: '#c678dd',
                    backgroundColor: 'rgba(198, 120, 221, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 1.5
                }]
            },
            options: {
                ...this.chartDefaults,
                plugins: {
                    ...this.chartDefaults.plugins,
                    annotation: {
                        annotations: {
                            threshold: {
                                type: 'line',
                                yMin: 2.5,
                                yMax: 2.5,
                                borderColor: '#e06c75',
                                borderWidth: 1,
                                borderDash: [5, 5],
                                label: {
                                    display: true,
                                    content: 'Threshold',
                                    position: 'end',
                                    color: '#e06c75',
                                    font: { size: 9 }
                                }
                            }
                        }
                    }
                },
                scales: {
                    ...this.chartDefaults.scales,
                    y: {
                        ...this.chartDefaults.scales.y,
                        min: 0,
                        suggestedMax: 4,
                        title: {
                            display: true,
                            text: 'Z-score',
                            color: '#5c6370',
                            font: { size: 10 }
                        }
                    }
                }
            }
        });
    }

    // Hourly statistics chart
    updateHourlyChart(data) {
        const ctx = document.getElementById('hourly-chart');
        if (!ctx) return;

        const labels = data.map(d => `${String(d.hour).padStart(2, '0')}:00`);
        const avgData = data.map(d => parseFloat(d.avg_db) || null);
        const maxData = data.map(d => parseFloat(d.max_db) || null);
        const countData = data.map(d => parseInt(d.count) || 0);

        if (this.hourlyChart) {
            this.hourlyChart.data.labels = labels;
            this.hourlyChart.data.datasets[0].data = avgData;
            this.hourlyChart.data.datasets[1].data = maxData;
            this.hourlyChart.data.datasets[2].data = countData;
            this.hourlyChart.update('none');
            return;
        }

        this.hourlyChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Avg dB',
                        data: avgData,
                        backgroundColor: 'rgba(97, 175, 239, 0.7)',
                        borderRadius: 2,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Max dB',
                        data: maxData,
                        backgroundColor: 'rgba(224, 108, 117, 0.5)',
                        borderRadius: 2,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Samples',
                        data: countData,
                        type: 'line',
                        borderColor: '#98c379',
                        backgroundColor: 'transparent',
                        pointRadius: 2,
                        borderWidth: 1,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                ...this.chartDefaults,
                scales: {
                    x: {
                        ...this.chartDefaults.scales.x,
                        type: 'category'
                    },
                    y: {
                        ...this.chartDefaults.scales.y,
                        position: 'left',
                        title: {
                            display: true,
                            text: 'dB',
                            color: '#5c6370',
                            font: { size: 10 }
                        }
                    },
                    y1: {
                        ...this.chartDefaults.scales.y,
                        position: 'right',
                        grid: { display: false },
                        title: {
                            display: true,
                            text: 'Samples',
                            color: '#5c6370',
                            font: { size: 10 }
                        }
                    }
                }
            }
        });
    }

    // History chart
    updateHistoryChart(data) {
        const ctx = document.getElementById('history-chart');
        if (!ctx) return;

        const labels = data.map(d => new Date(d.timestamp));
        const meanData = data.map(d => parseFloat(d.mean_db) || null);
        const maxData = data.map(d => parseFloat(d.max_db) || null);

        if (this.historyChart) {
            this.historyChart.data.labels = labels;
            this.historyChart.data.datasets[0].data = meanData;
            this.historyChart.data.datasets[1].data = maxData;
            this.historyChart.update('none');
            return;
        }

        this.historyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Mean dB',
                        data: meanData,
                        borderColor: '#61afef',
                        backgroundColor: 'rgba(97, 175, 239, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 1.5
                    },
                    {
                        label: 'Max dB',
                        data: maxData,
                        borderColor: '#e06c75',
                        backgroundColor: 'transparent',
                        fill: false,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 1
                    }
                ]
            },
            options: {
                ...this.chartDefaults,
                scales: {
                    ...this.chartDefaults.scales,
                    y: {
                        ...this.chartDefaults.scales.y,
                        title: {
                            display: true,
                            text: 'dB',
                            color: '#5c6370',
                            font: { size: 10 }
                        }
                    }
                }
            }
        });
    }
}
