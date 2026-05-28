// script.js – NetHealth UI logic (vanilla, secure)

// Utility: simple toast notification
function showToast(message, duration = 3000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, duration);
}

// Theme handling – persist in localStorage
function initTheme() {
  const saved = localStorage.getItem('nethealth-theme');
  const theme = saved || 'dark';
  document.documentElement.setAttribute('data-theme', theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('nethealth-theme', next);
  showToast(`Switched to ${next} mode`);
}

// Navigation drawer
function initNav() {
  const nav = document.getElementById('sideNav');
  const toggleBtn = document.getElementById('navToggle');
  toggleBtn.addEventListener('click', () => {
    nav.classList.toggle('open');
  });

  // Link handling – show sections
  const links = nav.querySelectorAll('.nav-link');
  links.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const target = link.dataset.section;
      showSection(target);
      // Mark active link
      links.forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      // Close nav on small screens
      if (window.innerWidth <= 768) nav.classList.remove('open');
    });
  });
}

function showSection(id) {
  const sections = document.querySelectorAll('.section');
  sections.forEach(sec => {
    if (sec.id === id) {
      sec.classList.add('active');
    } else {
      sec.classList.remove('active');
    }
  });
}

// Mock data generation
let mockData = {
  latency: [], // array of numbers for chart
  packetLoss: 0,
};

function generateMockData() {
  // Generate 30 points of latency (ms) between 20-120
  mockData.latency = Array.from({ length: 30 }, () => Math.floor(Math.random() * 100) + 20);
  // Packet loss percentage 0-5%
  mockData.packetLoss = (Math.random() * 5).toFixed(1) + '%';
}

// Render latency chart using Canvas API (simple line)
function renderLatencyChart() {
  const canvas = document.getElementById('latencyChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);

  const data = mockData.latency;
  const maxVal = Math.max(...data);
  const minVal = Math.min(...data);
  const padding = 10;
  const plotWidth = width - 2 * padding;
  const plotHeight = height - 2 * padding;

  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  data.forEach((val, idx) => {
    const x = padding + (idx / (data.length - 1)) * plotWidth;
    const y = padding + ((maxVal - val) / (maxVal - minVal)) * plotHeight;
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Axis baseline
  ctx.strokeStyle = 'rgba(255,255,255,0.3)';
  ctx.beginPath();
  ctx.moveTo(padding, height - padding);
  ctx.lineTo(width - padding, height - padding);
  ctx.stroke();
}

function updateMetrics() {
  // Packet loss display
  const lossEl = document.getElementById('packetLoss');
  if (lossEl) lossEl.textContent = mockData.packetLoss;

  renderLatencyChart();
}

// Export CSV of mock data
function exportCSV() {
  const rows = ['timestamp,latency'];
  const now = Date.now();
  mockData.latency.forEach((val, idx) => {
    rows.push(`${now + idx * 1000},${val}`);
  });
  const csvContent = rows.join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'nethealth_mock_data.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Mock data exported');
}

// Settings form handling
function initSettings() {
  const form = document.getElementById('settingsForm');
  if (!form) return;
  const intervalInput = document.getElementById('refreshInterval');
  // Load saved interval
  const saved = localStorage.getItem('nethealth-refresh-interval');
  if (saved) intervalInput.value = saved;

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const secs = parseInt(intervalInput.value, 10);
    if (isNaN(secs) || secs < 1) {
      showToast('Please enter a valid interval (>=1 sec)');
      return;
    }
    localStorage.setItem('nethealth-refresh-interval', secs);
    restartAutoRefresh(secs);
    showToast('Settings saved');
  });
}

let refreshTimer = null;
function restartAutoRefresh(seconds) {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    generateMockData();
    updateMetrics();
  }, seconds * 1000);
}

// Initialisation
function initApp() {
  initTheme();
  document.getElementById('themeToggle')?.addEventListener('click', toggleTheme);
  initNav();
  initSettings();
  // Export button
  const exportBtn = document.getElementById('exportBtn');
  exportBtn?.addEventListener('click', exportCSV);

  // Generate initial data and start auto‑refresh
  generateMockData();
  updateMetrics();
  const secs = parseInt(localStorage.getItem('nethealth-refresh-interval') || '5', 10);
  restartAutoRefresh(secs);

  // Show default section
  showSection('dashboard');
}

// Run after DOM is ready
document.addEventListener('DOMContentLoaded', initApp);
