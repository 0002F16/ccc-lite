const form = document.getElementById('generate-form');
const clientSelect = document.getElementById('client-select');
const companyInput = document.getElementById('company-input');
const positionInput = document.getElementById('position-input');
const jdInput = document.getElementById('jd-input');
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

let cachedClients = [];

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
  previewSubtitle.textContent = `${run.metadata.client_name} • current in-memory run`;
  summaryOutput.innerHTML = run.resume.summary || '<span class="muted">No summary returned.</span>';
  renderSkills(run.resume.skills);
  renderAudit(run);
  const cacheToken = run.runId || Date.now();
  pdfFrame.src = `${appendCacheBust(run.pdfUrl, cacheToken)}#toolbar=0&navpanes=0&scrollbar=1`;
  const filename = `${run.metadata.client_name}_${run.metadata.position}_Resume.pdf`.replace(/\s+/g, '_');
  enableExport(run.pdfUrl, run.downloadPdfUrl, filename, cacheToken);
  setStatus([
    'Generated current run.',
    `Client: ${run.metadata.client_name}`,
    `Position: ${run.metadata.position}`,
    `Provider: ${run.metadata.llm_provider || 'unknown'}`,
    `Page budget: ${run.metadata.page_budget}`,
    'Persistence: temp-only while server is running'
  ].join('\n'));
}

async function loadProviderStatus() {
  const response = await fetch('/api/provider');
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || 'Failed to load provider status');
  }
  setProviderIndicator(data.provider, data.model, data.configured);
}

async function loadClients() {
  const response = await fetch('/api/clients');
  const data = await response.json();
  cachedClients = data.clients || [];
  clientSelect.innerHTML = cachedClients
    .map((client) => `<option value="${client.name}">${client.name} (${client.source})</option>`)
    .join('');
}

async function initialize() {
  setStatus('Loading clients and provider status…');
  disableExport();
  try {
    await Promise.all([loadClients(), loadProviderStatus()]);
    setStatus(`Ready. ${cachedClients.length} clients loaded. This lite app keeps only the current run in memory.`);
  } catch (error) {
    setStatus(`Failed to initialize.\n${error.message}`);
  }
}

async function handleGenerate(event) {
  event.preventDefault();
  disableExport();
  generateButton.disabled = true;
  generateButton.textContent = 'Generating…';
  setStatus(`Generating resume with ${providerModel.textContent || 'configured model'}…\nThis can take a minute or two.`);
  previewTitle.textContent = 'Generating…';
  previewSubtitle.textContent = `${clientSelect.value} → ${positionInput.value || 'Untitled role'}`;
  pdfFrame.src = 'about:blank';

  const payload = {
    clientName: clientSelect.value,
    company: companyInput.value.trim(),
    position: positionInput.value.trim(),
    jdText: jdInput.value.trim()
  };

  try {
    const response = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Generation failed');
    }

    applyRunToPreview(data.run);
  } catch (error) {
    previewTitle.textContent = 'Generation failed';
    previewSubtitle.textContent = 'See run status for details.';
    summaryOutput.textContent = 'No preview available.';
    skillsOutput.innerHTML = '<div class="muted">No skills output yet.</div>';
    auditOutput.innerHTML = `<div class="audit-pill danger">${error.message}</div>`;
    setStatus(`Generation failed.\n${error.message}`);
  } finally {
    generateButton.disabled = false;
    generateButton.textContent = 'Generate resume';
  }
}

form.addEventListener('submit', handleGenerate);
initialize();
