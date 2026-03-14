/* =====================================================
   MARKET BREADTH DASHBOARD – VIETNAM MARKET
   script.js  |  Shared Utilities & Chart Helpers
   ===================================================== */

// ── Global Chart.js Defaults ──────────────────────────
Chart.defaults.font.family = "'DM Mono', monospace";
Chart.defaults.font.size   = 11;
Chart.defaults.color       = '#8b95a1';
Chart.defaults.plugins.tooltip.enabled = true;
Chart.defaults.plugins.legend.display  = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#0d1117';
Chart.defaults.plugins.tooltip.titleColor       = '#ffffff';
Chart.defaults.plugins.tooltip.bodyColor        = '#c8d0da';
Chart.defaults.plugins.tooltip.borderColor      = '#2d3748';
Chart.defaults.plugins.tooltip.borderWidth      = 1;
Chart.defaults.plugins.tooltip.padding          = 10;
Chart.defaults.plugins.tooltip.cornerRadius     = 6;
Chart.defaults.plugins.tooltip.titleFont        = { family: "'DM Mono', monospace", size: 11, weight: '500' };
Chart.defaults.plugins.tooltip.bodyFont         = { family: "'DM Mono', monospace", size: 11 };
Chart.defaults.scale.grid.color                 = 'rgba(0,0,0,0.05)';
Chart.defaults.scale.ticks.padding              = 6;

// ── Colour Palette ────────────────────────────────────
const COLORS = {
  green:    '#00c853',
  greenDim: 'rgba(0,200,83,0.12)',
  red:      '#f03e3e',
  redDim:   'rgba(240,62,62,0.08)',
  blue:     '#228be6',
  blueDim:  'rgba(34,139,230,0.10)',
  orange:   '#fd7e14',
  purple:   '#7950f2',
  teal:     '#20c997',
  yellow:   '#fab005',
  muted:    '#8b95a1',
};

// ── CSV Loader ─────────────────────────────────────────
function loadCSV(filePath) {
  return new Promise((resolve, reject) => {
    Papa.parse(filePath, {
      download:       true,
      header:         true,
      skipEmptyLines: true,
      dynamicTyping:  true,
      complete: (results) => resolve(results.data),
      error:    (err)     => reject(err),
    });
  });
}

// ── Date Helpers ──────────────────────────────────────
function cleanDate(raw) {
  if (!raw) return '';
  return String(raw).split(' ')[0];
}

function formatDateShort(dateStr) {
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
}

function formatDateFull(dateStr) {
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

// ── Range Filtering ───────────────────────────────────
/**
 * lastN – returns last N rows (0 = all)
 */
function lastN(arr, n) {
  if (!n || n >= arr.length) return arr;
  return arr.slice(-n);
}

/**
 * filterByDateRange – filter rows where Date is in [startDate, endDate].
 * startDate / endDate are "YYYY-MM" strings (month precision) or "YYYY-MM-DD".
 * Pass null to mean "no bound".
 */
function filterByDateRange(arr, startDate, endDate) {
  return arr.filter(r => {
    const d = r.Date || '';
    if (startDate && d < startDate) return false;
    if (endDate   && d > endDate + '-99') return false;
    return true;
  });
}

// ── Aggregation Helpers ────────────────────────────────
/**
 * aggregateWeekly – collapses daily rows into ISO-week buckets.
 * For each week the LAST trading day row is returned (for price/ratio series).
 * Numeric columns are averaged unless listed in sumCols.
 */
function aggregateWeekly(arr, sumCols = []) {
  const buckets = {};
  arr.forEach(r => {
    const d = new Date(r.Date);
    if (isNaN(d)) return;
    // ISO week key: year + week number
    const jan1 = new Date(d.getFullYear(), 0, 1);
    const week = Math.ceil((((d - jan1) / 86400000) + jan1.getDay() + 1) / 7);
    const key  = `${d.getFullYear()}-W${String(week).padStart(2,'0')}`;
    if (!buckets[key]) buckets[key] = [];
    buckets[key].push(r);
  });

  return Object.keys(buckets).sort().map(key => {
    const rows   = buckets[key];
    const last   = rows[rows.length - 1];
    const merged = { ...last };   // base from last day in week
    // For numeric cols, compute sum or average depending on type
    const numCols = Object.keys(last).filter(k => k !== 'Date' && typeof last[k] === 'number');
    numCols.forEach(col => {
      const vals = rows.map(r => r[col]).filter(v => v != null && !isNaN(v));
      if (vals.length === 0) { merged[col] = null; return; }
      if (sumCols.includes(col)) {
        merged[col] = vals.reduce((a,b) => a + b, 0);
      } else {
        merged[col] = vals.reduce((a,b) => a + b, 0) / vals.length;
      }
    });
    return merged;
  });
}

/**
 * aggregateMonthly – collapses daily rows into YYYY-MM buckets.
 * Same logic: last-day base, averages for ratio cols, sums for count cols.
 */
function aggregateMonthly(arr, sumCols = []) {
  const buckets = {};
  arr.forEach(r => {
    const key = r.Date ? r.Date.slice(0, 7) : null;
    if (!key) return;
    if (!buckets[key]) buckets[key] = [];
    buckets[key].push(r);
  });

  return Object.keys(buckets).sort().map(key => {
    const rows   = buckets[key];
    const last   = rows[rows.length - 1];
    const merged = { ...last };
    const numCols = Object.keys(last).filter(k => k !== 'Date' && typeof last[k] === 'number');
    numCols.forEach(col => {
      const vals = rows.map(r => r[col]).filter(v => v != null && !isNaN(v));
      if (vals.length === 0) { merged[col] = null; return; }
      if (sumCols.includes(col)) {
        merged[col] = vals.reduce((a,b) => a + b, 0);
      } else {
        merged[col] = vals.reduce((a,b) => a + b, 0) / vals.length;
      }
    });
    return merged;
  });
}

// ── Tick Reducer ──────────────────────────────────────
function sparseTickCallback(maxTicks, labels, formatFn) {
  const step = Math.max(1, Math.floor(labels.length / maxTicks));
  return function(val, idx) {
    return idx % step === 0 ? (formatFn ? formatFn(labels[idx]) : labels[idx]) : '';
  };
}

// ── Gradient Fill Helper ──────────────────────────────
function createGradient(ctx, color, alpha1 = 0.25, alpha2 = 0) {
  const gradient = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);
  gradient.addColorStop(0, hexToRgba(color, alpha1));
  gradient.addColorStop(1, hexToRgba(color, alpha2));
  return gradient;
}

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1,3), 16);
  const g = parseInt(hex.slice(3,5), 16);
  const b = parseInt(hex.slice(5,7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ── Sparkline Builder ─────────────────────────────────
function buildSparkline(canvasId, data, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  // Destroy any existing chart on this canvas
  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map((_, i) => i),
      datasets: [{
        data,
        borderColor:     color,
        borderWidth:     1.5,
        pointRadius:     0,
        tension:         0.4,
        fill:            true,
        backgroundColor: createGradient(ctx, color, 0.2, 0),
      }]
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      animation:           false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales:  { x: { display: false }, y: { display: false } }
    }
  });
}

// ── KPI Card Updater ──────────────────────────────────
function updateKpiCard(valueId, changeId, current, previous, format = 'decimal') {
  const valEl    = document.getElementById(valueId);
  const changeEl = document.getElementById(changeId);
  if (!valEl) return;

  const fmt = (v) => {
    if (v === null || v === undefined || isNaN(v)) return '–';
    if (format === 'integer') return Math.round(v).toLocaleString();
    if (format === 'pct')     return v.toFixed(1) + '%';
    return v.toFixed(2);
  };

  valEl.textContent = fmt(current);

  if (changeEl && previous !== null && !isNaN(previous) && !isNaN(current)) {
    const delta = current - previous;
    const sign  = delta > 0 ? '+' : '';
    changeEl.textContent = `${sign}${fmt(delta)} vs prev`;
    changeEl.className   = 'kpi-change ' + (delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat');
  }
}

// ── Range Button Wiring ───────────────────────────────
/**
 * wireRangeButtons – wires preset N-row buttons to a redraw function.
 */
function wireRangeButtons(groupId, redrawFn) {
  const wrap = document.getElementById(groupId);
  if (!wrap) return;
  wrap.querySelectorAll('.range-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      wrap.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const n = parseInt(btn.dataset.n) || 0;
      redrawFn(n);
    });
  });
}

/**
 * wireFreqButtons – wires Daily/Weekly/Monthly freq buttons.
 * @param {string} groupId
 * @param {Function} changeFn – called with 'daily' | 'weekly' | 'monthly'
 */
function wireFreqButtons(groupId, changeFn) {
  const wrap = document.getElementById(groupId);
  if (!wrap) return;
  wrap.querySelectorAll('.freq-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      wrap.querySelectorAll('.freq-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      changeFn(btn.dataset.freq);
    });
  });
}

/**
 * wireDateRangePicker – wires Start/End month inputs + Apply button.
 * @param {string} startId  – id of start <input type="month">
 * @param {string} endId    – id of end   <input type="month">
 * @param {string} applyId  – id of Apply button
 * @param {Function} applyFn – called with (startVal, endVal)
 * @param {string} clearId  – (optional) id of Clear/Reset button
 */
function wireDateRangePicker(startId, endId, applyId, applyFn, clearId) {
  const applyBtn = document.getElementById(applyId);
  if (applyBtn) {
    applyBtn.addEventListener('click', () => {
      const s = document.getElementById(startId)?.value || '';
      const e = document.getElementById(endId)?.value   || '';
      applyFn(s, e);
    });
  }
  if (clearId) {
    const clearBtn = document.getElementById(clearId);
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        const sEl = document.getElementById(startId);
        const eEl = document.getElementById(endId);
        if (sEl) sEl.value = '';
        if (eEl) eEl.value = '';
        applyFn('', '');
      });
    }
  }
}

// ── Chart Destroy Helper ──────────────────────────────
function destroyChart(chartRef) {
  if (chartRef && typeof chartRef.destroy === 'function') chartRef.destroy();
}

// ── Loading Overlay ───────────────────────────────────
function showLoading() { const el = document.getElementById('loadingOverlay'); if (el) el.style.display = 'flex'; }
function hideLoading() { const el = document.getElementById('loadingOverlay'); if (el) el.style.display = 'none'; }

// ── Last-Updated Stamp ────────────────────────────────
function setLastUpdated(dateStr) {
  const el = document.getElementById('lastUpdated');
  if (el && dateStr) el.textContent = 'DATA THRU: ' + formatDateFull(dateStr);
}
