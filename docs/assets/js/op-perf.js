/**
 * Op Performance view — AMD MI355X vs NVIDIA B300 operator benchmark
 * visualizations using Chart.js and D3.js.
 *
 * Layout:
 *   1. Summary boxes
 *   2. Win/Loss stacked bar (Chart.js)  |  Ratio vs Batch line chart (Chart.js)
 *   3. TFLOPS parity scatter (Chart.js)
 *   4. Per-category D3 heatmaps (expandable)
 */

// Chart instance registry (destroy before re-render)
window._opPerfCharts = window._opPerfCharts || {};

function destroyChart(id) {
  if (window._opPerfCharts[id]) {
    window._opPerfCharts[id].destroy();
    delete window._opPerfCharts[id];
  }
}

// ─── Dark theme defaults for Chart.js ───
var CHART_COLORS = {
  amd: 'rgba(31, 111, 235, 0.8)',
  amdFill: 'rgba(31, 111, 235, 0.15)',
  nv: 'rgba(118, 185, 0, 0.8)',
  nvFill: 'rgba(118, 185, 0, 0.15)',
  tie: 'rgba(139, 148, 158, 0.4)',
  grid: '#30363d',
  text: '#8b949e',
  textBright: '#e6edf3',
  parity: '#8b949e',
};

var CATEGORY_COLORS = {
  gemm_bf16:          { border: '#58a6ff', bg: 'rgba(88,166,255,0.6)' },
  gemm_fp8:           { border: '#79c0ff', bg: 'rgba(121,192,255,0.6)' },
  gemm_fp8_blockscale:{ border: '#a5d6ff', bg: 'rgba(165,214,255,0.5)' },
  mha_prefill:        { border: '#f0883e', bg: 'rgba(240,136,62,0.6)' },
  mha_decode:         { border: '#d29922', bg: 'rgba(210,153,34,0.6)' },
  fused_moe:          { border: '#bc8cff', bg: 'rgba(188,140,255,0.6)' },
};

function chartDarkDefaults() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: CHART_COLORS.textBright, font: { size: 11 } } },
      tooltip: {
        backgroundColor: '#161b22',
        borderColor: '#30363d',
        borderWidth: 1,
        titleColor: '#e6edf3',
        bodyColor: '#e6edf3',
        bodyFont: { family: "'SFMono-Regular', Consolas, monospace", size: 11 },
      }
    }
  };
}

// ─── Main render ───
function renderOpPerf(data) {
  var el = document.getElementById("op-perf-view");
  if (!data || !data.categories) {
    el.innerHTML = '<h2>Operator Performance</h2><p class="empty">No performance data available.</p>';
    return;
  }

  var s = data.summary || {};
  var allModels = s.per_model || [];
  var moeCount = allModels.filter(function(m){return m.type==='MoE';}).length;
  var moeWins = allModels.filter(function(m){return m.type==='MoE' && m.geomean>1.05;}).length;
  var denseCount = allModels.filter(function(m){return m.type!=='MoE';}).length;
  var denseNvWins = allModels.filter(function(m){return m.type!=='MoE' && m.geomean<0.95;}).length;

  var html = '<h2>Operator Performance &mdash; MI355X vs B300</h2>';

  // Executive summary
  var summaryText = 'MoE models (dominant on OpenRouter): AMD wins ' + moeWins + '/' + moeCount + '. Dense models: NV wins ' + denseNvWins + '/' + denseCount + '.';
  html += '<div class="op-exec-summary">' + summaryText + '</div>';

  html += '<p class="op-perf-subtitle">Performance comparison across model shapes. ';
  html += '<span class="op-badge-amd">AMD MI355X (AITER)</span> vs ';
  html += '<span class="op-badge-nv">NVIDIA B300 (cuBLAS/SDPA)</span></p>';

  // Summary boxes
  var allStats = computeAllStats(data);
  var geoEqStr = allStats.geomean > 0 ? allStats.geomean.toFixed(3) + 'x' : 'N/A';

  // Also compute per-config geomean (for reference)
  var configLogSum = 0, configLogCount = 0;
  for (var ci = 0; ci < data.categories.length; ci++) {
    var crs = data.categories[ci].results;
    for (var ri = 0; ri < crs.length; ri++) {
      var _a = crs[ri].amd_tflops || crs[ri].amd_bw || 0;
      var _n = crs[ri].nv_tflops || crs[ri].nv_bw || 0;
      if (_a > 0 && _n > 0) { configLogSum += Math.log(_a / _n); configLogCount++; }
    }
  }
  var geoPerConfig = configLogCount > 0 ? Math.exp(configLogSum / configLogCount) : 0;
  var geoCfgStr = geoPerConfig > 0 ? geoPerConfig.toFixed(3) + 'x' : 'N/A';

  html += '<div class="oc-summary">';
  html += summaryBox(s.total_configs || 0, "Total Configs");
  html += summaryBox(s.operators || 0, "Operators");
  html += summaryBox(allStats.amdWins, "AMD Wins");
  html += summaryBox(allStats.nvWins, "NV Wins");
  html += summaryBox(geoEqStr, "GeoMean (equal-weight)");
  var geoInfStr = (s.geomean_inference || 0) > 0 ? s.geomean_inference.toFixed(3) + 'x' : 'N/A';
  html += summaryBox(geoInfStr, "GeoMean (inference-weighted)");
  html += '</div>';

  // Per-model breakdown, grouped by MoE vs Dense
  if (s.per_model && s.per_model.length > 0) {
    html += '<div class="op-perf-models">';
    html += '<h3>Per-Model Inference-Weighted GeoMean</h3>';

    var moeModels = s.per_model.filter(function(m) { return m.type === 'MoE'; });
    var denseModels = s.per_model.filter(function(m) { return m.type !== 'MoE'; });

    if (moeModels.length > 0) {
      html += '<h4 class="op-model-group-header">MoE Models</h4>';
      html += '<div class="op-model-grid">';
      for (var mi = 0; mi < moeModels.length; mi++) {
        html += buildModelCard(moeModels[mi], data);
      }
      html += '</div>';
    }

    if (denseModels.length > 0) {
      html += '<h4 class="op-model-group-header">Dense Models</h4>';
      html += '<div class="op-model-grid">';
      for (var mi = 0; mi < denseModels.length; mi++) {
        html += buildModelCard(denseModels[mi], data);
      }
      html += '</div>';
    }

    html += '</div>';
  }

  // Chart grid: win/loss bar + ratio line
  html += '<div class="op-perf-charts-grid">';
  html += '<div class="op-chart-card"><h3>Win / Loss by Category</h3>';
  html += '<div class="op-chart-wrap"><canvas id="chart-winloss"></canvas></div></div>';
  html += '<div class="op-chart-card"><h3>Performance Ratio vs Batch Size</h3>';
  html += '<div class="op-perf-chart-filters">';
  html += buildChartFilter(data, 'ratio-model', 'Model');
  html += buildChartFilter(data, 'ratio-tp', 'TP', 'tp');
  html += '</div>';
  html += '<div class="op-chart-wrap"><canvas id="chart-ratio-scaling"></canvas></div></div>';
  html += '</div>';

  // Scatter parity plot
  html += '<div class="op-chart-card op-chart-full"><h3>Performance Parity &mdash; every config plotted (above diagonal = AMD wins)</h3>';
  html += '<div class="op-chart-wrap op-chart-tall"><canvas id="chart-scatter"></canvas></div></div>';

  // Per-category heatmaps
  for (var c = 0; c < data.categories.length; c++) {
    var cat = data.categories[c];
    var stats = computeCatStats(cat.results);
    html += buildPerfCategory(cat, stats, data.gpus);
  }

  // Notes
  html += '<div class="op-perf-notes"><h3>Methodology &amp; Reproducibility</h3>';
  html += '<p class="op-perf-links">';
  html += '<a href="METHODOLOGY.md" target="_blank" class="op-doc-link">Design Doc &amp; Fairness Audit</a>';
  html += '<a href="https://github.com/sunway513/project-dashboard/blob/feat/op-perf-tab/scripts/reproduce.py" target="_blank" class="op-doc-link">Reproduce Any Data Point</a>';
  html += '<a href="https://github.com/sunway513/project-dashboard/blob/feat/op-perf-tab/docs/METHODOLOGY.md" target="_blank" class="op-doc-link">Precision Matching Table</a>';
  html += '</p>';
  html += '<ul>';
  html += '<li><strong>GEMM</strong>: Both use vendor-optimized BLAS (hipBLASLt / cuBLAS) via torch.matmul and torch._scaled_mm.</li>';
  html += '<li><strong>Attention</strong>: Both use PyTorch SDPA (FlashAttention backend).</li>';
  html += '<li><strong>Fused MoE</strong>: AMD uses AITER fused_moe (FP8 for production models). NV uses best-of vLLM/FlashInfer (BF16 only &mdash; <a href="METHODOLOGY.md#fp8-moe-availability-verified-2026-03-22" target="_blank">FP8 MoE not yet available on Blackwell</a>).</li>';
  html += '<li><strong>Precision</strong>: Each model benchmarked at its OpenRouter production precision (FP8, BF16, or INT4).</li>';
  html += '<li><strong>Reproducibility</strong>: Click any heatmap cell to copy the exact repro command. Run <code>python3 scripts/reproduce.py --generate-all</code> for full script.</li>';
  html += '</ul></div>';

  if (data.lastUpdated) {
    html += '<div class="oc-updated">Data collected: ' + escapeHtml(data.lastUpdated) + '</div>';
  }

  el.innerHTML = html;

  // Render charts (must be after innerHTML so canvases exist)
  renderWinLossChart(data);
  renderRatioScalingChart(data);
  renderScatterChart(data);
  attachPerfFilters(data);
}

// ─── Stats helpers ───
function computeAllStats(data) {
  var matched = 0, amdWins = 0, nvWins = 0;
  var opGeos = []; // per-operator geomeans for equal-weight calculation

  for (var c = 0; c < data.categories.length; c++) {
    var s = computeCatStats(data.categories[c].results);
    matched += s.matched;
    amdWins += s.amdWins;
    nvWins += s.nvWins;
    if (s.geomean > 0) {
      opGeos.push(s.geomean);
    }
  }

  // Equal-weight geomean across operators (each operator counts equally)
  var geomean = 0;
  if (opGeos.length > 0) {
    var logSum = 0;
    for (var i = 0; i < opGeos.length; i++) { logSum += Math.log(opGeos[i]); }
    geomean = Math.exp(logSum / opGeos.length);
  }

  return { matched: matched, amdWins: amdWins, nvWins: nvWins, geomean: geomean, numOps: opGeos.length };
}

// Get AMD/NV performance values — works for both TFLOPS and bandwidth ops
function getPerfValues(r) {
  var amd = r.amd_tflops || r.amd_bw || 0;
  var nv = r.nv_tflops || r.nv_bw || 0;
  var unit = r.amd_tflops ? 'TFLOPS' : 'GB/s';
  return { amd: amd, nv: nv, unit: unit };
}

function computeCatStats(results) {
  var matched = 0, amdWins = 0, nvWins = 0, ratios = [];
  for (var i = 0; i < results.length; i++) {
    var pv = getPerfValues(results[i]);
    if (pv.amd > 0 && pv.nv > 0) {
      matched++;
      var ratio = pv.amd / pv.nv;
      ratios.push(ratio);
      if (ratio > 1.05) amdWins++;
      else if (ratio < 0.95) nvWins++;
    }
  }
  var avg = ratios.length > 0 ? ratios.reduce(function(a,b){return a+b;}, 0) / ratios.length : 0;
  var logSum = 0;
  for (var j = 0; j < ratios.length; j++) { if (ratios[j] > 0) logSum += Math.log(ratios[j]); }
  var geomean = ratios.length > 0 ? Math.exp(logSum / ratios.length) : 0;
  return { matched: matched, amdWins: amdWins, nvWins: nvWins, avg: avg, geomean: geomean, ratios: ratios };
}

function summaryBox(num, label) {
  return '<div class="oc-summary-box"><div class="oc-summary-num">' + num + '</div><div class="oc-summary-label">' + label + '</div></div>';
}

// ─── Chart 1: Win/Loss stacked bar ───
function renderWinLossChart(data) {
  destroyChart('winloss');
  var canvas = document.getElementById('chart-winloss');
  if (!canvas) return;

  var labels = [];
  var amdData = [], nvData = [], tieData = [];
  for (var c = 0; c < data.categories.length; c++) {
    var cat = data.categories[c];
    var s = computeCatStats(cat.results);
    labels.push(cat.name);
    amdData.push(s.amdWins);
    nvData.push(s.nvWins);
    tieData.push(s.matched - s.amdWins - s.nvWins);
  }

  window._opPerfCharts['winloss'] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        { label: 'AMD Wins', data: amdData, backgroundColor: CHART_COLORS.amd },
        { label: 'Tie (±5%)', data: tieData, backgroundColor: CHART_COLORS.tie },
        { label: 'NV Wins', data: nvData, backgroundColor: CHART_COLORS.nv },
      ]
    },
    options: Object.assign({}, chartDarkDefaults(), {
      indexAxis: 'y',
      scales: {
        x: { stacked: true, ticks: { color: CHART_COLORS.text }, grid: { color: CHART_COLORS.grid } },
        y: { stacked: true, ticks: { color: CHART_COLORS.textBright, font: { size: 12 } }, grid: { display: false } }
      },
      plugins: Object.assign({}, chartDarkDefaults().plugins, {
        legend: { position: 'bottom', labels: { color: CHART_COLORS.textBright, usePointStyle: true, pointStyle: 'rect' } }
      })
    })
  });
}

// ─── Chart 2: Ratio vs Batch line chart ───
function renderRatioScalingChart(data, filterModel, filterTp) {
  destroyChart('ratio');
  var canvas = document.getElementById('chart-ratio-scaling');
  if (!canvas) return;

  filterModel = filterModel || 'all';
  filterTp = filterTp || 'all';

  // Group results by op sub-type
  var groups = {};
  for (var c = 0; c < data.categories.length; c++) {
    var cat = data.categories[c];
    for (var i = 0; i < cat.results.length; i++) {
      var r = cat.results[i];
      var _pv = getPerfValues(r);
      if (_pv.amd <= 0 || _pv.nv <= 0) continue;
      if (filterModel !== 'all' && r.model !== filterModel) continue;
      if (filterTp !== 'all' && String(r.tp) !== String(filterTp)) continue;

      var opKey;
      if (cat.id === 'gemm') opKey = r.op;
      else if (cat.id === 'attention') opKey = 'mha_' + (r.mode || 'prefill');
      else opKey = 'fused_moe';

      if (!groups[opKey]) groups[opKey] = {};
      var M = r.M || r.batch || 0;
      if (!groups[opKey][M]) groups[opKey][M] = [];
      groups[opKey][M].push(_pv.amd / _pv.nv);
    }
  }

  // Build datasets
  var mValues = [1, 4, 16, 64, 256, 1024, 4096];
  var datasets = [];

  for (var opKey in groups) {
    var color = CATEGORY_COLORS[opKey] || { border: '#8b949e', bg: 'rgba(139,148,158,0.4)' };
    var points = [];
    for (var mi = 0; mi < mValues.length; mi++) {
      var m = mValues[mi];
      var vals = groups[opKey][m];
      if (vals && vals.length > 0) {
        var avg = vals.reduce(function(a,b){return a+b;},0) / vals.length;
        points.push({ x: mi, y: avg });
      }
    }
    if (points.length > 0) {
      datasets.push({
        label: opKey,
        data: points,
        borderColor: color.border,
        backgroundColor: color.bg,
        borderWidth: 2,
        pointRadius: 4,
        tension: 0.3,
        fill: false,
      });
    }
  }

  // Parity line
  datasets.push({
    label: 'Parity (1.0x)',
    data: mValues.map(function(_, i) { return { x: i, y: 1.0 }; }),
    borderColor: CHART_COLORS.parity,
    borderDash: [6, 4],
    borderWidth: 1.5,
    pointRadius: 0,
    fill: false,
  });

  window._opPerfCharts['ratio'] = new Chart(canvas, {
    type: 'line',
    data: { labels: mValues.map(String), datasets: datasets },
    options: Object.assign({}, chartDarkDefaults(), {
      scales: {
        x: {
          title: { display: true, text: 'Batch / M', color: CHART_COLORS.text },
          ticks: { color: CHART_COLORS.text },
          grid: { color: CHART_COLORS.grid },
        },
        y: {
          type: 'logarithmic',
          title: { display: true, text: 'AMD / NV TFLOPS Ratio', color: CHART_COLORS.text },
          ticks: {
            color: CHART_COLORS.text,
            callback: function(v) { return v + 'x'; }
          },
          grid: { color: CHART_COLORS.grid },
        }
      },
      plugins: Object.assign({}, chartDarkDefaults().plugins, {
        legend: { position: 'bottom', labels: { color: CHART_COLORS.textBright, usePointStyle: true, font: { size: 10 } } },
        tooltip: Object.assign({}, chartDarkDefaults().plugins.tooltip, {
          callbacks: {
            label: function(ctx) {
              return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(2) + 'x';
            }
          }
        })
      })
    })
  });
}

// ─── Chart 3: Scatter parity plot ───
function renderScatterChart(data) {
  destroyChart('scatter');
  var canvas = document.getElementById('chart-scatter');
  if (!canvas) return;

  var datasetMap = {};
  var colorMap = {
    'GEMM':                              { bg: 'rgba(88,166,255,0.50)',  border: '#58a6ff' },
    'Attention':                         { bg: 'rgba(240,136,62,0.50)',  border: '#f0883e' },
    'Fused MoE (production precision)':  { bg: 'rgba(188,140,255,0.50)', border: '#bc8cff' },
    'RMSNorm':                           { bg: 'rgba(63,185,80,0.50)',   border: '#3fb950' },
    'RoPE':                              { bg: 'rgba(219,171,255,0.50)', border: '#d2a8ff' },
    'FP8 Quantization':                  { bg: 'rgba(255,159,28,0.50)',  border: '#ff9f1c' },
    'Softmax':                           { bg: 'rgba(121,192,255,0.50)', border: '#79c0ff' },
    'Communication (8 GPU, TP/EP)':      { bg: 'rgba(218,54,51,0.50)',   border: '#da3633' },
    'EP Communication (Mori vs DeepEP)': { bg: 'rgba(255,123,114,0.50)', border: '#ff7b72' },
  };

  for (var c = 0; c < data.categories.length; c++) {
    var cat = data.categories[c];
    var col = colorMap[cat.name] || { bg: 'rgba(139,148,158,0.4)', border: '#8b949e' };

    var points = [];
    for (var i = 0; i < cat.results.length; i++) {
      var r = cat.results[i];
      var _spv = getPerfValues(r);
      if (_spv.amd > 0.01 && _spv.nv > 0.01) {
        points.push({
          x: _spv.nv,
          y: _spv.amd,
          _model: r.model,
          _op: r.op || r.mode || '',
          _M: r.M || r.batch || 0,
          _tp: r.tp,
        });
      }
    }

    if (points.length > 0) {
      datasetMap[cat.name] = {
        label: cat.name + ' (' + points.length + ')',
        data: points,
        backgroundColor: col.bg,
        borderColor: col.border,
        borderWidth: 1,
        pointRadius: 3.5,
        pointHoverRadius: 6,
      };
    }
  }

  var datasets = Object.keys(datasetMap).map(function(k) { return datasetMap[k]; });

  // Parity line y=x
  datasets.push({
    label: 'Parity (y=x)',
    type: 'line',
    data: [{ x: 0.01, y: 0.01 }, { x: 3000, y: 3000 }],
    borderColor: CHART_COLORS.parity,
    borderDash: [8, 4],
    borderWidth: 1.5,
    pointRadius: 0,
    fill: false,
    order: 10,
  });

  window._opPerfCharts['scatter'] = new Chart(canvas, {
    type: 'scatter',
    data: { datasets: datasets },
    options: Object.assign({}, chartDarkDefaults(), {
      scales: {
        x: {
          type: 'logarithmic',
          title: { display: true, text: 'NV B300 TFLOPS  →', color: '#7ee787', font: { size: 12 } },
          ticks: { color: CHART_COLORS.text },
          grid: { color: CHART_COLORS.grid },
          min: 0.1,
        },
        y: {
          type: 'logarithmic',
          title: { display: true, text: '← AMD MI355X TFLOPS', color: '#58a6ff', font: { size: 12 } },
          ticks: { color: CHART_COLORS.text },
          grid: { color: CHART_COLORS.grid },
          min: 0.1,
        }
      },
      plugins: Object.assign({}, chartDarkDefaults().plugins, {
        legend: { position: 'bottom', labels: { color: CHART_COLORS.textBright, usePointStyle: true, font: { size: 11 } } },
        tooltip: Object.assign({}, chartDarkDefaults().plugins.tooltip, {
          callbacks: {
            label: function(ctx) {
              var d = ctx.raw;
              var ratio = (d.y / d.x).toFixed(2);
              return d._model + ' ' + d._op + ' M=' + d._M + ' TP=' + d._tp +
                ' | AMD:' + d.y.toFixed(1) + ' NV:' + d.x.toFixed(1) + ' (' + ratio + 'x)';
            }
          }
        })
      })
    })
  });
}

// ─── Chart filter helpers ───
function buildChartFilter(data, id, label, field) {
  field = field || 'model';
  var vals = {};
  for (var c = 0; c < data.categories.length; c++) {
    for (var i = 0; i < data.categories[c].results.length; i++) {
      var v = data.categories[c].results[i][field];
      if (v !== undefined && v !== null) vals[v] = true;
    }
  }
  var sorted = Object.keys(vals).sort();
  var html = '<label class="op-perf-filter"><span>' + label + ':</span>';
  html += '<select class="op-chart-filter" data-chart="ratio" data-field="' + field + '" id="filter-' + id + '">';
  html += '<option value="all">All</option>';
  for (var i = 0; i < sorted.length; i++) {
    html += '<option value="' + escapeHtml(sorted[i]) + '">' + escapeHtml(sorted[i]) + '</option>';
  }
  html += '</select></label>';
  return html;
}

// ─── Category heatmap (D3.js) ───
function buildPerfCategory(cat, stats, gpus) {
  var html = '<details class="oc-category" id="perf-cat-' + cat.id + '">';
  html += '<summary>';
  html += '<span class="oc-cat-name">' + escapeHtml(cat.name) + '</span>';
  html += '<span class="oc-cat-count">' + cat.results.length + ' configs</span>';
  html += '<span class="oc-cat-badges">';
  if (stats.matched > 0) {
    html += '<span class="oc-badge-amd">AMD: ' + stats.amdWins + '</span>';
    html += '<span class="oc-badge-nv">NV: ' + stats.nvWins + '</span>';
    html += '<span class="op-badge-ratio">GeoMean: ' + (stats.geomean > 0 ? stats.geomean.toFixed(2) + 'x' : 'N/A') + '</span>';
  } else {
    html += '<span class="op-badge-ratio">NV-only data (' + cat.results.length + ' configs)</span>';
  }
  html += '</span></summary>';

  // Filters
  html += '<div class="op-perf-filters" data-cat="' + cat.id + '">';
  html += buildFilterDropdown(cat, 'model', 'Model');
  html += buildFilterDropdown(cat, 'tp', 'TP');
  if (cat.id === 'gemm') html += buildFilterDropdown(cat, 'op', 'Precision');
  html += '</div>';

  // D3 heatmap container
  html += '<div class="d3-heatmap-container" id="heatmap-' + cat.id + '"></div>';
  // Tooltip div
  html += '<div class="d3-tooltip" id="tooltip-' + cat.id + '" style="display:none"></div>';

  html += '</details>';
  return html;
}

function buildFilterDropdown(cat, field, label) {
  var vals = {};
  for (var i = 0; i < cat.results.length; i++) {
    var v = cat.results[i][field];
    if (v !== undefined && v !== null) vals[v] = true;
  }
  var sorted = Object.keys(vals).sort(function(a, b) {
    var na = parseFloat(a), nb = parseFloat(b);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return a < b ? -1 : 1;
  });
  var html = '<label class="op-perf-filter"><span>' + label + ':</span>';
  html += '<select class="op-filter-select" data-cat="' + cat.id + '" data-field="' + field + '">';
  html += '<option value="all">All</option>';
  for (var i = 0; i < sorted.length; i++) {
    html += '<option value="' + escapeHtml(sorted[i]) + '">' + escapeHtml(sorted[i]) + '</option>';
  }
  html += '</select></label>';
  return html;
}

// ─── D3 Heatmap rendering ───
function renderD3Heatmap(catId, cat, gpus, filters) {
  filters = filters || {};
  var container = document.getElementById('heatmap-' + catId);
  var tooltip = document.getElementById('tooltip-' + catId);
  if (!container) return;

  // Filter results (include one-sided data)
  var results = cat.results.filter(function(r) {
    for (var f in filters) {
      if (filters[f] !== 'all' && String(r[f]) !== String(filters[f])) return false;
    }
    var _fpv = getPerfValues(r);
    return _fpv.amd > 0 || _fpv.nv > 0;
  });

  if (results.length === 0) {
    container.innerHTML = '<p class="empty">No results match filters.</p>';
    return;
  }

  // Group into rows (model+op+label+tp) and columns (M/batch)
  var rowMap = {};
  var colSet = {};
  results.forEach(function(r) {
    var rowKey;
    if (catId === 'gemm') rowKey = r.model + ' | ' + r.op + ' | ' + (r.label || '') + ' TP=' + r.tp;
    else if (catId === 'attention') rowKey = r.model + ' | ' + (r.mode || '') + ' HQ=' + r.hq + ' TP=' + r.tp;
    else rowKey = r.model + ' | ' + (r.label || '') + ' TP=' + r.tp;

    var colKey = r.M || r.batch || 0;
    colSet[colKey] = true;
    if (!rowMap[rowKey]) rowMap[rowKey] = {};
    rowMap[rowKey][colKey] = r;
  });

  var rows = Object.keys(rowMap).sort();
  var cols = Object.keys(colSet).map(Number).sort(function(a,b){ return a-b; });

  // Dimensions
  var cellW = 70, cellH = 26;
  var labelW = Math.min(350, 12 * Math.max.apply(null, rows.map(function(r){ return r.length; })));
  var headerH = 30;
  var svgW = labelW + cols.length * cellW + 20;
  var svgH = headerH + rows.length * cellH + 10;

  container.innerHTML = '';
  var svg = d3.select(container).append('svg')
    .attr('width', svgW)
    .attr('height', svgH)
    .style('overflow', 'visible');

  // Color scale: diverging green (NV wins) → gray → blue (AMD wins)
  // Domain: log2(ratio), clamped to [-3, 3]
  var colorScale = d3.scaleDiverging()
    .domain([-2, 0, 2])
    .interpolator(d3.interpolateRgbBasis(['#238636', '#30363d', '#1f6feb']));

  // Column headers
  svg.selectAll('.col-header')
    .data(cols)
    .enter().append('text')
    .attr('x', function(d, i) { return labelW + i * cellW + cellW / 2; })
    .attr('y', headerH - 8)
    .attr('text-anchor', 'middle')
    .attr('fill', CHART_COLORS.text)
    .attr('font-size', '11px')
    .attr('font-family', "'SFMono-Regular', Consolas, monospace")
    .text(function(d) { return 'M=' + d; });

  // Row groups
  var rowGroups = svg.selectAll('.hm-row')
    .data(rows)
    .enter().append('g')
    .attr('transform', function(d, i) { return 'translate(0,' + (headerH + i * cellH) + ')'; });

  // Row labels
  rowGroups.append('text')
    .attr('x', labelW - 8)
    .attr('y', cellH / 2 + 4)
    .attr('text-anchor', 'end')
    .attr('fill', CHART_COLORS.text)
    .attr('font-size', '10px')
    .attr('font-family', "'SFMono-Regular', Consolas, monospace")
    .text(function(d) { return d.length > 45 ? d.substring(0, 42) + '...' : d; });

  // Cells
  rowGroups.each(function(rowKey) {
    var rowData = rowMap[rowKey];
    d3.select(this).selectAll('.hm-cell')
      .data(cols)
      .enter().append('rect')
      .attr('class', 'd3-heatmap-cell')
      .attr('x', function(d, i) { return labelW + i * cellW; })
      .attr('y', 0)
      .attr('width', cellW - 2)
      .attr('height', cellH - 2)
      .attr('rx', 3)
      .attr('fill', function(col) {
        var r = rowData[col];
        var _hpv = r ? getPerfValues(r) : {amd:0, nv:0};
        if (!r) return '#21262d';
        if (_hpv.amd <= 0 && _hpv.nv <= 0) return '#21262d';
        if (_hpv.amd <= 0) return 'rgba(118, 185, 0, 0.3)'; // NV only
        if (_hpv.nv <= 0) return 'rgba(31, 111, 235, 0.3)'; // AMD only
        var logRatio = Math.log2(_hpv.amd / _hpv.nv);
        return colorScale(Math.max(-2, Math.min(2, logRatio)));
      })
      .on('mouseover', function(event, col) {
        var r = rowData[col];
        if (!r) return;
        var _tpv = getPerfValues(r);
        var ratio = (_tpv.amd > 0 && _tpv.nv > 0) ? (_tpv.amd / _tpv.nv).toFixed(2) + 'x' : 'N/A';
        tooltip.style.display = 'block';
        var ttHtml = '<strong>' + escapeHtml(rowKey) + '</strong><br>M=' + (r.M || r.batch || col) + '<br>';
        if (_tpv.amd > 0) ttHtml += 'AMD: <span style="color:#58a6ff">' + _tpv.amd.toFixed(1) + ' ' + _tpv.unit + '</span><br>';
        if (_tpv.nv > 0) ttHtml += 'NV: <span style="color:#7ee787">' + _tpv.nv.toFixed(1) + ' ' + _tpv.unit + '</span><br>';
        if (_tpv.amd > 0 && _tpv.nv > 0) ttHtml += 'Ratio: ' + ratio + '<br>';
        ttHtml += '<span style="color:#8b949e;font-size:10px">Click to copy repro command</span>';
        tooltip.innerHTML = ttHtml;
        var rect = container.getBoundingClientRect();
        tooltip.style.left = (event.pageX - rect.left + 12) + 'px';
        tooltip.style.top = (event.pageY - rect.top - 60) + 'px';
      })
      .on('mouseout', function() { tooltip.style.display = 'none'; })
      .on('click', function(event, col) {
        var r = rowMap[rowKey] ? rowMap[rowKey][col] : null;
        if (!r) return;
        var cmd = generateReproCommand(catId, r);
        if (navigator.clipboard) {
          navigator.clipboard.writeText(cmd).then(function() {
            tooltip.innerHTML = '<span style="color:#7ee787">Copied to clipboard!</span>';
            setTimeout(function() { tooltip.style.display = 'none'; }, 1000);
          });
        } else {
          prompt('Repro command:', cmd);
        }
      });

    // Cell text (ratio)
    d3.select(this).selectAll('.hm-text')
      .data(cols)
      .enter().append('text')
      .attr('x', function(d, i) { return labelW + i * cellW + cellW / 2 - 1; })
      .attr('y', cellH / 2 + 4)
      .attr('text-anchor', 'middle')
      .attr('fill', '#e6edf3')
      .attr('font-size', '10px')
      .attr('font-family', "'SFMono-Regular', Consolas, monospace")
      .attr('pointer-events', 'none')
      .text(function(col) {
        var r = rowData[col];
        var _cpv = r ? getPerfValues(r) : {amd:0,nv:0};
        if (!r || (_cpv.amd <= 0 && _cpv.nv <= 0)) return '—';
        if (_cpv.amd <= 0) return _cpv.nv.toFixed(0);
        if (_cpv.nv <= 0) return _cpv.amd.toFixed(0);
        return (_cpv.amd / _cpv.nv).toFixed(2) + 'x';
      });
  });
}

// ─── Model card builder with tooltip ───
function buildModelCard(m, data) {
  var cls = m.geomean > 1.05 ? 'op-model-amd' : m.geomean < 0.95 ? 'op-model-nv' : 'op-model-tie';
  var isMoE = m.type === 'MoE';
  var weights = isMoE
    ? {moe_fused:0.40, attention:0.22, gemm:0.13, communication:0.10, rmsnorm:0.05, rope:0.03, softmax:0.04, quant:0.03}
    : {gemm:0.48, attention:0.27, communication:0.10, rmsnorm:0.05, rope:0.03, softmax:0.04, quant:0.03};

  // Compute per-op breakdown for this model
  var breakdown = '';
  for (var c = 0; c < data.categories.length; c++) {
    var cat = data.categories[c];
    var w = weights[cat.id] || 0;
    if (w <= 0) continue;
    var rs = [];
    for (var i = 0; i < cat.results.length; i++) {
      var r = cat.results[i];
      if (r.model !== m.model) continue;
      var a = r.amd_tflops || r.amd_bw || 0;
      var n = r.nv_tflops || r.nv_bw || 0;
      if (a > 0 && n > 0) rs.push(a / n);
    }
    if (rs.length > 0) {
      var logSum = 0;
      for (var j = 0; j < rs.length; j++) logSum += Math.log(rs[j]);
      var geo = Math.exp(logSum / rs.length);
      breakdown += cat.name.substring(0, 12) + ': ' + geo.toFixed(2) + 'x × ' + (w * 100).toFixed(0) + '%\\n';
    }
  }

  var html = '<div class="op-model-card ' + cls + '">';
  html += '<div class="op-model-tooltip">';
  html += '<strong>' + escapeHtml(m.model) + '</strong><br>';
  html += 'Inference-weighted GeoMean: ' + m.geomean.toFixed(3) + 'x<br><br>';
  html += breakdown.replace(/\\n/g, '<br>');
  html += '</div>';
  html += '<div class="op-model-name">' + escapeHtml(m.model) + '</div>';
  html += '<div class="op-model-type">' + escapeHtml(m.type) + '</div>';
  html += '<div class="op-model-geo">' + m.geomean.toFixed(3) + 'x</div>';
  html += '</div>';
  return html;
}

// ─── Repro command generator ───
function generateReproCommand(catId, r) {
  var M = r.M || r.batch || 0;
  if (catId === 'gemm') {
    var op = r.op || 'gemm_bf16';
    if (op.indexOf('fp8') >= 0 && op.indexOf('block') < 0) {
      return 'python3 -c "import torch; M,N,K=' + M + ',' + r.N + ',' + r.K +
        '; A=torch.randn(M,K,dtype=torch.bfloat16,device=\'cuda\').to(torch.float8_e4m3fn)' +
        '; B=torch.randn(N,K,dtype=torch.bfloat16,device=\'cuda\').to(torch.float8_e4m3fn)' +
        '; s=torch.tensor(1.0,device=\'cuda\')' +
        '; [torch._scaled_mm(A,B.t(),scale_a=s,scale_b=s,out_dtype=torch.bfloat16) for _ in range(100)]' +
        '; torch.cuda.synchronize(); import time; t=time.time()' +
        '; [torch._scaled_mm(A,B.t(),scale_a=s,scale_b=s,out_dtype=torch.bfloat16) for _ in range(100)]' +
        '; torch.cuda.synchronize(); ms=(time.time()-t)/100*1000' +
        '; print(f\'FP8 GEMM M={M} N={N} K={K}: {2*M*N*K/ms*1e-9:.1f} TFLOPS ({ms:.3f}ms)\')"';
    } else {
      return 'python3 -c "import torch; M,N,K=' + M + ',' + r.N + ',' + r.K +
        '; A=torch.randn(M,K,dtype=torch.bfloat16,device=\'cuda\')' +
        '; B=torch.randn(K,N,dtype=torch.bfloat16,device=\'cuda\')' +
        '; [torch.matmul(A,B) for _ in range(100)]' +
        '; torch.cuda.synchronize(); import time; t=time.time()' +
        '; [torch.matmul(A,B) for _ in range(100)]' +
        '; torch.cuda.synchronize(); ms=(time.time()-t)/100*1000' +
        '; print(f\'BF16 GEMM M={M} N={N} K={K}: {2*M*N*K/ms*1e-9:.1f} TFLOPS ({ms:.3f}ms)\')"';
    }
  } else if (catId === 'attention') {
    var hq = r.hq || 128, hk = r.hk || 8, hd = r.head_dim || 128;
    var sq = r.seq_q || 4096, sk = r.seq_k || 4096;
    var batch = r.batch || 1;
    return 'python3 -c "import torch,torch.nn.functional as F; ' +
      'q=torch.randn(' + batch + ',' + hq + ',' + sq + ',' + hd + ',dtype=torch.bfloat16,device=\'cuda\'); ' +
      'k=torch.randn(' + batch + ',' + hk + ',' + sk + ',' + hd + ',dtype=torch.bfloat16,device=\'cuda\'); ' +
      'v=k.clone(); ' +
      (hk !== hq ? 'k=k.repeat_interleave(' + (hq/hk) + ',dim=1); v=v.repeat_interleave(' + (hq/hk) + ',dim=1); ' : '') +
      '[F.scaled_dot_product_attention(q,k,v) for _ in range(30)]; ' +
      'torch.cuda.synchronize(); import time; t=time.time(); ' +
      '[F.scaled_dot_product_attention(q,k,v) for _ in range(30)]; ' +
      'torch.cuda.synchronize(); ms=(time.time()-t)/30*1000; ' +
      'print(f\'Attn B=' + batch + ' HQ=' + hq + ' S=' + sq + '/' + sk + ': {2*' + batch + '*' + hq + '*' + sq + '*' + sk + '*2*' + hd + '/ms*1e-9:.1f} TFLOPS ({ms:.3f}ms)\')"';
  } else if (catId === 'moe_fused') {
    return '# AMD: AITER fused_moe (run in MI355X container)\n' +
      '# NV: vLLM fused_experts (run on B300)\n' +
      '# See scripts/reproduce.py --op moe_fused --M ' + M + ' --N ' + r.N + ' --K ' + r.K + ' --E ' + r.E + ' --top-k ' + r.top_k;
  } else {
    return 'python3 scripts/reproduce.py --op ' + catId + ' --M ' + M + ' --N ' + (r.N || r.K || '') + ' --gpu both';
  }
}

// ─── Event binding ───
function attachPerfFilters(data) {
  // Category heatmap filters
  var selects = document.querySelectorAll('.op-filter-select');
  for (var i = 0; i < selects.length; i++) {
    selects[i].addEventListener('change', function() {
      var catId = this.getAttribute('data-cat');
      updateHeatmap(catId, data);
    });
  }

  // Ratio chart filters
  var chartFilters = document.querySelectorAll('.op-chart-filter');
  for (var i = 0; i < chartFilters.length; i++) {
    chartFilters[i].addEventListener('change', function() {
      var modelSel = document.getElementById('filter-ratio-model');
      var tpSel = document.getElementById('filter-ratio-tp');
      renderRatioScalingChart(data, modelSel ? modelSel.value : 'all', tpSel ? tpSel.value : 'all');
    });
  }

  // Render initial heatmaps when details are opened
  var details = document.querySelectorAll('.oc-category[id^="perf-cat-"]');
  for (var i = 0; i < details.length; i++) {
    details[i].addEventListener('toggle', function() {
      if (this.open) {
        var catId = this.id.replace('perf-cat-', '');
        updateHeatmap(catId, data);
      }
    });
  }
}

function updateHeatmap(catId, data) {
  var cat = null;
  for (var i = 0; i < data.categories.length; i++) {
    if (data.categories[i].id === catId) { cat = data.categories[i]; break; }
  }
  if (!cat) return;

  var filters = {};
  var filterSelects = document.querySelectorAll('.op-filter-select[data-cat="' + catId + '"]');
  for (var i = 0; i < filterSelects.length; i++) {
    var field = filterSelects[i].getAttribute('data-field');
    var val = filterSelects[i].value;
    if (val !== 'all') filters[field] = val;
  }

  renderD3Heatmap(catId, cat, data.gpus, filters);
}
