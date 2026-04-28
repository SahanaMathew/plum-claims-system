/* =====================================================
   Plum Claims Processing System — Frontend JS
   ===================================================== */

const API = '';  // relative URLs — same origin

// ---- State ----
let testCasesData = [];
let documentsCount = 0;

// ---- Utility ----
function $(id) { return document.getElementById(id); }

function showToast(msg, type = 'info') {
  const container = $('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function showLoading(text = 'Processing claim...') {
  $('loadingText').textContent = text;
  $('loadingOverlay').classList.add('visible');
}

function hideLoading() {
  $('loadingOverlay').classList.remove('visible');
}

function formatCurrency(amount) {
  if (amount === null || amount === undefined) return '—';
  return '₹' + Number(amount).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ---- Tab Navigation ----
function switchTab(tabId) {
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');
  $(tabId).classList.add('active');
  if (tabId === 'tabHistory') refreshHistory();
}

// ---- Document Management ----
function addDocument(prefillData = null) {
  documentsCount++;
  const idx = documentsCount;
  const container = $('documentsContainer');

  const div = document.createElement('div');
  div.className = 'doc-item';
  div.id = `doc-${idx}`;

  const p = prefillData || {};

  div.innerHTML = `
    <div class="doc-item-header">
      <span>Document #${idx}</span>
      <button class="btn btn-danger btn-sm" onclick="removeDocument(${idx})">Remove</button>
    </div>
    <div class="doc-grid">
      <div class="form-group">
        <label>File ID *</label>
        <input type="text" id="doc-fileid-${idx}" placeholder="e.g. F001" value="${escapeHtml(p.file_id || '')}">
      </div>
      <div class="form-group">
        <label>File Name</label>
        <input type="text" id="doc-filename-${idx}" placeholder="e.g. prescription.jpg" value="${escapeHtml(p.file_name || '')}">
      </div>
      <div class="form-group">
        <label>Document Type</label>
        <select id="doc-type-${idx}">
          <option value="">-- Select Type --</option>
          <option value="PRESCRIPTION" ${p.actual_type === 'PRESCRIPTION' ? 'selected' : ''}>PRESCRIPTION</option>
          <option value="HOSPITAL_BILL" ${p.actual_type === 'HOSPITAL_BILL' ? 'selected' : ''}>HOSPITAL_BILL</option>
          <option value="PHARMACY_BILL" ${p.actual_type === 'PHARMACY_BILL' ? 'selected' : ''}>PHARMACY_BILL</option>
          <option value="LAB_REPORT" ${p.actual_type === 'LAB_REPORT' ? 'selected' : ''}>LAB_REPORT</option>
          <option value="DISCHARGE_SUMMARY" ${p.actual_type === 'DISCHARGE_SUMMARY' ? 'selected' : ''}>DISCHARGE_SUMMARY</option>
          <option value="DENTAL_REPORT" ${p.actual_type === 'DENTAL_REPORT' ? 'selected' : ''}>DENTAL_REPORT</option>
          <option value="DIAGNOSTIC_REPORT" ${p.actual_type === 'DIAGNOSTIC_REPORT' ? 'selected' : ''}>DIAGNOSTIC_REPORT</option>
          <option value="UNKNOWN" ${p.actual_type === 'UNKNOWN' ? 'selected' : ''}>UNKNOWN</option>
        </select>
      </div>
    </div>
    <div class="doc-grid">
      <div class="form-group">
        <label>Quality</label>
        <select id="doc-quality-${idx}">
          <option value="">-- Not specified --</option>
          <option value="GOOD" ${p.quality === 'GOOD' ? 'selected' : ''}>GOOD</option>
          <option value="PARTIAL" ${p.quality === 'PARTIAL' ? 'selected' : ''}>PARTIAL</option>
          <option value="UNREADABLE" ${p.quality === 'UNREADABLE' ? 'selected' : ''}>UNREADABLE</option>
        </select>
      </div>
      <div class="form-group">
        <label>Patient Name on Doc</label>
        <input type="text" id="doc-patient-${idx}" placeholder="Name printed on document" value="${escapeHtml(p.patient_name_on_doc || '')}">
      </div>
    </div>
    <div class="form-group">
      <label>Content JSON (structured data — leave blank for LLM extraction)</label>
      <textarea id="doc-content-${idx}" placeholder='{"diagnosis": "Fever", "line_items": [{"description": "Consultation", "amount": 500}]}'>${p.content ? JSON.stringify(p.content, null, 2) : ''}</textarea>
    </div>
  `;

  container.appendChild(div);
}

function removeDocument(idx) {
  const el = $(`doc-${idx}`);
  if (el) el.remove();
}

function clearDocuments() {
  $('documentsContainer').innerHTML = '';
  documentsCount = 0;
}

function collectDocuments() {
  const docs = [];
  document.querySelectorAll('.doc-item').forEach(el => {
    const idx = el.id.replace('doc-', '');
    const fileId = $(`doc-fileid-${idx}`)?.value?.trim();
    if (!fileId) return;

    let content = null;
    const contentRaw = $(`doc-content-${idx}`)?.value?.trim();
    if (contentRaw) {
      try { content = JSON.parse(contentRaw); }
      catch (e) { showToast(`Document #${idx}: Invalid JSON in content field`, 'error'); }
    }

    docs.push({
      file_id: fileId,
      file_name: $(`doc-filename-${idx}`)?.value?.trim() || null,
      actual_type: $(`doc-type-${idx}`)?.value || null,
      quality: $(`doc-quality-${idx}`)?.value || null,
      content: content,
      patient_name_on_doc: $(`doc-patient-${idx}`)?.value?.trim() || null,
    });
  });
  return docs;
}

// ---- Test Case Loader ----
async function loadTestCasesList() {
  try {
    const res = await fetch(`${API}/api/test-cases`);
    const data = await res.json();
    testCasesData = data.test_cases || [];

    const sel = $('testCaseSelect');
    sel.innerHTML = '<option value="">-- Load a test case --</option>';
    testCasesData.forEach(tc => {
      const opt = document.createElement('option');
      opt.value = tc.case_id;
      opt.textContent = `${tc.case_id}: ${tc.case_name}`;
      sel.appendChild(opt);
    });

    // Also populate the run-tests tab
    renderTestCaseCards();
  } catch (e) {
    console.warn('Could not load test cases:', e);
  }
}

function loadTestCase() {
  const caseId = $('testCaseSelect').value;
  if (!caseId) return;

  const tc = testCasesData.find(t => t.case_id === caseId);
  if (!tc) return;

  const inp = tc.input;

  $('memberId').value = inp.member_id || '';
  $('policyId').value = inp.policy_id || 'PLUM_GHI_2024';
  $('claimCategory').value = inp.claim_category || '';
  $('treatmentDate').value = inp.treatment_date || '';
  $('claimedAmount').value = inp.claimed_amount || '';
  $('hospitalName').value = inp.hospital_name || '';
  $('ytdAmount').value = inp.ytd_claims_amount || 0;
  $('simulateFailure').checked = !!inp.simulate_component_failure;

  // Claims history
  $('claimsHistory').value = inp.claims_history?.length
    ? JSON.stringify(inp.claims_history, null, 2)
    : '';

  // Documents
  clearDocuments();
  (inp.documents || []).forEach(d => addDocument(d));

  showToast(`Loaded ${caseId}: ${tc.case_name}`, 'info');

  // Hide previous decision
  $('decisionPanel').classList.remove('visible');
}

// ---- Form Submit ----
async function submitClaim() {
  const memberId = $('memberId').value.trim();
  const policyId = $('policyId').value.trim();
  const category = $('claimCategory').value;
  const treatmentDate = $('treatmentDate').value;
  const claimedAmount = parseFloat($('claimedAmount').value);

  if (!memberId || !policyId || !category || !treatmentDate || isNaN(claimedAmount)) {
    showToast('Please fill in all required fields', 'error');
    return;
  }

  const docs = collectDocuments();
  if (docs.length === 0) {
    showToast('Please add at least one document', 'error');
    return;
  }

  let claimsHistory = [];
  const histRaw = $('claimsHistory').value.trim();
  if (histRaw) {
    try { claimsHistory = JSON.parse(histRaw); }
    catch (e) { showToast('Invalid JSON in claims history', 'error'); return; }
  }

  const payload = {
    member_id: memberId,
    policy_id: policyId,
    claim_category: category,
    treatment_date: treatmentDate,
    claimed_amount: claimedAmount,
    hospital_name: $('hospitalName').value.trim() || null,
    ytd_claims_amount: parseFloat($('ytdAmount').value) || 0,
    claims_history: claimsHistory,
    documents: docs,
    simulate_component_failure: $('simulateFailure').checked,
  };

  showLoading('Processing claim through AI pipeline...');
  try {
    const res = await fetch(`${API}/api/submit-claim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const result = await res.json();
    renderDecision(result);
    $('decisionPanel').classList.add('visible');
    $('decisionPanel').scrollIntoView({ behavior: 'smooth' });
    showToast('Claim processed successfully', 'success');
  } catch (e) {
    showToast(`Error: ${e.message}`, 'error');
    console.error(e);
  } finally {
    hideLoading();
  }
}

// ---- Render Decision ----
function renderDecision(result) {
  const panel = $('decisionPanel');

  const decision = result.decision || 'EARLY_EXIT';
  const badgeClass = `badge-${decision}`;

  const decisionLabels = {
    APPROVED: 'Approved',
    REJECTED: 'Rejected',
    PARTIAL: 'Partial Approval',
    MANUAL_REVIEW: 'Manual Review',
    EARLY_EXIT: 'Document Issue',
    null: 'Document Issue',
  };

  const decisionIcons = {
    APPROVED: '✓',
    REJECTED: '✗',
    PARTIAL: '◑',
    MANUAL_REVIEW: '⚠',
    EARLY_EXIT: '⚑',
    null: '⚑',
  };

  panel.innerHTML = `
    <div class="card">
      <div class="decision-header">
        <div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">
            Claim ID: <strong>${escapeHtml(result.claim_id)}</strong> &nbsp;|&nbsp;
            Member: <strong>${escapeHtml(result.member_id)}</strong>
          </div>
          <span class="decision-badge ${badgeClass}">
            ${decisionIcons[decision] || '?'} ${decisionLabels[decision] || decision}
          </span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span class="pipeline-status-chip status-chip-${result.pipeline_status}">${result.pipeline_status}</span>
        </div>
      </div>

      ${result.rejection_reasons?.length ? `
        <div class="rejection-chips">
          ${result.rejection_reasons.map(r => `<span class="rejection-chip">${escapeHtml(r)}</span>`).join('')}
        </div>
      ` : ''}

      <div class="decision-amounts">
        <div class="amount-card">
          <div class="amount-label">Claimed Amount</div>
          <div class="amount-value">${formatCurrency(result.claimed_amount)}</div>
        </div>
        <div class="amount-card">
          <div class="amount-label">Approved Amount</div>
          <div class="amount-value ${decision === 'APPROVED' || decision === 'PARTIAL' ? 'approved' : decision === 'REJECTED' ? 'rejected' : ''}">
            ${result.approved_amount !== null && result.approved_amount !== undefined
              ? formatCurrency(result.approved_amount)
              : '—'}
          </div>
        </div>
        <div class="amount-card">
          <div class="amount-label">Confidence</div>
          <div class="amount-value">${result.confidence_score !== null && result.confidence_score !== undefined
            ? (result.confidence_score * 100).toFixed(0) + '%'
            : '—'
          }</div>
        </div>
      </div>

      ${result.confidence_score !== null && result.confidence_score !== undefined ? `
        <div class="confidence-bar">
          <div class="confidence-label">
            <span>Confidence Score</span>
            <span>${(result.confidence_score * 100).toFixed(0)}%</span>
          </div>
          <div class="confidence-track">
            <div class="confidence-fill" style="width:${result.confidence_score * 100}%;background:${
              result.confidence_score >= 0.8 ? 'var(--approved)' :
              result.confidence_score >= 0.5 ? 'var(--partial)' :
              'var(--rejected)'
            };"></div>
          </div>
        </div>
      ` : ''}

      <div class="decision-message">${escapeHtml(result.message)}</div>

      ${result.partial_items?.length ? renderPartialItems(result.partial_items) : ''}

      ${result.trace?.length ? renderTrace(result.trace) : ''}
    </div>
  `;
}

function renderPartialItems(items) {
  const rows = items.map(item => `
    <tr>
      <td>${escapeHtml(item.description || 'Unknown')}</td>
      <td>${formatCurrency(item.amount)}</td>
      <td class="item-${item.status}">${item.status}</td>
      <td style="color:var(--text-muted);font-size:11px;">${escapeHtml(item.reason || item.exclusion_matched || '')}</td>
    </tr>
  `).join('');

  return `
    <div style="margin-bottom:16px;">
      <div class="trace-title">Line Item Breakdown</div>
      <table class="partial-items-table">
        <thead>
          <tr><th>Description</th><th>Amount</th><th>Status</th><th>Reason</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderTrace(trace) {
  const steps = trace.map((step, i) => {
    const dotClass = `dot-${step.status}`;
    const badgeClass = `status-${step.status}`;
    const id = `trace-step-${i}`;

    const checksHtml = step.checks?.length ? `
      <div class="trace-field">
        <div class="trace-field-label">Checks</div>
        <div class="checks-list">
          ${step.checks.map(c => {
            const icon = c.status === 'PASSED' || c.status === 'APPROVED' ? '✓' :
                         c.status === 'FAILED' ? '✗' :
                         c.status === 'FLAGGED' ? '⚠' :
                         c.status === 'APPLIED' ? '→' : '•';
            const cssClass = `check-status-${c.status || 'PASSED'}`;
            return `
              <div class="check-item ${cssClass}">
                <span class="check-icon">${icon}</span>
                <div>
                  <strong>${escapeHtml(c.check)}</strong>
                  ${c.detail ? `<br><span style="color:var(--text-muted)">${escapeHtml(c.detail)}</span>` : ''}
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    ` : '';

    return `
      <div class="trace-step" id="${id}">
        <div class="trace-step-header" onclick="toggleTrace('${id}')">
          <div class="trace-status-dot ${dotClass}"></div>
          <span class="trace-agent-name">${escapeHtml(step.agent)}</span>
          <span class="trace-status-badge ${badgeClass}">${step.status}</span>
          ${step.timestamp ? `<span style="font-size:10px;color:var(--text-muted);">${step.timestamp.split('T')[1]?.split('.')[0] || ''}</span>` : ''}
          <span class="trace-chevron">▶</span>
        </div>
        <div class="trace-step-body">
          ${step.input_summary ? `
            <div class="trace-field">
              <div class="trace-field-label">Input</div>
              <div class="trace-field-value">${escapeHtml(step.input_summary)}</div>
            </div>
          ` : ''}
          ${step.output_summary ? `
            <div class="trace-field">
              <div class="trace-field-label">Output</div>
              <div class="trace-field-value">${escapeHtml(step.output_summary)}</div>
            </div>
          ` : ''}
          ${checksHtml}
          ${step.error ? `
            <div class="trace-field">
              <div class="trace-field-label">Error</div>
              <div class="trace-field-value" style="color:var(--rejected)">${escapeHtml(step.error)}</div>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="trace-container">
      <div class="trace-title">Agent Pipeline Trace (${trace.length} steps)</div>
      ${steps}
    </div>
  `;
}

function toggleTrace(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('open');
}

// ---- Claims History ----
async function refreshHistory() {
  try {
    const res = await fetch(`${API}/api/claims`);
    const claims = await res.json();
    renderHistoryTable(claims);
  } catch (e) {
    $('historyTableBody').innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">Could not load claims</td></tr>';
  }
}

function renderHistoryTable(claims) {
  const tbody = $('historyTableBody');
  if (!claims.length) {
    tbody.innerHTML = `
      <tr><td colspan="7">
        <div class="empty-state">
          <div class="empty-icon">📋</div>
          <p>No claims processed yet in this session.</p>
        </div>
      </td></tr>
    `;
    return;
  }

  tbody.innerHTML = claims.map(c => {
    const decision = c.decision || 'EARLY_EXIT';
    const badgeClass = `badge-${decision}`;
    return `
      <tr>
        <td><code>${escapeHtml(c.claim_id)}</code></td>
        <td>${escapeHtml(c.member_id)}</td>
        <td>${formatCurrency(c.claimed_amount)}</td>
        <td>${c.approved_amount !== null && c.approved_amount !== undefined ? formatCurrency(c.approved_amount) : '—'}</td>
        <td><span class="decision-badge ${badgeClass}" style="font-size:11px;padding:3px 10px;">${decision}</span></td>
        <td><span class="pipeline-status-chip status-chip-${c.pipeline_status}" style="font-size:11px;">${c.pipeline_status}</span></td>
        <td style="font-size:11px;color:var(--text-muted);">${c.created_at?.split('T')[0] || ''}</td>
      </tr>
    `;
  }).join('');
}

// ---- Run All Test Cases ----
function renderTestCaseCards() {
  const container = $('testCaseCards');
  if (!testCasesData.length) {
    container.innerHTML = '<div class="empty-state"><p>Test cases not loaded.</p></div>';
    return;
  }

  container.innerHTML = testCasesData.map(tc => `
    <div class="test-card" id="tc-card-${tc.case_id}">
      <div class="test-card-id">${tc.case_id}</div>
      <div class="test-card-name">${escapeHtml(tc.case_name)}</div>
      <div class="test-card-desc">${escapeHtml(tc.description)}</div>
      <div class="test-result-row" id="tc-result-${tc.case_id}">
        <span style="color:var(--text-muted);font-size:11px;">Not run</span>
      </div>
    </div>
  `).join('');
}

async function runAllTestCases() {
  const btn = $('runTestsBtn');
  btn.disabled = true;
  btn.textContent = 'Running...';

  $('testSummary').textContent = '';
  let passed = 0, failed = 0, total = testCasesData.length;

  for (const tc of testCasesData) {
    const card = $(`tc-card-${tc.case_id}`);
    const resultRow = $(`tc-result-${tc.case_id}`);

    card.className = 'test-card result-running';
    resultRow.innerHTML = '<div class="test-spinner"></div><span style="color:var(--accent);font-size:11px;">Running...</span>';

    try {
      const inp = tc.input;
      const payload = {
        member_id: inp.member_id,
        policy_id: inp.policy_id,
        claim_category: inp.claim_category,
        treatment_date: inp.treatment_date,
        claimed_amount: inp.claimed_amount,
        hospital_name: inp.hospital_name || null,
        ytd_claims_amount: inp.ytd_claims_amount || 0,
        claims_history: inp.claims_history || [],
        documents: inp.documents || [],
        simulate_component_failure: inp.simulate_component_failure || false,
      };

      const res = await fetch(`${API}/api/submit-claim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const result = await res.json();
      const expected = tc.expected;
      const { pass, reason } = evaluateTestCase(tc, result);

      if (pass) {
        passed++;
        card.className = 'test-card result-pass';
        resultRow.innerHTML = `
          <span style="color:var(--approved);font-weight:600;">PASS</span>
          <span class="decision-badge badge-${result.decision || 'null'}" style="font-size:10px;padding:2px 8px;">${result.decision || 'EARLY_EXIT'}</span>
        `;
      } else {
        failed++;
        card.className = 'test-card result-fail';
        resultRow.innerHTML = `
          <span style="color:var(--rejected);font-weight:600;">FAIL</span>
          <span style="font-size:10px;color:var(--text-muted);" title="${escapeHtml(reason)}">${escapeHtml(reason.substring(0, 60))}</span>
        `;
      }
    } catch (e) {
      failed++;
      card.className = 'test-card result-fail';
      $(`tc-result-${tc.case_id}`).innerHTML = `
        <span style="color:var(--rejected);font-weight:600;">ERROR</span>
        <span style="font-size:10px;color:var(--text-muted);">${escapeHtml(e.message)}</span>
      `;
    }

    // Small delay to show progress
    await new Promise(r => setTimeout(r, 200));
  }

  $('testSummary').innerHTML = `
    <div style="display:flex;gap:16px;align-items:center;padding:12px 0;">
      <span style="font-weight:700;font-size:16px;">Results: ${passed}/${total} passed</span>
      <span style="color:var(--approved);">${passed} PASS</span>
      <span style="color:var(--rejected);">${failed} FAIL</span>
    </div>
  `;

  btn.disabled = false;
  btn.textContent = 'Run All Test Cases';
  showToast(`Test run complete: ${passed}/${total} passed`, passed === total ? 'success' : 'error');
}

function evaluateTestCase(tc, result) {
  const expected = tc.expected;

  // TC001, TC002, TC003 — expect EARLY_EXIT
  if (expected.decision === null || expected.decision === undefined) {
    if (result.pipeline_status !== 'EARLY_EXIT') {
      return { pass: false, reason: `Expected EARLY_EXIT but got ${result.pipeline_status}` };
    }
    return { pass: true };
  }

  // Check decision
  if (expected.decision && result.decision !== expected.decision) {
    return { pass: false, reason: `Expected ${expected.decision}, got ${result.decision}` };
  }

  // Check approved amount (±1 tolerance)
  if (expected.approved_amount !== undefined && expected.approved_amount !== null) {
    if (result.approved_amount === null || result.approved_amount === undefined) {
      return { pass: false, reason: `Expected ₹${expected.approved_amount} but got null` };
    }
    if (Math.abs(result.approved_amount - expected.approved_amount) > 1) {
      return { pass: false, reason: `Expected ₹${expected.approved_amount}, got ₹${result.approved_amount}` };
    }
  }

  // Check rejection reasons
  if (expected.rejection_reasons) {
    for (const reason of expected.rejection_reasons) {
      if (!(result.rejection_reasons || []).includes(reason)) {
        return { pass: false, reason: `Missing rejection reason: ${reason}` };
      }
    }
  }

  // TC011 — component failure
  if (tc.case_id === 'TC011') {
    if (result.confidence_score >= 1.0) {
      return { pass: false, reason: `Confidence should be < 1.0 for degraded pipeline` };
    }
    if (!result.message.toLowerCase().includes('manual review') &&
        !result.message.toLowerCase().includes('component')) {
      return { pass: false, reason: 'Message should mention component failure' };
    }
  }

  return { pass: true };
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  // Set today as default treatment date
  const today = new Date().toISOString().split('T')[0];
  const dateInput = $('treatmentDate');
  if (dateInput && !dateInput.value) dateInput.value = today;

  // Load test cases
  loadTestCasesList();

  // Bind nav tabs
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });
});
