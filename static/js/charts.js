// Global chart configuration
Chart.defaults.font.family = "'Inter', 'Segoe UI', sans-serif";
Chart.defaults.font.size = 13;
Chart.defaults.color = '#6b7280';

// Responsive canvas sizing
function resizeCharts() {
    const canvases = document.querySelectorAll('canvas');
    canvases.forEach(canvas => {
        const ctx = canvas.getContext('2d');
        canvas.height = canvas.clientHeight;
        canvas.width = canvas.clientWidth;
    });
}

window.addEventListener('resize', resizeCharts);
document.addEventListener('DOMContentLoaded', resizeCharts);
