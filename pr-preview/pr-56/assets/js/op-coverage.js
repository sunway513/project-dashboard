/**
 * Op Coverage view — renders AMD vs NV operator comparison tables.
 * Called from dashboard.js after data is loaded.
 */

function renderOpCoverage(data) {
  var el = document.getElementById("op-coverage-view");
  if (!data || !data.categories) {
    el.innerHTML = '<h2>AI Operator Coverage</h2><p class="empty">No op coverage data available.</p>';
    return;
  }

  var cats = data.categories;
  var totalOps = 0;
  var totalAmd = 0;
  var totalNv = 0;

  for (var i = 0; i < cats.length; i++) {
    var ops = cats[i].operators;
    var amdProjects = cats[i].amd_projects;
    var nvProjects = cats[i].nv_projects;
    totalOps += ops.length;
    for (var j = 0; j < ops.length; j++) {
      var cov = ops[j].coverage;
      var hasAmd = amdProjects.some(function (p) { return covSupported(cov[p]); });
      var hasNv = nvProjects.some(function (p) { return covSupported(cov[p]); });
      if (hasAmd) totalAmd++;
      if (hasNv) totalNv++;
    }
  }

  var html = '<h2>AI Operator Coverage &mdash; AMD vs NV Ecosystem</h2>';

  // Summary boxes
  html += '<div class="oc-summary">';
  html += '<div class="oc-summary-box"><div class="oc-summary-num">' + totalOps + '</div><div class="oc-summary-label">Total Operators</div></div>';
  html += '<div class="oc-summary-box"><div class="oc-summary-num">' + totalAmd + '</div><div class="oc-summary-label">AMD Covered</div></div>';
  html += '<div class="oc-summary-box"><div class="oc-summary-num">' + totalNv + '</div><div class="oc-summary-label">NV Covered</div></div>';
  html += '<div class="oc-summary-box"><div class="oc-summary-num">' + cats.length + '</div><div class="oc-summary-label">Categories</div></div>';
  html += '</div>';

  // Accordion categories
  html += '<div class="oc-categories">';
  for (var i = 0; i < cats.length; i++) {
    html += buildOcCategory(cats[i]);
  }
  html += '</div>';

  if (data.lastUpdated) {
    html += '<div class="oc-updated">Data last updated: ' + escapeHtml(data.lastUpdated) + '</div>';
  }

  el.innerHTML = html;
}

function buildOcCategory(cat) {
  var ops = cat.operators;
  var amdProjects = cat.amd_projects;
  var nvProjects = cat.nv_projects;

  var amdCount = 0;
  var nvCount = 0;
  for (var i = 0; i < ops.length; i++) {
    var cov = ops[i].coverage;
    if (amdProjects.some(function (p) { return covSupported(cov[p]); })) amdCount++;
    if (nvProjects.some(function (p) { return covSupported(cov[p]); })) nvCount++;
  }

  var html = '<details class="oc-category">';

  // Summary line
  html += '<summary>';
  html += '<span class="oc-cat-name">' + escapeHtml(cat.name) + '</span>';
  html += '<span class="oc-cat-count">' + ops.length + ' ops</span>';
  html += '<span class="oc-cat-badges">';
  html += '<span class="oc-badge-amd">AMD: ' + amdCount + '/' + ops.length + '</span>';
  html += '<span class="oc-badge-nv">NV: ' + nvCount + '/' + ops.length + '</span>';
  html += '</span>';
  html += '</summary>';

  // Table
  html += '<div class="oc-table-wrap">';
  html += '<table class="oc-table">';

  // Header row
  html += '<tr>';
  html += '<th>Operator</th>';
  html += '<th>Backend</th>';
  for (var a = 0; a < amdProjects.length; a++) {
    html += '<th>' + escapeHtml(amdProjects[a]) + '</th>';
  }
  for (var n = 0; n < nvProjects.length; n++) {
    html += '<th class="' + (n === 0 ? 'oc-th-sep' : '') + '">' + escapeHtml(nvProjects[n]) + '</th>';
  }
  html += '</tr>';

  // Data rows
  for (var i = 0; i < ops.length; i++) {
    var op = ops[i];
    html += '<tr>';
    html += '<td>' + escapeHtml(op.name) + '</td>';
    html += '<td>' + backendBadges(op.backend, op.backend_urls) + '</td>';
    for (var a = 0; a < amdProjects.length; a++) {
      html += '<td>' + coverageIcon(op.coverage[amdProjects[a]]) + '</td>';
    }
    for (var n = 0; n < nvProjects.length; n++) {
      html += '<td class="' + (n === 0 ? 'oc-td-sep' : '') + '">' + coverageIcon(op.coverage[nvProjects[n]]) + '</td>';
    }
    html += '</tr>';
  }

  html += '</table>';
  html += '</div>';
  html += '</details>';
  return html;
}

// val can be: true, false, "partial", or { supported: true/false/"partial", url: "..." }
function covSupported(val) {
  if (val === true) return true;
  if (val && typeof val === "object") return val.supported === true;
  return false;
}

function coverageIcon(val) {
  if (val && typeof val === "object") {
    var icon = coverageIconSimple(val.supported);
    if (val.url && val.supported) {
      return '<a href="' + val.url + '" target="_blank" class="oc-link">' + icon + '</a>';
    }
    return icon;
  }
  return coverageIconSimple(val);
}

function coverageIconSimple(val) {
  if (val === true) return '<span class="oc-yes">&#10003;</span>';
  if (val === "partial") return '<span class="oc-partial">&#9881;</span>';
  return '<span class="oc-no">&mdash;</span>';
}

function backendBadges(val, urls) {
  if (!val) return '<span class="oc-no">&mdash;</span>';
  var parts = val.split(/\s*[\/+]\s*/);
  var html = '';
  for (var i = 0; i < parts.length; i++) {
    var p = parts[i].trim();
    var cls = 'oc-be-other';
    var label = p;
    if (p === 'Triton') cls = 'oc-be-triton';
    else if (p === 'CK') cls = 'oc-be-ck';
    else if (p === 'ASM') cls = 'oc-be-asm';
    else if (p.indexOf('ASM') >= 0 && p.indexOf('Triton') >= 0) { cls = 'oc-be-asm'; label = 'ASM+Triton'; }
    else if (p === 'HIP') cls = 'oc-be-hip';
    else if (p === 'FlyDSL') cls = 'oc-be-flydsl';
    else if (p === 'PyTorch') cls = 'oc-be-hip';
    var altCls = i === 0 ? '' : ' oc-be-alt';
    var badge = '<span class="oc-be' + altCls + ' ' + cls + '">' + escapeHtml(label) + '</span>';
    if (urls && urls[p]) {
      html += '<a href="' + urls[p] + '" target="_blank" class="oc-be-link">' + badge + '</a>';
    } else {
      html += badge;
    }
  }
  return html;
}
