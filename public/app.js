const form = document.getElementById('generate-form');
const clientSelect = document.getElementById('client-select');
const companyInput = document.getElementById('company-input');
const positionInput = document.getElementById('position-input');
const jdInput = document.getElementById('jd-input');
const workRightsToggle = document.getElementById('work-rights-toggle');
const providerIndicator = document.getElementById('provider-indicator');
const providerModel = document.getElementById('provider-model');
const generateButton = document.getElementById('generate-button');
const statusBox = document.getElementById('status-box');
const previewTitle = document.getElementById('preview-title');
const previewSubtitle = document.getElementById('preview-subtitle');
const pdfFrame = document.getElementById('pdf-frame');
const openPdfLink = document.getElementById('open-pdf-link');
const downloadPdfLink = document.getElementById('download-pdf-link');
const summaryOutput = document.getElementById('summary-output');
const skillsOutput = document.getElementById('skills-output');
const auditOutput = document.getElementById('audit-output');
const currentUser = document.getElementById('current-user');
const currentAccess = document.getElementById('current-access');
const logoutButton = document.getElementById('logout-button');
const noClientsCard = document.getElementById('no-clients-card');
const noClientsMessage = document.getElementById('no-clients-message');

let cachedClients = [];
let authUser = null;

function setStatus(text) {
  statusBox.textContent = text;
}

function appendCacheBust(url, token) {
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}v=${encodeURIComponent(token)}`;
}

function enableExport(url, downloadUrl, filename, cacheToken) {
  const finalUrl = cacheToken ? appendCacheBust(url, cacheToken) : url;
  const finalDownloadUrl = cacheToken ? appendCacheBust((downloadUrl || url), cacheToken) : (downloadUrl || url);
  openPdfLink.href = finalUrl;
  downloadPdfLink.href = finalDownloadUrl;
  if (filename) {
    downloadPdfLink.setAttribute('download', filename);
  }
  openPdfLink.classList.remove('disabled');
  downloadPdfLink.classList.remove('disabled');
}

function disableExport() {
  openPdfLink.href = '#';
  downloadPdfLink.href = '#';
  downloadPdfLink.setAttribute('download', 'resume.pdf');
  openPdfLink.classList.add('disabled');
  downloadPdfLink.classList.add('disabled');
}

function setProviderIndicator(provider, model, ready = true) {
  const normalized = String(provider || '').toLowerCase();
  providerIndicator.textContent = normalized === 'openai' ? 'GPT' : normalized === 'gemini' ? 'Gemini' : provider || 'Unavailable';
  providerIndicator.className = `provider-indicator ${ready ? `provider-${normalized || 'unknown'}` : 'provider-loading'}`;
  providerModel.textContent = model || 'No model configured';
}

function renderSkills(skills) {
  if (!skills || !Object.keys(skills).length) {
    skillsOutput.innerHTML = '<div class="muted">No skills output yet.</div>';
    return;
  }

  skillsOutput.innerHTML = Object.entries(skills)
    .map(([category, items]) => `
      <div class="skill-row">
        <strong>${category}</strong><br />
        <span class="muted">${items}</span>
      </div>
    `)
    .join('');
}

function renderAudit(run) {
  const pills = [];
  const quality = run?.rulesAudit?.quality_gate || {};
  const layout = run?.layoutAudit || run?.rulesAudit?.layout_audit_summary;

  pills.push(`
    <div class="audit-pill ${quality.target_title_in_summary ? 'success' : 'danger'}">
      Title match: ${quality.target_title_in_summary ? 'pass' : 'fail'}
    </div>
  `);
  pills.push(`
    <div class="audit-pill ${quality.metric_ratio_ge_40pct ? 'success' : 'danger'}">
      Metric ratio: ${quality.metric_ratio_ge_40pct ? 'pass' : 'fail'}
    </div>
  `);
  pills.push(`
    <div class="audit-pill ${quality.page_budget_respected ? 'success' : 'danger'}">
      Page budget: ${quality.page_budget_respected ? 'pass' : 'fail'}
    </div>
  `);

  if (layout?.status) {
    const danger = layout.status === 'underfilled' || layout.status === 'overflow' || layout.status === 'dense';
    pills.push(`
      <div class="audit-pill ${danger ? 'danger' : 'success'}">
        Layout: ${layout.status}
      </div>
    `);
  }

  const extra = [];
  const droppedSkills = run?.rulesAudit?.enforcement?.dropped_skill_items || [];
  const trimmedCategories = run?.rulesAudit?.enforcement?.trimmed_skill_categories || [];

  if (droppedSkills.length) {
    extra.push(`<div class="muted"><strong>Dropped skill items:</strong><br />${droppedSkills.join('<br />')}</div>`);
  }
  if (trimmedCategories.length) {
    extra.push(`<div class="muted"><strong>Trimmed categories:</strong> ${trimmedCategories.join(', ')}</div>`);
  }

  auditOutput.innerHTML = `${pills.join(' ')} ${extra.join('')}`;
}

function applyRunToPreview(run) {
  previewTitle.textContent = `${run.metadata.company} — ${run.metadata.position}`;
  previewSubtitle.textContent = `${run.metadata.client_name} • latest draft`;
  summaryOutput.innerHTML = run.resume.summary || '<span class="muted">No summary returned.</span>';
  renderSkills(run.resume.skills);
  renderAudit(run);
  const cacheToken = run.runId || Date.now();
  pdfFrame.src = `${appendCacheBust(run.pdfUrl, cacheToken)}#toolbar=0&navpanes=0&scrollbar=1`;
  const filename = `${run.metadata.client_name}_${run.metadata.position}_Resume.pdf`.replace(/\s+/g, '_');
  enableExport(run.pdfUrl, run.downloadPdfUrl, filename, cacheToken);
  setStatus([
    'Done.',
    `Profile: ${run.metadata.client_name}`,
    `Role: ${run.metadata.position}`,
    `Model: ${run.metadata.llm_provider || 'unknown'}`,
    `Pages: ${run.metadata.page_budget}`,
    'Storage: session only',
  ].join('\n'));
}

function clearPreview(message = 'Nothing yet.') {
  previewTitle.textContent = 'Nothing yet';
  previewSubtitle.textContent = 'Your latest draft appears here.';
  summaryOutput.textContent = message;
  skillsOutput.innerHTML = '<div class="muted">Nothing generated yet.</div>';
  auditOutput.innerHTML = '<div class="muted">No audit output yet.</div>';
  pdfFrame.src = 'about:blank';
  disableExport();
}

function setFormEnabled(enabled) {
  clientSelect.disabled = !enabled;
  companyInput.disabled = !enabled;
  positionInput.disabled = !enabled;
  jdInput.disabled = !enabled;
  workRightsToggle.disabled = !enabled;
  generateButton.disabled = !enabled;
}

function describeAccess(user) {
  if (!user) return '';
  if (user.access.allClients) {
    return 'All profiles';
  }
  if (user.access.hasAssignedClients) {
    return `${user.access.assignedCount} profile${user.access.assignedCount === 1 ? '' : 's'}`;
  }
  return 'No profiles';
}

function renderUser(user) {
  authUser = user;
  currentUser.textContent = user.displayName;
  currentAccess.textContent = describeAccess(user);
}

function handleUnauthorized(response) {
  if (response.status === 401) {
    window.location.assign('/login');
    return true;
  }
  return false;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (handleUnauthorized(response)) {
    throw new Error('Authentication required.');
  }
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || 'Request failed.');
  }
  return data;
}

async function loadCurrentUser() {
  const data = await fetchJson('/api/auth/me');
  renderUser(data.user);
}

async function loadProviderStatus() {
  const data = await fetchJson('/api/provider');
  setProviderIndicator(data.provider, data.model, data.configured);
}

function renderClientList(clients, access) {
  cachedClients = clients || [];

  if (!cachedClients.length) {
    clientSelect.innerHTML = '<option value="">No assigned clients yet</option>';
    noClientsMessage.textContent = access.placeholderMessage || 'No profiles assigned.';
    noClientsCard.classList.remove('hidden');
    setFormEnabled(false);
    clearPreview('A draft appears here once a profile is assigned.');
    setStatus('No profiles assigned.');
    return;
  }

  noClientsCard.classList.add('hidden');
  clientSelect.innerHTML = cachedClients
    .map((client) => `<option value="${client.name}">${client.name} (${client.source})</option>`)
    .join('');
  setFormEnabled(true);
}

async function loadClients() {
  const data = await fetchJson('/api/clients');
  renderClientList(data.clients || [], {
    placeholderMessage: data.access?.placeholderMessage,
  });
}

async function initialize() {
  setStatus('Loading…');
  disableExport();
  clearPreview();

  try {
    await loadCurrentUser();
    await Promise.all([loadClients(), loadProviderStatus()]);
    if (cachedClients.length) {
      setStatus(`Ready. ${cachedClients.length} profile${cachedClients.length === 1 ? '' : 's'}.`);
    }
  } catch (error) {
    if (error.message !== 'Authentication required.') {
      setStatus(`Could not load.\n${error.message}`);
    }
  }
}

async function handleGenerate(event) {
  event.preventDefault();
  disableExport();
  generateButton.disabled = true;
  generateButton.textContent = 'Generating…';
  setStatus('Generating…');
  previewTitle.textContent = 'Generating…';
  previewSubtitle.textContent = `${clientSelect.value} → ${positionInput.value || 'Untitled role'}`;
  pdfFrame.src = 'about:blank';

  const payload = {
    clientName: clientSelect.value,
    company: companyInput.value.trim(),
    position: positionInput.value.trim(),
    jdText: jdInput.value.trim(),
    displayWorkAuthorization: workRightsToggle.checked,
  };

  try {
    const data = await fetchJson('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    applyRunToPreview(data.run);
  } catch (error) {
    if (error.message === 'Authentication required.') return;
    previewTitle.textContent = 'Failed';
    previewSubtitle.textContent = 'See status.';
    summaryOutput.textContent = 'Nothing to show yet.';
    skillsOutput.innerHTML = '<div class="muted">No skills output yet.</div>';
    auditOutput.innerHTML = `<div class="audit-pill danger">${error.message}</div>`;
    setStatus(`Failed.\n${error.message}`);
  } finally {
    generateButton.disabled = !cachedClients.length;
    generateButton.textContent = 'Generate resume';
  }
}

async function handleLogout() {
  logoutButton.disabled = true;
  try {
    await fetchJson('/api/auth/logout', { method: 'POST' });
  } catch (error) {
    if (error.message !== 'Authentication required.') {
      setStatus(`Sign out failed.\n${error.message}`);
      logoutButton.disabled = false;
      return;
    }
  }
  window.location.assign('/login');
}

form.addEventListener('submit', handleGenerate);
logoutButton.addEventListener('click', handleLogout);
initialize();
