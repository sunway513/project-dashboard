/**
 * Op Performance view — renders AMD MI355X vs NVIDIA B300 operator benchmark
 * heatmaps with interactive filters.
 * Called from dashboard.js after data is loaded.
 */

function renderOpPerf(data) {
  var el = document.getElementById("op-perf-view");
  if (!data || !data.categories) {
    el.innerHTML = '<h2>Operator Performance</h2><p class="empty">No performance data available.</p>';
    return;
  }

  var html = '<h2>Operator Performance &mdash; MI355X vs B300</h2>';
  html += '<p class="op-perf-subtitle">TFLOPS comparison across model shapes. ';
  html += '<span class="op-badge-amd">AMD MI355X (AITER)</span> vs ';
  html += '<span class="op-badge-nv">NVIDIA B300 (cuBLAS/SDPA)</span></p>';

  // Summary boxes
  var s = data.summary || {};
  html += '<div class="oc-summary">';
  html += summaryBox(s.total_configs || 0, "Total Configs");
  html += summaryBox(s.gemm_configs || 0, "GEMM");
  html += summaryBox(s.attention_configs || 0, "Attention");
  html += summaryBox(s.moe_configs || 0, "Fused MoE");
  html += '</div>';

  // Compute per-category stats
  for (var c = 0; c < data.categories.length; c++) {
    var cat = data.categories[c];
    var stats = computeCatStats(cat.results);
    html += buildPerfCategory(cat, stats, data.gpus);
  }

  // Notes
  html += '<div class="op-perf-notes">';
  html += '<h3>Notes</h3><ul>';
  html += '<li><strong>GEMM</strong>: AMD uses AITER Triton kernels; NVIDIA uses cuBLAS via torch.matmul / _scaled_mm</li>';
  html += '<li><strong>Attention</strong>: AMD uses AITER Triton FlashAttention; NVIDIA uses PyTorch SDPA (FlashAttention backend). FA3 for Blackwell not yet available.</li>';
  html += '<li><strong>MoE</strong>: AMD uses AITER fused_moe Triton kernel; NVIDIA uses naive batched matmul (no fused kernel available for Blackwell yet). Comparison is <em>not fair</em> for NV.</li>';
  html += '<li>Color scale: <span class="hm-cell hm-amd-win" style="display:inline-block;width:60px;text-align:center">AMD</span> ';
  html += '<span class="hm-cell hm-tie" style="display:inline-block;width:60px;text-align:center">Tie</span> ';
  html += '<span class="hm-cell hm-nv-win" style="display:inline-block;width:60px;text-align:center">NV</span></li>';
  html += '</ul></div>';

  if (data.lastUpdated) {
    html += '<div class="oc-updated">Data collected: ' + escapeHtml(data.lastUpdated) + '</div>';
  }

  el.innerHTML = html;

  // Attach filter event listeners
  attachPerfFilters(data);
}

function summaryBox(num, label) {
  return '<div class="oc-summary-box"><div class="oc-summary-num">' + num + '</div><div class="oc-summary-label">' + label + '</div></div>';
}

function computeCatStats(results) {
  var matched = 0, amdWins = 0, nvWins = 0, ratios = [];
  for (var i = 0; i < results.length; i++) {
    var r = results[i];
    if (r.amd_tflops > 0 && r.nv_tflops > 0) {
      matched++;
      var ratio = r.amd_tflops / r.nv_tflops;
      ratios.push(ratio);
      if (ratio > 1.05) amdWins++;
      else if (ratio < 0.95) nvWins++;
    }
  }
  var avg = ratios.length > 0 ? ratios.reduce(function(a,b){return a+b;}, 0) / ratios.length : 0;
  return { matched: matched, amdWins: amdWins, nvWins: nvWins, avg: avg, ratios: ratios };
}

function buildPerfCategory(cat, stats, gpus) {
  var html = '<details class="oc-category" id="perf-cat-' + cat.id + '">';

  // Summary line
  html += '<summary>';
  html += '<span class="oc-cat-name">' + escapeHtml(cat.name) + '</span>';
  html += '<span class="oc-cat-count">' + cat.results.length + ' configs</span>';
  html += '<span class="oc-cat-badges">';
  if (stats.matched > 0) {
    html += '<span class="oc-badge-amd">AMD wins: ' + stats.amdWins + '</span>';
    html += '<span class="oc-badge-nv">NV wins: ' + stats.nvWins + '</span>';
    html += '<span class="op-badge-ratio">Avg: ' + stats.avg.toFixed(2) + 'x</span>';
  }
  html += '</span>';
  html += '</summary>';

  // Filters
  html += '<div class="op-perf-filters" data-cat="' + cat.id + '">';
  html += buildFilterDropdown(cat, 'model', 'Model');
  html += buildFilterDropdown(cat, 'op', 'Op Type');
  html += buildFilterDropdown(cat, 'tp', 'TP');
  html += '<label class="op-perf-metric-toggle">';
  html += '<span>Metric:</span>';
  html += '<select class="op-perf-metric" data-cat="' + cat.id + '">';
  html += '<option value="tflops" selected>TFLOPS</option>';
  html += '<option value="time">Time (ms)</option>';
  html += '<option value="ratio">AMD/NV Ratio</option>';
  html += '</select>';
  html += '</label>';
  html += '</div>';

  // Heatmap container
  html += '<div class="op-perf-heatmap" id="heatmap-' + cat.id + '">';
  html += buildHeatmap(cat, gpus);
  html += '</div>';

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
  var html = '<label class="op-perf-filter">';
  html += '<span>' + label + ':</span>';
  html += '<select class="op-filter-select" data-cat="' + cat.id + '" data-field="' + field + '">';
  html += '<option value="all">All</option>';
  for (var i = 0; i < sorted.length; i++) {
    html += '<option value="' + escapeHtml(sorted[i]) + '">' + escapeHtml(sorted[i]) + '</option>';
  }
  html += '</select>';
  html += '</label>';
  return html;
}

function buildHeatmap(cat, gpus, filters, metric) {
  filters = filters || {};
  metric = metric || "tflops";

  // Filter results
  var results = [];
  for (var i = 0; i < cat.results.length; i++) {
    var r = cat.results[i];
    var ok = true;
    for (var f in filters) {
      if (filters[f] !== "all" && String(r[f]) !== String(filters[f])) { ok = false; break; }
    }
    if (ok) results.push(r);
  }

  if (results.length === 0) {
    return '<p class="empty">No results match the current filters.</p>';
  }

  // Build grouped heatmap tables per model+op
  var groups = {};
  for (var i = 0; i < results.length; i++) {
    var r = results[i];
    var gkey;
    if (cat.id === "gemm") {
      gkey = r.model + " | " + r.op + " | " + r.label + " (TP=" + r.tp + ")";
    } else if (cat.id === "attention") {
      gkey = r.model + " | " + r.mode + " (TP=" + r.tp + ", HQ=" + r.hq + ", HK=" + r.hk + ")";
    } else if (cat.id === "moe") {
      gkey = r.model + " | " + r.label + " (TP=" + r.tp + ", E=" + r.E + ", top_k=" + r.top_k + ")";
    } else {
      gkey = r.model || "unknown";
    }
    if (!groups[gkey]) groups[gkey] = [];
    groups[gkey].push(r);
  }

  var html = '';
  var groupKeys = Object.keys(groups).sort();

  for (var g = 0; g < groupKeys.length; g++) {
    var gk = groupKeys[g];
    var rows = groups[gk];
    html += '<div class="hm-group">';
    html += '<div class="hm-group-title">' + escapeHtml(gk) + '</div>';
    html += '<table class="hm-table">';

    // Header
    html += '<tr><th class="hm-th-shape">M</th>';
    if (cat.id === "attention") {
      html += '<th class="hm-th-shape">Seq</th>';
    }
    if (cat.id === "gemm" || cat.id === "moe") {
      html += '<th class="hm-th-shape">N</th><th class="hm-th-shape">K</th>';
    }
    html += '<th class="hm-th-gpu op-badge-amd-bg">' + (gpus.amd || 'AMD') + '</th>';
    html += '<th class="hm-th-gpu op-badge-nv-bg">' + (gpus.nvidia || 'NV') + '</th>';
    html += '<th class="hm-th-ratio">Ratio</th>';
    html += '</tr>';

    // Sort rows by M (or batch for attention)
    rows.sort(function(a, b) {
      var ma = a.M || a.batch || 0, mb = b.M || b.batch || 0;
      if (ma !== mb) return ma - mb;
      var sa = a.seq_q || a.N || 0, sb = b.seq_q || b.N || 0;
      return sa - sb;
    });

    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var amdVal, nvVal, ratioVal;

      if (metric === "tflops") {
        amdVal = r.amd_tflops;
        nvVal = r.nv_tflops;
      } else if (metric === "time") {
        amdVal = r.amd_ms;
        nvVal = r.nv_ms;
      } else {
        amdVal = r.amd_tflops;
        nvVal = r.nv_tflops;
      }

      var ratio = (amdVal > 0 && nvVal > 0) ? amdVal / nvVal : null;
      if (metric === "time" && ratio !== null) {
        // For time, lower is better, so invert: NV_ms/AMD_ms shows AMD speedup
        ratio = nvVal / amdVal;
      }
      var ratioClass = getRatioClass(ratio, metric);

      html += '<tr>';
      if (cat.id === "attention") {
        html += '<td class="hm-td-shape">' + (r.batch || r.M || '') + '</td>';
        html += '<td class="hm-td-shape">' + formatSeqLen(r.seq_q, r.seq_k) + '</td>';
      } else {
        html += '<td class="hm-td-shape">' + (r.M || '') + '</td>';
        html += '<td class="hm-td-shape">' + (r.N || '') + '</td>';
        html += '<td class="hm-td-shape">' + (r.K || '') + '</td>';
      }

      if (metric === "ratio") {
        html += '<td class="hm-cell ' + ratioClass + '" colspan="2" style="text-align:center">';
        html += ratio !== null ? ratio.toFixed(2) + 'x' : 'N/A';
        html += '</td>';
        html += '<td class="hm-cell ' + ratioClass + '">';
        html += ratio !== null ? (ratio > 1.05 ? 'AMD' : ratio < 0.95 ? 'NV' : 'Tie') : '';
        html += '</td>';
      } else {
        html += '<td class="hm-cell ' + ratioClass + '">' + formatVal(amdVal, metric) + '</td>';
        html += '<td class="hm-cell ' + ratioClass + '">' + formatVal(nvVal, metric) + '</td>';
        html += '<td class="hm-cell ' + ratioClass + '">';
        html += ratio !== null ? ratio.toFixed(2) + 'x' : 'N/A';
        html += '</td>';
      }
      html += '</tr>';
    }

    html += '</table>';
    html += '</div>';
  }

  return html;
}

function formatSeqLen(sq, sk) {
  if (sq === sk || !sk) {
    return formatNum(sq);
  }
  return formatNum(sq) + '/' + formatNum(sk);
}

function formatNum(n) {
  if (n >= 1000) return (n / 1000).toFixed(n % 1000 === 0 ? 0 : 1) + 'K';
  return String(n);
}

function formatVal(val, metric) {
  if (val === 0 || val === null || val === undefined) return '<span class="oc-no">&mdash;</span>';
  if (metric === "time") return val.toFixed(3);
  return val.toFixed(1);
}

function getRatioClass(ratio, metric) {
  if (ratio === null) return '';
  // ratio > 1 means AMD is better (for tflops and ratio modes)
  if (ratio > 1.5) return 'hm-amd-win';
  if (ratio > 1.05) return 'hm-amd-slight';
  if (ratio < 0.67) return 'hm-nv-win';
  if (ratio < 0.95) return 'hm-nv-slight';
  return 'hm-tie';
}

function attachPerfFilters(data) {
  var selects = document.querySelectorAll('.op-filter-select, .op-perf-metric');
  for (var i = 0; i < selects.length; i++) {
    selects[i].addEventListener('change', function () {
      var catId = this.getAttribute('data-cat');
      updateHeatmap(catId, data);
    });
  }
}

function updateHeatmap(catId, data) {
  var cat = null;
  for (var i = 0; i < data.categories.length; i++) {
    if (data.categories[i].id === catId) { cat = data.categories[i]; break; }
  }
  if (!cat) return;

  // Gather current filter values
  var filters = {};
  var filterSelects = document.querySelectorAll('.op-filter-select[data-cat="' + catId + '"]');
  for (var i = 0; i < filterSelects.length; i++) {
    var field = filterSelects[i].getAttribute('data-field');
    var val = filterSelects[i].value;
    if (val !== 'all') filters[field] = val;
  }

  var metricEl = document.querySelector('.op-perf-metric[data-cat="' + catId + '"]');
  var metric = metricEl ? metricEl.value : 'tflops';

  var container = document.getElementById('heatmap-' + catId);
  if (container) {
    container.innerHTML = buildHeatmap(cat, data.gpus, filters, metric);
  }
}

// Store data globally for filter callbacks
window._opPerfData = null;
