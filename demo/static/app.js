/**
 * DESIGNDOCTOR AI 2.0 — FRONTEND CLIENT ARCHITECTURE
 * Precision Website Experience & UI/UX Telemetry
 * Built with the AWS User Group Madurai Strands Decider hackathon kit
 */

(() => {
  'use strict';

  // ── Element Selectors ────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const $$ = (sel) => document.querySelectorAll(sel);

  // Core DOM references
  const urlField = $('url-field');
  const auditBtn = $('audit-btn');
  const auditProgressBar = $('audit-progress');
  const chatScroll = $('chat-scroll');
  const chatInput = $('m') || $('msg');
  const sendBtn = $('send');
  const themeToggleBtn = $('theme-toggle-btn');
  const reportBtn = $('report-btn');
  const copyMdBtn = $('copy-md-btn');
  const resetBtn = $('reset-btn');
  const overallScoreVal = $('overall-score-val');
  const gaugeFill = $('gauge-fill');
  const healthStatusBadge = $('health-status-badge');
  const healthHeadline = $('health-headline');
  const healthCaveat = $('health-caveat');
  const healthCard = $('health-card');
  const coverageNotice = $('coverage-notice');
  const issuesListEl = $('issues-list');
  const issuesCountLabel = $('issues-count-label');
  const honestyPerformedList = $('honesty-performed-list');
  const honestyUnverifiedList = $('honesty-unverified-list');
  const deciderProbBars = $('decider-prob-bars');
  const deciderStatusPill = $('decider-status-pill');
  const deciderTargetTitle = $('decider-target-title');
  const deciderLatencyVal = $('decider-latency-val');
  const deciderHistoryList = $('decider-history-list');
  const deciderExplanation = $('decider-explanation');

  // Application State
  const state = {
    currentUrl: 'https://example.com',
    theme: localStorage.getItem('theme') || 'dark',
    turnsCount: 0,
    isAuditing: false,
    isChatting: false,
    currentPillarFilter: 'all',
    currentSeverityFilter: 'all',
    activeMobileView: 'overview',
    auditData: null,
    allIssues: [],
    decisionsHistory: [],
    chatHistory: [],
  };

  // ── URL Normalization & Validation ───────────────────────────────────────
  /**
   * Strips repeated or nested schemes (e.g. "https://https://w3.org" -> "https://w3.org")
   * and enforces lowercase http/https scheme with clean trimming.
   */
  function sanitizeAndNormalizeUrl(raw) {
    if (!raw) return '';
    let s = String(raw).trim();

    // Strip whitespace inside protocol prefix
    s = s.replace(/^(https?:\/\/)\s+/i, '$1');

    // Repeated nested schemes loop (e.g., https://https://, http://https://)
    while (/^(https?:\/\/)+(https?:\/\/)/i.test(s)) {
      s = s.replace(/^(https?:\/\/)+/i, '');
    }

    // Single scheme extraction
    const match = s.match(/^(https?:\/\/)(.*)$/i);
    if (match) {
      const scheme = match[1].toLowerCase();
      let rest = match[2].trim();
      // Clean leading slashes
      rest = rest.replace(/^\/+/g, '');
      // Strip any inner redundant scheme
      rest = rest.replace(/^(https?:\/\/)+/i, '');
      s = scheme + rest;
    } else {
      // Missing scheme: default to public https://
      s = 'https://' + s.replace(/^\/+/g, '');
    }

    return s;
  }

  function isValidTargetUrl(urlStr) {
    try {
      const u = new URL(urlStr);
      if (u.protocol !== 'http:' && u.protocol !== 'https:') return false;
      const host = u.hostname.toLowerCase();
      if (!host || host.length < 3) return false;
      // Disallow local loopback, link-local, and obvious RFC-1918 private ranges for public audits
      if (host === 'localhost' || host === '127.0.0.1' || host === '0.0.0.0' || host === '::1') {
        return false;
      }
      if (host.startsWith('192.168.') || host.startsWith('10.') || host.endsWith('.local') || host.endsWith('.internal')) {
        return false;
      }
      return host.includes('.');
    } catch {
      return false;
    }
  }

  // ── Theme Management ─────────────────────────────────────────────────────
  function applyTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    if (themeToggleBtn) {
      themeToggleBtn.innerHTML = theme === 'dark' 
        ? '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
        : '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
      themeToggleBtn.title = `Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`;
    }
    // Update gauge stroke color according to current score and theme
    if (state.auditData) {
      updateGauge(
        state.auditData.overall_score,
        state.auditData.is_partial,
        state.auditData.coverage_label,
        state.auditData.coverage_warning,
        state.auditData.tested_categories_count,
        state.auditData.total_categories_count
      );
    }
  }

  themeToggleBtn?.addEventListener('click', () => {
    applyTheme(state.theme === 'dark' ? 'light' : 'dark');
  });
  applyTheme(state.theme);

  // ── Header System Telemetry (Honest Provider Status) ──────────────────────
  async function loadSystemInfo() {
    try {
      const res = await fetch('/api/info');
      if (!res.ok) return;
      const data = await res.json();

      // 1. LLM Status Pill (Never claim Bedrock without verified AWS authentication)
      const llmPill = $('llm-pill');
      if (llmPill) {
        const llm = data.llm_details || {};
        if (llm.status === 'connected') {
          llmPill.className = 'telemetry-pill pill-live';
          llmPill.textContent = 'Bedrock: Connected';
          llmPill.title = `Amazon Bedrock (${llm.model_id || 'Nova Pro'}) authenticated and active.`;
        } else if (llm.status === 'unconfigured') {
          llmPill.className = 'telemetry-pill pill-offline';
          llmPill.textContent = 'LLM: Rule Engine';
          llmPill.title = llm.message || 'AWS credentials not configured. Static website auditing operates 100% locally with zero cloud API dependencies.';
        } else {
          llmPill.className = 'telemetry-pill pill-warning';
          llmPill.textContent = 'LLM: Offline';
          llmPill.title = llm.message || 'Bedrock connection unavailable. Static engine active.';
        }
      }

      // 2. Strands Decider 2B Status Pill
      const decPill = $('dec-pill');
      if (decPill) {
        const dec = data.decider_details || {};
        if (dec.status === 'connected') {
          decPill.className = 'telemetry-pill pill-live';
          decPill.textContent = 'Decider: Hosted 2B';
          decPill.title = `Strands Decider 2B connected (${dec.endpoint || 'UGMdu hosted'}). Real-time neural tool routing active.`;
        } else if (dec.status === 'unconfigured') {
          decPill.className = 'telemetry-pill pill-warning';
          decPill.textContent = 'Decider: Heuristic';
          decPill.title = dec.message || 'Hosted endpoint live. Set DECIDER_API_KEY in .env for neural model routing.';
        } else {
          decPill.className = 'telemetry-pill pill-warning';
          decPill.textContent = 'Decider: Offline';
          decPill.title = dec.message || 'Decider endpoint offline. Rule-based heuristic fallback active.';
        }
      }

      // 3. Auditor Engine Status Pill
      const auditorPill = $('auditor-pill') || $('tgt-pill');
      if (auditorPill) {
        auditorPill.className = 'telemetry-pill pill-live';
        auditorPill.textContent = 'Auditor: Static';
        auditorPill.title = 'Deterministic DOM & static analysis engine (100% local, no AI tokens consumed).';
      }
    } catch {
      // Offline / default state handled by markup
    }
  }
  loadSystemInfo();

  // ── Mobile Segmented Control ─────────────────────────────────────────────
  $$('.segment-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.view;
      setMobileView(view);
    });
  });

  function setMobileView(view) {
    state.activeMobileView = view;
    $$('.segment-btn').forEach((b) => b.classList.toggle('active', b.dataset.view === view));
    
    // Toggle mobile panels
    const leftPanel = $('panel-left');
    const rightPanel = $('panel-right');
    const overviewSection = $('overview-section');
    const findingsSection = $('findings-section');

    if (view === 'overview') {
      leftPanel?.classList.add('mobile-active');
      rightPanel?.classList.remove('mobile-active');
      if (overviewSection) overviewSection.style.display = 'flex';
      if (findingsSection) findingsSection.style.display = 'none';
    } else if (view === 'findings') {
      leftPanel?.classList.add('mobile-active');
      rightPanel?.classList.remove('mobile-active');
      if (overviewSection) overviewSection.style.display = 'none';
      if (findingsSection) findingsSection.style.display = 'flex';
    } else if (view === 'decider' || view === 'copilot') {
      leftPanel?.classList.remove('mobile-active');
      rightPanel?.classList.add('mobile-active');
      const deciderSec = $('decider-section');
      const copilotSec = $('copilot-section');
      if (deciderSec) deciderSec.style.display = view === 'decider' ? 'flex' : 'none';
      if (copilotSec) copilotSec.style.display = view === 'copilot' ? 'flex' : 'none';
    }
  }

  // ── HTML Escape & Markdown Formatting ────────────────────────────────────
  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function renderMarkdown(src) {
    if (!src) return '';

    // Replace fenced code blocks with rich wrapper and copy action
    src = src.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const cleanLang = lang ? lang.toLowerCase() : 'code';
      const cleanCode = code.trimEnd();
      const encodedCode = esc(cleanCode);
      return `\n\n###CODEBLOCK###<div class="code-block-wrapper">` +
        `<div class="code-block-header">` +
          `<span>${esc(cleanLang)}</span>` +
          `<button class="copy-code-btn" type="button" data-clipboard="${encodedCode}" aria-label="Copy code">` +
            `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>` +
            `<span>Copy</span>` +
          `</button>` +
        `</div>` +
        `<pre><code>${esc(cleanCode)}</code></pre>` +
      `</div>###ENDCODEBLOCK###\n\n`;
    });

    const lines = src.split('\n');
    let html = '', inList = null, listBuf = '';

    function flushList() {
      if (inList) {
        html += `<${inList}>${listBuf}</${inList}>`;
        inList = null;
        listBuf = '';
      }
    }

    function inlineFormat(s) {
      s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
      s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
      s = s.replace(/\[CRITICAL\]/gi, '<span class="sev-badge sev-critical">[CRITICAL]</span>');
      s = s.replace(/\[WARNING\]/gi, '<span class="sev-badge sev-warning">[WARNING]</span>');
      s = s.replace(/\[INFO\]/gi, '<span class="sev-badge sev-info">[INFO]</span>');
      s = s.replace(/\[PASS\]/gi, '<span class="sev-badge" style="background: var(--metric-pass-subtle); color: var(--metric-pass); border-color: var(--metric-pass);">[PASS]</span>');
      s = s.replace(/\b(\d{1,3})\/100\b/g, (_, n) => {
        const v = parseInt(n, 10);
        const cls = v >= 75 ? 'score-good' : v >= 50 ? 'score-warn' : 'score-crit';
        return `<span class="pillar-score-badge ${cls}">${n}/100</span>`;
      });
      return s;
    }

    for (let raw of lines) {
      raw = raw.trimEnd();

      if (raw.includes('###CODEBLOCK###')) {
        flushList();
        const blockHtml = raw.replace(/###CODEBLOCK###/g, '').replace(/###ENDCODEBLOCK###/g, '');
        html += blockHtml;
        continue;
      }
      if (/^### /.test(raw)) {
        flushList();
        html += `<h3>${inlineFormat(esc(raw.slice(4)))}</h3>`;
        continue;
      }
      if (/^## /.test(raw)) {
        flushList();
        html += `<h2>${inlineFormat(esc(raw.slice(3)))}</h2>`;
        continue;
      }
      if (/^# /.test(raw)) {
        flushList();
        html += `<h1>${inlineFormat(esc(raw.slice(2)))}</h1>`;
        continue;
      }
      if (/^---+$/.test(raw.trim())) {
        flushList();
        html += '<hr>';
        continue;
      }
      if (/^> /.test(raw)) {
        flushList();
        html += `<blockquote>${inlineFormat(esc(raw.slice(2)))}</blockquote>`;
        continue;
      }
      if (/^[-*] /.test(raw)) {
        if (inList !== 'ul') { flushList(); inList = 'ul'; }
        listBuf += `<li>${inlineFormat(esc(raw.slice(2)))}</li>`;
        continue;
      }
      if (/^\d+\. /.test(raw)) {
        if (inList !== 'ol') { flushList(); inList = 'ol'; }
        listBuf += `<li>${inlineFormat(esc(raw.replace(/^\d+\. /, '')))}</li>`;
        continue;
      }
      if (!raw.trim()) {
        flushList();
        continue;
      }
      flushList();
      html += `<p>${inlineFormat(esc(raw))}</p>`;
    }
    flushList();
    return html;
  }

  // ── SVG Gauge & Scores (Honest Aggregation Engine) ────────────────────────
  function updateGauge(score, isPartial = false, coverageLabel = '', coverageWarning = '', testedCount = 4, totalCount = 4) {
    if (!gaugeFill || !overallScoreVal) return;

    // Circumference = 2 * PI * r = 2 * 3.14159 * 45 = ~282.74
    const circumference = 282.74;

    if (score == null || isNaN(score)) {
      overallScoreVal.textContent = '—';
      gaugeFill.style.strokeDashoffset = circumference;
      gaugeFill.style.stroke = 'var(--text-tertiary)';
      if (healthStatusBadge) {
        healthStatusBadge.className = 'health-status-badge status-pass';
        healthStatusBadge.textContent = 'AWAITING AUDIT';
      }
      if (healthHeadline) healthHeadline.textContent = 'Enter a valid URL to run the diagnostic suite.';
      if (healthCard) healthCard.classList.remove('partial-audit');
      if (coverageNotice) coverageNotice.style.display = 'none';
      return;
    }

    const numericScore = Math.round(score);
    overallScoreVal.textContent = String(numericScore);

    const offset = circumference - (numericScore / 100) * circumference;
    gaugeFill.style.strokeDashoffset = offset;

    let strokeColor = 'var(--metric-pass)';
    let statusText = 'EXCEPTIONAL';
    let statusCls = 'status-pass';
    let headline = 'Healthy website architecture and UX foundations.';

    if (numericScore < 50) {
      strokeColor = 'var(--metric-crit)';
      statusText = 'CRITICAL DEFICITS';
      statusCls = 'status-crit';
      headline = 'Severe UX barriers, accessibility failures, or structural defects detected.';
    } else if (numericScore < 80) {
      strokeColor = 'var(--metric-warn)';
      statusText = 'IMPROVEMENTS NEEDED';
      statusCls = 'status-warn';
      headline = 'Noticeable design debt, missing tags, or non-optimal responsive rules.';
    }

    if (isPartial) {
      statusText = `PARTIAL AUDIT (${testedCount}/${totalCount} TESTED)`;
      statusCls = 'status-warn';
      strokeColor = 'var(--metric-warn)';
      headline = coverageLabel || `Audited ${testedCount} of ${totalCount} categories. Aggregate score reflects measured categories only.`;
      if (healthCard) healthCard.classList.add('partial-audit');
      if (coverageNotice) {
        coverageNotice.style.display = 'block';
        coverageNotice.innerHTML = `
          <div class="coverage-notice-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
            Scope Coverage Notice: ${esc(coverageLabel || 'Partial Audit')}
          </div>
          <div class="coverage-notice-text">
            ${esc(coverageWarning || 'Only selected categories were measured. Unmeasured categories are excluded from the aggregate score to prevent misleading 0% or 100% ratings.')}
          </div>`;
      }
    } else {
      if (healthCard) healthCard.classList.remove('partial-audit');
      if (coverageNotice) {
        coverageNotice.style.display = 'none';
        coverageNotice.innerHTML = '';
      }
    }

    gaugeFill.style.stroke = strokeColor;
    if (healthStatusBadge) {
      healthStatusBadge.className = `health-status-badge ${statusCls}`;
      healthStatusBadge.textContent = statusText;
    }
    if (healthHeadline) healthHeadline.textContent = headline;
  }

  // ── Render 4-Pillar Score Cards (4-State Display Engine) ──────────────────
  function renderPillars(results) {
    const pillars = [
      { key: 'accessibility', title: 'Accessibility', elScore: 'score-a11y', elBar: 'bar-a11y', elMeta: 'meta-a11y', defaultMeta: 'ARIA labels, contrast, alt text' },
      { key: 'typography', title: 'Typography', elScore: 'score-type', elBar: 'bar-type', elMeta: 'meta-type', defaultMeta: 'Heading hierarchy, line-height, density' },
      { key: 'layout', title: 'Layout & Mobile', elScore: 'score-layout', elBar: 'bar-layout', elMeta: 'meta-layout', defaultMeta: 'Viewport meta, overflow, fixed widths' },
      { key: 'performance', title: 'Performance Hints', elScore: 'score-perf', elBar: 'bar-perf', elMeta: 'meta-perf', defaultMeta: 'Render blocking, lazy loading, weight' },
    ];

    pillars.forEach(({ key, elScore, elBar, elMeta }) => {
      const data = results[key] || { state: 'not_tested' };
      const pillarState = data.state || (typeof data.score === 'number' ? 'tested' : 'not_tested');
      const score = typeof data.score === 'number' ? data.score : null;
      const issues = data.issues || [];
      const scoreEl = $(elScore);
      const barEl = $(elBar);
      const metaEl = $(elMeta);

      if (!scoreEl || !barEl || !metaEl) return;

      // 1. Tested and Scored
      if (pillarState === 'tested' && score !== null) {
        const cls = score >= 80 ? 'score-good' : score >= 50 ? 'score-warn' : 'score-crit';
        const barColor = score >= 80 ? 'var(--metric-pass)' : score >= 50 ? 'var(--metric-warn)' : 'var(--metric-crit)';
        scoreEl.className = `pillar-score-badge ${cls}`;
        scoreEl.textContent = `${score}/100`;
        barEl.style.width = `${score}%`;
        barEl.style.backgroundColor = barColor;
        metaEl.textContent = `${issues.length} issue${issues.length === 1 ? '' : 's'} · ${data.score_basis || 'Measured'}`;
      }
      // 2. Failed / Execution Error
      else if (pillarState === 'failed') {
        scoreEl.className = 'pillar-score-badge score-failed';
        scoreEl.textContent = 'Failed';
        barEl.style.width = '100%';
        barEl.style.backgroundColor = 'var(--metric-crit)';
        metaEl.textContent = `Check failed: ${data.error || 'Execution error'}`;
      }
      // 3. Partially Tested
      else if (pillarState === 'partially_tested') {
        const cls = score != null && score >= 75 ? 'score-good' : 'score-warn';
        scoreEl.className = `pillar-score-badge ${cls}`;
        scoreEl.textContent = score != null ? `${score}/100*` : 'Partial';
        barEl.style.width = `${score || 50}%`;
        barEl.style.backgroundColor = 'var(--metric-warn)';
        metaEl.textContent = `Partial measure: ${data.score_basis || 'Incomplete'}`;
      }
      // 4. Not Tested / Excluded
      else {
        scoreEl.className = 'pillar-score-badge score-untested';
        scoreEl.textContent = 'Not Tested';
        barEl.style.width = '0%';
        barEl.style.backgroundColor = 'transparent';
        metaEl.textContent = 'Excluded from audit scope';
      }
    });
  }

  // ── Render Telemetry Strip ───────────────────────────────────────────────
  function renderTelemetryMetrics(results) {
    const perf = results.performance?.evidence || {};
    const layout = results.layout?.evidence || {};

    if ($('val-size')) $('val-size').textContent = perf.html_size_kb ? `${perf.html_size_kb} KB` : '—';
    if ($('val-scripts')) $('val-scripts').textContent = perf.blocking_scripts != null ? String(perf.blocking_scripts) : '0';
    if ($('val-images')) $('val-images').textContent = perf.images_total != null ? `${perf.images_total} (${perf.lazy_images || 0} lazy)` : '—';
    if ($('val-viewport')) $('val-viewport').textContent = layout.viewport_content ? 'Active ✓' : (results.layout ? 'Missing ✗' : '—');
  }

  // ── Render Findings & Issue Explorer ─────────────────────────────────────
  function renderFindings(issues) {
    if (!issuesListEl) return;
    issuesListEl.innerHTML = '';

    // Apply active filters
    const filtered = issues.filter((iss) => {
      const matchesPillar = state.currentPillarFilter === 'all' || iss.pillar === state.currentPillarFilter;
      const matchesSeverity = state.currentSeverityFilter === 'all' || iss.severity === state.currentSeverityFilter;
      return matchesPillar && matchesSeverity;
    });

    if (issuesCountLabel) {
      issuesCountLabel.textContent = `Showing ${filtered.length} of ${issues.length} findings`;
    }

    if (filtered.length === 0) {
      issuesListEl.innerHTML = `
        <div style="padding: 24px; text-align: center; color: var(--text-tertiary); background: var(--bg-surface-0); border: 1px dashed var(--border-default); border-radius: var(--radius-md);">
          <div style="font-size: 20px; margin-bottom: 6px;">✓</div>
          <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary);">No issues found in this filter category</div>
          <div style="font-size: 11px; margin-top: 4px;">All static checks passed for the selected criteria.</div>
        </div>`;
      return;
    }

    filtered.forEach((iss) => {
      const card = document.createElement('div');
      card.className = 'issue-card';
      const sevCls = iss.severity === 'critical' ? 'sev-critical' : iss.severity === 'warning' ? 'sev-warning' : 'sev-info';
      const wcag = iss.wcag ? `<span class="issue-wcag-tag">${esc(iss.wcag)}</span>` : '';

      card.innerHTML = `
        <div class="issue-card-head">
          <span class="sev-badge ${sevCls}">${esc(iss.severity || 'info')}</span>
          <span class="issue-category-tag">${esc(iss.category || 'General UX')} · ${esc(iss.pillar || '')}</span>
          ${wcag}
        </div>
        <div class="issue-finding">${esc(iss.finding || '')}</div>
        <div class="issue-fix-box">
          <strong>Recommended Fix:</strong> ${esc(iss.fix || 'Review page structure.')}
        </div>`;
      issuesListEl.appendChild(card);
    });
  }

  // ── Render Honesty Accordion ─────────────────────────────────────────────
  function renderHonestyLists(results) {
    const performedSet = new Set();
    const notPerformedSet = new Set();

    Object.values(results).forEach((r) => {
      if (Array.isArray(r.checks_performed)) r.checks_performed.forEach((c) => performedSet.add(c));
      if (Array.isArray(r.checks_not_performed)) r.checks_not_performed.forEach((c) => notPerformedSet.add(c));
    });

    if (honestyPerformedList) {
      honestyPerformedList.innerHTML = Array.from(performedSet)
        .map((c) => `<li>${esc(c)}</li>`)
        .join('');
    }
    if (honestyUnverifiedList) {
      honestyUnverifiedList.innerHTML = Array.from(notPerformedSet)
        .map((c) => `<li>${esc(c)}</li>`)
        .join('');
    }
  }

  // ── Render Manual Audit Scope Selection ──────────────────────────────────
  function renderAuditRouting(routing, tool) {
    const selected = routing?.tool_selected || tool || 'all';
    const routingType = routing?.routing_type || (tool === 'all' ? 'full_audit' : 'manual_selection');
    const desc = routing?.description || (tool === 'all' ? 'Full Suite Audit (Running all 4 audit categories)' : `Manual Selection (User picked ${selected})`);

    if (deciderTargetTitle) {
      deciderTargetTitle.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon></svg> Scope: <code>${esc(selected)}</code>`;
    }

    if (deciderStatusPill) {
      deciderStatusPill.className = 'decider-status-pill manual';
      deciderStatusPill.textContent = routingType === 'full_audit' ? 'Full Suite Audit' : 'Manual Selection';
    }

    if (deciderExplanation) {
      deciderExplanation.style.display = 'block';
      deciderExplanation.innerHTML = `<strong>Audit Routing:</strong> ${esc(desc)}`;
    }

    if (deciderLatencyVal) {
      deciderLatencyVal.textContent = 'Mode: User Scope Selection';
    }

    if (deciderProbBars) {
      const tools = [
        { name: 'audit_accessibility', label: 'Accessibility', active: selected === 'all' || selected === 'audit_accessibility' },
        { name: 'audit_typography', label: 'Typography', active: selected === 'all' || selected === 'audit_typography' },
        { name: 'audit_layout', label: 'Layout & Responsiveness', active: selected === 'all' || selected === 'audit_layout' },
        { name: 'audit_performance_hints', label: 'Performance Hints', active: selected === 'all' || selected === 'audit_performance_hints' },
      ];
      deciderProbBars.innerHTML = tools.map((t) => {
        const pct = t.active ? 100 : 0;
        const color = t.active ? 'var(--metric-pass)' : 'var(--text-tertiary)';
        return `
          <div class="prob-entry">
            <span class="prob-tool-name ${t.active ? 'winner' : ''}" title="${esc(t.name)}">${esc(t.label)}</span>
            <div class="prob-meter-track">
              <div class="prob-meter-fill" style="width: ${pct}%; background: ${color}"></div>
            </div>
            <span class="prob-number-val">${t.active ? 'AUDITED' : 'EXCLUDED'}</span>
          </div>`;
      }).join('');
    }
  }

  // ── Strands Decider 2B Decision Panel (Copilot Routing) ──────────────────
  function renderDeciderState(dec) {
    if (!dec) return;
    const tool = dec.tool || 'none';
    const confidence = typeof dec.confidence === 'number' ? Math.round(dec.confidence * 100) : null;
    const latency = dec.decider_ms ? Math.round(dec.decider_ms) : null;
    const routingMode = dec.routing_mode || (dec.narrowed ? 'decider_model' : 'unsure');

    const routeLabel = $('decider-route-label');
    if (routeLabel) routeLabel.textContent = tool;

    if (deciderTargetTitle) {
      deciderTargetTitle.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon></svg> <span>Route: <code>${esc(tool)}</code></span>`;
    }

    if (deciderStatusPill) {
      if (routingMode === 'heuristic_fallback') {
        deciderStatusPill.className = 'decider-status-pill fallback';
        deciderStatusPill.textContent = 'Heuristic Fallback';
        if (deciderExplanation) {
          deciderExplanation.style.display = 'block';
          deciderExplanation.innerHTML = `<strong>Heuristic Fallback:</strong> ${esc(dec.reason || 'Rule-based router matched query keywords.')}`;
        }
      } else if (routingMode === 'manual_selection' || routingMode === 'full_audit') {
        deciderStatusPill.className = 'decider-status-pill manual';
        deciderStatusPill.textContent = routingMode === 'full_audit' ? 'Full Suite' : 'Manual Scope';
        if (deciderExplanation) {
          deciderExplanation.style.display = 'block';
          deciderExplanation.innerHTML = '<strong>Manual Selection:</strong> User directly invoked tool scope.';
        }
      } else if (routingMode === 'decider_model' || (dec.narrowed === true && tool !== 'none')) {
        deciderStatusPill.className = 'decider-status-pill model-routed';
        deciderStatusPill.textContent = confidence != null ? `✓ Neural (${confidence}%)` : '✓ Neural (High)';
        if (deciderExplanation) {
          deciderExplanation.style.display = 'block';
          deciderExplanation.innerHTML = `<strong>Strands Decider 2B:</strong> Real-time neural classifier routed query directly to <code>${esc(tool)}</code>.`;
        }
      } else if (tool === 'none') {
        deciderStatusPill.className = 'decider-status-pill no-tool';
        deciderStatusPill.textContent = 'No Tool Needed';
        if (deciderExplanation) {
          deciderExplanation.style.display = 'block';
          deciderExplanation.innerHTML = '<strong>Direct Response:</strong> General design question answered without tool execution.';
        }
      } else {
        deciderStatusPill.className = 'decider-status-pill unsure';
        deciderStatusPill.textContent = 'Broad Query';
        if (deciderExplanation) {
          deciderExplanation.style.display = 'block';
          deciderExplanation.innerHTML = '<strong>Broad Query:</strong> Decider retained full tool suite.';
        }
      }
    }

    if (deciderLatencyVal) {
      if (routingMode === 'heuristic_fallback') {
        deciderLatencyVal.textContent = latency ? `${latency}ms (heuristic)` : '<1ms (heuristic)';
      } else if (latency) {
        deciderLatencyVal.textContent = `${latency}ms`;
      }
    }

    // Probability Bars (Rule 8: Do not present heuristic scores as genuine AI model confidence)
    if (deciderProbBars) {
      if (routingMode === 'heuristic_fallback') {
        deciderProbBars.innerHTML = `
          <div style="padding: 10px 12px; font-size: 11.5px; color: var(--text-secondary); background: var(--bg-surface-1); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm);">
            <div style="font-weight: 600; color: var(--metric-warn); margin-bottom: 3px;">Rule-based Routing Active</div>
            <div>Query matched keyword heuristic for <code>${esc(tool)}</code>. Hosted neural classifier key not configured.</div>
          </div>`;
      } else {
        let probs = [];
        if (dec.probabilities && typeof dec.probabilities === 'object') {
          probs = Object.entries(dec.probabilities);
        } else {
          probs = Object.entries(dec).filter(([k, v]) => typeof v === 'number' && v >= 0 && v <= 1 && !k.endsWith('_ms'));
        }
        probs.sort((a, b) => b[1] - a[1]);

        if (probs.length > 0) {
          deciderProbBars.innerHTML = probs.map(([name, val]) => {
            const pct = (val * 100).toFixed(0);
            const isWinner = name === tool;
            const color = val >= 0.65 ? 'var(--metric-pass)' : val >= 0.35 ? 'var(--metric-warn)' : 'var(--text-tertiary)';
            return `
              <div class="prob-entry">
                <span class="prob-tool-name ${isWinner ? 'winner' : ''}" title="${esc(name)}">${esc(name)}</span>
                <div class="prob-meter-track">
                  <div class="prob-meter-fill" style="width: ${pct}%; background: ${color}"></div>
                </div>
                <span class="prob-number-val">${pct}%</span>
              </div>`;
          }).join('');
        } else {
          deciderProbBars.innerHTML = '';
        }
      }
    }

    // Prepend to Decider History without duplicates
    if (deciderHistoryList) {
      const historyCard = document.createElement('div');
      historyCard.className = 'history-card-mini';
      const badgeColor = routingMode === 'heuristic_fallback' ? 'color: var(--metric-warn);' : routingMode === 'decider_model' ? 'color: var(--metric-pass);' : '';
      historyCard.innerHTML = `
        <span style="font-family: var(--font-mono); font-weight: 600; ${badgeColor}">→ ${esc(tool)}</span>
        <span>${confidence != null ? confidence + '%' : (routingMode === 'heuristic_fallback' ? 'heuristic' : '')} · ${latency != null ? latency + 'ms' : '<1ms'}</span>`;
      deciderHistoryList.prepend(historyCard);
    }
  }

  // ── Run Website Audit (Real Data Engine) ─────────────────────────────────
  async function runAudit(targetUrl, tool = 'all') {
    if (state.isAuditing) return;
    const raw = (targetUrl || urlField?.value || '').trim();
    if (!raw) {
      alert('Please enter a website URL or domain name to audit.');
      return;
    }

    const normalized = sanitizeAndNormalizeUrl(raw);
    if (!isValidTargetUrl(normalized)) {
      alert(`Invalid Target URL: "${raw}".\n\nPlease enter a valid public website URL (e.g. "https://example.com" or "stripe.com"). Localhost and private IP addresses cannot be audited.`);
      return;
    }

    state.currentUrl = normalized;
    if (urlField) urlField.value = normalized;

    const urlBadge = $('active-url-badge');
    try {
      const parsedHost = new URL(normalized).hostname;
      if (urlBadge) urlBadge.textContent = `Target: ${parsedHost}`;
    } catch {}

    state.isAuditing = true;
    if (auditBtn) auditBtn.disabled = true;
    if (auditProgressBar) auditProgressBar.classList.add('active');

    try {
      const res = await fetch('/api/audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: normalized, tool }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Audit execution failed' }));
        alert(`Audit Error: ${err.error || 'Could not audit URL'}`);
        return;
      }

      const data = await res.json();
      state.auditData = data;
      state.allIssues = data.issues || [];

      // Update UI components with measured data
      updateGauge(
        data.overall_score,
        data.is_partial,
        data.coverage_label,
        data.coverage_warning,
        data.tested_categories_count,
        data.total_categories_count
      );
      renderPillars(data.results || {});
      renderTelemetryMetrics(data.results || {});
      renderFindings(state.allIssues);
      renderHonestyLists(data.results || {});
      renderAuditRouting(data.routing, tool);

      // Add a clean telemetry announcement in chat
      const scoreStr = data.overall_score != null ? `${data.overall_score}/100` : '—';
      const partialBadge = data.is_partial ? ' *(Partial Audit)*' : '';
      addBotMessage(
        `### Completed Audit for \`${esc(data.url_normalized || normalized)}\`\n` +
        `**Overall UX Health Score:** ${scoreStr}${partialBadge}\n` +
        (data.coverage_warning ? `> ⚠️ **Coverage Notice:** ${esc(data.coverage_warning)}\n\n` : '') +
        `- **Accessibility:** ${formatPillarChatScore(data.results?.accessibility)}\n` +
        `- **Typography:** ${formatPillarChatScore(data.results?.typography)}\n` +
        `- **Layout:** ${formatPillarChatScore(data.results?.layout)}\n` +
        `- **Performance Hints:** ${formatPillarChatScore(data.results?.performance)}\n\n` +
        `Identified **${data.total_issues || 0} issues** across measured static checks. Review findings on the left or ask me questions about specific remediations below.`,
        `DesignDoctor AI · ${data.is_partial ? 'partial audit' : 'full audit'}`
      );
    } catch (err) {
      alert(`Network Error: ${err.message}`);
    } finally {
      state.isAuditing = false;
      if (auditBtn) auditBtn.disabled = false;
      if (auditProgressBar) auditProgressBar.classList.remove('active');
    }
  }

  function formatPillarChatScore(res) {
    if (!res) return 'Not Tested';
    if (res.state === 'not_tested') return 'Not Tested (Excluded)';
    if (res.state === 'failed') return 'Failed ✗';
    if (typeof res.score === 'number') return `${res.score}/100`;
    return 'Not Tested';
  }

  // ── Conversational Copilot Chat ──────────────────────────────────────────
  function addUserMessage(text) {
    const emptyState = $('copilot-empty-state');
    if (emptyState) emptyState.style.display = 'none';

    const row = document.createElement('div');
    row.className = 'chat-message-row user';
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble user';
    bubble.textContent = text;
    row.appendChild(bubble);
    chatScroll?.appendChild(row);
    chatScroll?.scrollTo({ top: chatScroll.scrollHeight, behavior: 'smooth' });
  }

  function addBotMessage(text, metaOrOut = '') {
    const emptyState = $('copilot-empty-state');
    if (emptyState) emptyState.style.display = 'none';

    const row = document.createElement('div');
    row.className = 'chat-message-row bot';

    let servedBy = '';
    let decCount = 0;
    let latencyMs = null;
    let tagsHtml = '';

    if (typeof metaOrOut === 'object' && metaOrOut !== null) {
      servedBy = metaOrOut.served_by || '';
      decCount = (metaOrOut.decisions || []).length;
      latencyMs = metaOrOut.latency_ms;
      const ms = latencyMs != null ? `${(latencyMs / 1000).toFixed(1)}s` : '';
      const tags = [];
      if (servedBy) tags.push(`<span class="bot-served-tag">${esc(servedBy)}</span>`);
      if (decCount > 0) tags.push(`<span>${decCount} decision${decCount === 1 ? '' : 's'}</span>`);
      if (ms) tags.push(`<span>${ms}</span>`);
      tagsHtml = tags.join(' · ');
    } else if (typeof metaOrOut === 'string' && metaOrOut) {
      tagsHtml = `<span>${esc(metaOrOut)}</span>`;
    }

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble bot md';

    bubble.innerHTML = `
      <div class="bot-message-header">
        <div class="bot-identity">
          <span class="bot-avatar-badge">DD</span>
          <span>DesignDoctor Copilot</span>
        </div>
        <div class="bot-meta-tags">
          ${tagsHtml}
        </div>
      </div>
      <div class="bot-message-body">
        ${renderMarkdown(text)}
      </div>`;

    row.appendChild(bubble);
    chatScroll?.appendChild(row);
    chatScroll?.scrollTo({ top: chatScroll.scrollHeight, behavior: 'smooth' });
    return bubble;
  }

  function showLoadingIndicator(statusText = 'Analyzing with Strands Decider & static diagnostics...') {
    hideLoadingIndicator();
    const row = document.createElement('div');
    row.className = 'chat-message-row bot';
    row.id = 'copilot-typing';
    row.innerHTML = `
      <div class="copilot-loading-row">
        <div class="copilot-spinner"></div>
        <span>${esc(statusText)}</span>
      </div>`;
    chatScroll?.appendChild(row);
    chatScroll?.scrollTo({ top: chatScroll.scrollHeight, behavior: 'smooth' });
  }

  function hideLoadingIndicator() {
    const el = $('copilot-typing');
    if (el) el.remove();
  }

  function renderErrorMessage(errMsg, retryQuery = '') {
    hideLoadingIndicator();
    const row = document.createElement('div');
    row.className = 'chat-message-row bot';
    const card = document.createElement('div');
    card.className = 'copilot-error-card';
    card.innerHTML = `
      <div class="copilot-error-head">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        <span>Audit Copilot Notice</span>
      </div>
      <div>${esc(errMsg)}</div>
      ${retryQuery ? `<button class="copilot-retry-btn" type="button">Retry Query</button>` : ''}
    `;
    if (retryQuery) {
      card.querySelector('.copilot-retry-btn')?.addEventListener('click', () => {
        card.remove();
        sendChatMessage(retryQuery);
      });
    }
    row.appendChild(card);
    chatScroll?.appendChild(row);
    chatScroll?.scrollTo({ top: chatScroll.scrollHeight, behavior: 'smooth' });
  }

  async function sendChatMessage(customText) {
    if (state.isChatting) return;
    const input = $('m') || $('msg');
    const rawText = (customText || input?.value || '').trim();
    if (!rawText) return;

    // Resolve any {url} placeholders with current target URL
    const resolvedText = rawText.replace(/\{url\}/gi, state.currentUrl || 'https://example.com');

    // Clear input only after submission is accepted
    if (input) {
      input.value = '';
      input.style.height = 'auto';
    }

    state.isChatting = true;
    if (sendBtn) sendBtn.disabled = true;

    // Render user message immediately
    addUserMessage(resolvedText);
    showLoadingIndicator('Routing via Strands Decider 2B & static engine...');

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: resolvedText,
          session_id: 'demo',
          url: state.currentUrl || 'https://example.com',
        }),
      });

      hideLoadingIndicator();

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ error: `Server returned HTTP ${res.status}` }));
        renderErrorMessage(errJson.error || 'Server error occurred during processing.', resolvedText);
        return;
      }

      const out = await res.json();

      // Crucial: increment turn counter for Playwright automation compatibility
      state.turnsCount++;
      document.body.dataset.turns = String(state.turnsCount);

      // Render any Strands Decider 2B decisions returned
      if (Array.isArray(out.decisions) && out.decisions.length > 0) {
        out.decisions.forEach((d) => renderDeciderState(d));
      }

      if (out.error) {
        renderErrorMessage(out.error, resolvedText);
      } else {
        addBotMessage(out.reply || '', out);
        state.chatHistory.push({
          role: 'assistant',
          content: out.reply,
          decisions: out.decisions,
          served_by: out.served_by,
        });
      }
    } catch (err) {
      hideLoadingIndicator();
      renderErrorMessage(`Network connection failure: ${err.message}`, resolvedText);
    } finally {
      state.isChatting = false;
      if (sendBtn) sendBtn.disabled = false;
      input?.focus();
    }
  }

  function initNewChat() {
    fetch('/api/reset', { method: 'POST' }).catch(() => {});
    state.turnsCount = 0;
    document.body.dataset.turns = '0';
    state.chatHistory = [];
    if (chatScroll) {
      chatScroll.innerHTML = `
        <div class="copilot-welcome-card" id="copilot-empty-state">
          <div class="welcome-header">
            <div class="welcome-badge">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 14h-2v-2h2zm0-4h-2V7h2z"></path></svg>
              <span>DesignDoctor Copilot 2.0</span>
            </div>
            <h2 class="welcome-title">Production UI/UX Intelligence</h2>
            <p class="welcome-subtitle">
              Strands Decider 2B neural tool routing paired with deterministic static HTML analysis. Ask any question about website accessibility, typography, layout, or performance.
            </p>
          </div>
          <div class="welcome-actions-grid">
            <div class="welcome-action-card" data-prompt="Audit the accessibility of {url}">
              <div class="welcome-card-icon">♿</div>
              <div class="welcome-card-title">Accessibility Diagnostic</div>
              <div class="welcome-card-desc">Inspect ARIA attributes, missing alt text, form labels, and WCAG AA contrast.</div>
            </div>
            <div class="welcome-action-card" data-prompt="Check the typography and heading structure for {url}">
              <div class="welcome-card-icon">🔤</div>
              <div class="welcome-card-title">Typography &amp; Hierarchy</div>
              <div class="welcome-card-desc">Validate single H1 structure, font sizing, line length, and meta descriptions.</div>
            </div>
            <div class="welcome-action-card" data-prompt="Is this page going to look broken on a mobile phone?">
              <div class="welcome-card-icon">📐</div>
              <div class="welcome-card-title">Mobile Layout Check</div>
              <div class="welcome-card-desc">Detect missing viewport tags, disabled pinch-to-zoom, and container overflow.</div>
            </div>
            <div class="welcome-action-card" data-prompt="Summarise the top 3 high-impact fixes I should make for {url}">
              <div class="welcome-card-icon">🚀</div>
              <div class="welcome-card-title">Priority Remediations</div>
              <div class="welcome-card-desc">Get an executive list of the highest-impact fixes for the active target URL.</div>
            </div>
          </div>
        </div>`;
      bindWelcomeCards();
    }
    const routeLabel = $('decider-route-label');
    if (routeLabel) routeLabel.textContent = 'Awaiting Query';
    if (deciderStatusPill) {
      deciderStatusPill.className = 'decider-status-pill narrowed';
      deciderStatusPill.textContent = 'Ready';
    }
    if (deciderLatencyVal) deciderLatencyVal.textContent = 'Telemetry Ready';
  }

  function bindWelcomeCards() {
    $$('.welcome-action-card').forEach((card) => {
      card.addEventListener('click', () => {
        const promptText = card.getAttribute('data-prompt');
        if (promptText) sendChatMessage(promptText);
      });
    });
  }

  // ── Event Handlers & Bindings ────────────────────────────────────────────
  // URL Inspection Bar
  auditBtn?.addEventListener('click', () => {
    runAudit(urlField?.value || 'https://example.com');
  });

  urlField?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      runAudit(urlField.value || 'https://example.com');
    }
  });

  // URL Field Blur & Paste sanitization
  if (urlField) {
    urlField.addEventListener('blur', () => {
      if (urlField.value.trim()) {
        urlField.value = sanitizeAndNormalizeUrl(urlField.value);
      }
    });
    urlField.addEventListener('paste', () => {
      setTimeout(() => {
        if (urlField.value.trim()) {
          urlField.value = sanitizeAndNormalizeUrl(urlField.value);
        }
      }, 0);
    });
  }

  // Preset Chips
  $$('.preset-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const presetUrl = chip.dataset.url;
      if (presetUrl) {
        const normalized = sanitizeAndNormalizeUrl(presetUrl);
        if (urlField) urlField.value = normalized;
        runAudit(normalized);
      }
    });
  });

  // Tool Filter Chips on Command Bar (Manual Scope Selection)
  $$('.tool-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      $$('.tool-chip').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      const tool = chip.dataset.tool || 'all';
      runAudit(urlField?.value || state.currentUrl, tool);
    });
  });

  // Pillar Card Clicks (Drill down into findings)
  $$('.pillar-card').forEach((card) => {
    card.addEventListener('click', () => {
      const pillar = card.dataset.pillar;
      state.currentPillarFilter = pillar || 'all';
      $$('.pillar-card').forEach((c) => c.classList.toggle('active', c.dataset.pillar === pillar));
      renderFindings(state.allIssues);
      
      // If on mobile, switch to findings view
      if (window.innerWidth < 1024) {
        setMobileView('findings');
      }
    });
  });

  // Findings Severity Filters
  $$('.filter-pill').forEach((pill) => {
    pill.addEventListener('click', () => {
      $$('.filter-pill').forEach((p) => p.classList.remove('active'));
      pill.classList.add('active');
      state.currentSeverityFilter = pill.dataset.severity || 'all';
      renderFindings(state.allIssues);
    });
  });

  // Chat Input & Enter to Send
  const chatInputEl = $('m') || $('msg');
  if (chatInputEl) {
    chatInputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
    chatInputEl.addEventListener('input', () => {
      chatInputEl.style.height = 'auto';
      chatInputEl.style.height = `${Math.min(chatInputEl.scrollHeight, 120)}px`;
    });
  }

  sendBtn?.addEventListener('click', () => sendChatMessage());

  // Quick Prompt Chips
  $$('.prompt-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const promptText = chip.dataset.prompt;
      if (promptText) {
        sendChatMessage(promptText.replace('{url}', state.currentUrl));
      }
    });
  });

  // Report Exporter
  reportBtn?.addEventListener('click', () => {
    if (!state.auditData) {
      alert('No audit data yet. Please run an audit on a website first.');
      return;
    }
    const reportPayload = {
      product: 'DesignDoctor AI 2.0',
      timestamp: new Date().toISOString(),
      url: state.currentUrl,
      overall_score: state.auditData.overall_score,
      is_partial: state.auditData.is_partial,
      coverage_label: state.auditData.coverage_label,
      results: state.auditData.results,
      issues: state.allIssues,
      engine: 'Strands Decider 2B (#tool-selection)',
      kit_credit: 'Built with the AWS User Group Madurai Strands Decider hackathon kit',
    };
    const blob = new Blob([JSON.stringify(reportPayload, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `designdoctor-audit-${new URL(state.currentUrl).hostname}-${Date.now()}.json`;
    a.click();
  });

  // Copy Markdown Report
  copyMdBtn?.addEventListener('click', async () => {
    if (!state.auditData) {
      alert('No audit data yet. Please run an audit first.');
      return;
    }
    const scoreVal = state.auditData.overall_score != null ? `${state.auditData.overall_score}/100` : '—';
    const partialNotice = state.auditData.is_partial ? `\n> **Notice:** ${state.auditData.coverage_warning}` : '';
    const mdSummary = [
      `# DesignDoctor AI Audit Report: ${state.currentUrl}`,
      `**Generated:** ${new Date().toUTCString()}`,
      `**Overall UX Health Score:** ${scoreVal}${partialNotice}`,
      '',
      '## Pillar Scores',
      `- Accessibility: ${state.auditData.results?.accessibility?.score != null ? state.auditData.results.accessibility.score + '/100' : (state.auditData.results?.accessibility?.state || 'Not Tested')}`,
      `- Typography: ${state.auditData.results?.typography?.score != null ? state.auditData.results.typography.score + '/100' : (state.auditData.results?.typography?.state || 'Not Tested')}`,
      `- Layout & Responsiveness: ${state.auditData.results?.layout?.score != null ? state.auditData.results.layout.score + '/100' : (state.auditData.results?.layout?.state || 'Not Tested')}`,
      `- Performance Hints: ${state.auditData.results?.performance?.score != null ? state.auditData.results.performance.score + '/100' : (state.auditData.results?.performance?.state || 'Not Tested')}`,
      '',
      '## Critical & Key Issues Found',
      ...state.allIssues.map((i) => `- [${i.severity?.toUpperCase() || 'INFO'}] **${i.category}**: ${i.finding}\n  - Fix: ${i.fix}${i.wcag ? ` (${i.wcag})` : ''}`),
      '',
      '---',
      'Built with the AWS User Group Madurai Strands Decider hackathon kit',
    ].join('\n');

    try {
      await navigator.clipboard.writeText(mdSummary);
      const originalText = copyMdBtn.innerHTML;
      copyMdBtn.innerHTML = '✓ Copied';
      setTimeout(() => { copyMdBtn.innerHTML = originalText; }, 2000);
    } catch {
      alert('Clipboard access denied.');
    }
  });

  // Session Reset
  resetBtn?.addEventListener('click', async () => {
    if (!confirm('Start a new audit session? This clears the current findings and chat.')) return;
    try {
      await fetch('/api/reset', { method: 'POST' });
    } catch {}
    state.turnsCount = 0;
    document.body.dataset.turns = '0';
    state.auditData = null;
    state.allIssues = [];
    if (chatScroll) chatScroll.innerHTML = '';
    if (deciderProbBars) deciderProbBars.innerHTML = '';
    if (deciderHistoryList) deciderHistoryList.innerHTML = '';
    updateGauge(null);
    renderPillars({});
    renderFindings([]);
    addBotMessage('Session reset. Enter a URL above or ask a design question to begin.', 'DesignDoctor AI · ready');
  });

  // ── Focus Mode Management ────────────────────────────────────────────────
  function setFocusMode(isFocus) {
    const ws = document.querySelector('main.workspace');
    if (!ws) return;

    if (isFocus) {
      ws.classList.add('focus-copilot');
      document.body.classList.add('is-focus-mode');
    } else {
      ws.classList.remove('focus-copilot');
      document.body.classList.remove('is-focus-mode');
    }

    const active = ws.classList.contains('focus-copilot');
    sessionStorage.setItem('designdoctor_focus_mode', active ? '1' : '0');

    // Update Focus button in Copilot header
    const focusBtn = $('toggle-focus-btn');
    const focusLabel = $('toggle-focus-label');
    if (focusBtn) {
      focusBtn.classList.toggle('active', active);
      focusBtn.title = active ? 'Return to Split Dashboard View' : 'Expand Copilot into Full Workspace';
    }
    if (focusLabel) {
      focusLabel.textContent = active ? 'Exit Focus' : 'Focus Mode';
    }

    // Update Header Focus button
    const headerFocusBtn = $('header-focus-btn');
    const headerFocusLabel = $('header-focus-label');
    if (headerFocusBtn) {
      headerFocusBtn.classList.toggle('active', active);
      headerFocusBtn.title = active ? 'Return to Dashboard View' : 'Expand Copilot to Full Workspace';
    }
    if (headerFocusLabel) {
      headerFocusLabel.textContent = active ? 'Dashboard' : 'Copilot Workspace';
    }

    // Auto-scroll chat to preserve reading position
    if (chatScroll) {
      setTimeout(() => {
        chatScroll.scrollTo({ top: chatScroll.scrollHeight, behavior: 'smooth' });
      }, 60);
    }

    if (active) {
      const input = $('m') || $('msg');
      input?.focus();
    }
  }

  // ── Mobile Segmented View Controller ─────────────────────────────────────
  function setMobileView(view) {
    state.activeMobileView = view;

    $$('.segment-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.view === view);
    });

    const panelLeft = $('panel-left');
    const panelRight = $('panel-right');
    const overviewSec = $('overview-section');
    const findingsSec = $('findings-section');
    const deciderSec = $('decider-section');

    if (view === 'overview') {
      panelLeft?.classList.add('mobile-active');
      panelRight?.classList.remove('mobile-active');
      if (overviewSec) overviewSec.style.display = 'flex';
      if (findingsSec) findingsSec.style.display = 'none';
    } else if (view === 'findings') {
      panelLeft?.classList.add('mobile-active');
      panelRight?.classList.remove('mobile-active');
      if (overviewSec) overviewSec.style.display = 'none';
      if (findingsSec) findingsSec.style.display = 'block';
    } else if (view === 'decider') {
      panelRight?.classList.add('mobile-active');
      panelLeft?.classList.remove('mobile-active');
      deciderSec?.classList.add('expanded');
      $('toggle-decider-btn')?.classList.add('active');
    } else if (view === 'copilot') {
      panelRight?.classList.add('mobile-active');
      panelLeft?.classList.remove('mobile-active');
      if (chatScroll) {
        setTimeout(() => {
          chatScroll.scrollTo({ top: chatScroll.scrollHeight, behavior: 'smooth' });
        }, 60);
      }
    }
  }

  // Mobile segmented control button clicks
  $$('.segment-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.view;
      if (view) setMobileView(view);
    });
  });

  // Focus Mode Trigger Buttons
  $('toggle-focus-btn')?.addEventListener('click', () => {
    const ws = document.querySelector('main.workspace');
    setFocusMode(!ws?.classList.contains('focus-copilot'));
  });

  $('header-focus-btn')?.addEventListener('click', () => {
    const ws = document.querySelector('main.workspace');
    setFocusMode(!ws?.classList.contains('focus-copilot'));
  });

  $('back-to-dashboard-btn')?.addEventListener('click', () => {
    setFocusMode(false);
  });

  $('left-expand-copilot-btn')?.addEventListener('click', () => {
    setFocusMode(true);
  });

  // New Chat Action
  $('new-chat-btn')?.addEventListener('click', () => {
    initNewChat();
  });

  // Decider Telemetry Drawer Toggles
  $('toggle-decider-btn')?.addEventListener('click', () => {
    const sec = $('decider-section');
    sec?.classList.toggle('expanded');
    const isExpanded = sec?.classList.contains('expanded');
    $('toggle-decider-btn')?.classList.toggle('active', isExpanded);
  });

  $('decider-expand-btn')?.addEventListener('click', () => {
    const sec = $('decider-section');
    sec?.classList.toggle('expanded');
    const isExpanded = sec?.classList.contains('expanded');
    $('toggle-decider-btn')?.classList.toggle('active', isExpanded);
  });

  // Global Code Block Copy Handler
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.copy-code-btn');
    if (btn) {
      const code = btn.getAttribute('data-clipboard') || '';
      const label = btn.querySelector('span');
      const setCopied = () => {
        if (label) label.textContent = 'Copied! ✓';
        btn.classList.add('copied');
        setTimeout(() => {
          if (label) label.textContent = 'Copy';
          btn.classList.remove('copied');
        }, 2000);
      };

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code).then(setCopied).catch(() => {
          const ta = document.createElement('textarea');
          ta.value = code;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          setCopied();
        });
      } else {
        const ta = document.createElement('textarea');
        ta.value = code;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        setCopied();
      }
    }
  });

  // Bind Welcome Cards click listeners
  bindWelcomeCards();

  // Restore saved focus mode if set
  if (sessionStorage.getItem('designdoctor_focus_mode') === '1') {
    setFocusMode(true);
  }

  // Initial trigger on load with default example.com
  runAudit('https://example.com');
})();
