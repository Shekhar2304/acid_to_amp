const socket = io();

let voltageChart, metalsChart;
let dataPoints = [];

// Initialize charts
document.addEventListener('DOMContentLoaded', function() {
    initCharts();
    loadRecentData();
    setupSocketListeners();
});

// Socket.IO listeners
function setupSocketListeners() {
    socket.on('sensor_update', function(data) {
        updateLiveMetrics(data);
        updateCharts(data);
        addTableRow(data);
    });
}

function initCharts() {
    const ctx1 = document.getElementById('voltageChart').getContext('2d');
    voltageChart = new Chart(ctx1, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Voltage (V)',
                data: [],
                borderColor: '#667eea',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });

    const ctx2 = document.getElementById('metalsChart').getContext('2d');
    metalsChart = new Chart(ctx2, {
        type: 'bar',
        data: {
            labels: ['Iron', 'Copper'],
            datasets: [{
                label: 'Concentration (mg/L)',
                data: [120, 50],
                backgroundColor: ['#ff6b6b', '#f093fb']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: true } }
        }
    });
}

function updateLiveMetrics(data) {
    document.getElementById('voltage').textContent = `${data.voltage}V`;
    document.getElementById('current').textContent = `${data.current}mA`;
    document.getElementById('ph').textContent = data.ph;
    document.getElementById('biofilm').textContent = data.biofilm;
}

function updateCharts(data) {
    const now = new Date().toLocaleTimeString();
    
    // Voltage chart
    voltageChart.data.labels.push(now);
    voltageChart.data.datasets[0].data.push(data.voltage);
    
    // Keep only last 20 points
    if (voltageChart.data.labels.length > 20) {
        voltageChart.data.labels.shift();
        voltageChart.data.datasets[0].data.shift();
    }
    
    voltageChart.update('none');
}

function addTableRow(data) {
    const tbody = document.getElementById('dataTable');
    const row = tbody.insertRow(0);
    row.classList.add('table-primary');
    
    row.innerHTML = `
        <td>${new Date(data.timestamp).toLocaleString()}</td>
        <td>${data.voltage}V</td>
        <td>${data.current}mA</td>
        <td>${data.ph}</td>
        <td>${data.iron} mg/L</td>
        <td>${data.copper} mg/L</td>
        <td><span class="badge bg-success">${data.biofilm}</span></td>
    `;
    
    // Keep only 10 rows
    while (tbody.rows.length > 10) {
        tbody.deleteRow(-1);
    }
}

function loadRecentData() {
    fetch('/api/recent-data')
        .then(response => response.json())
        .then(data => {
            data.forEach(item => addTableRow(item));
        });
}
