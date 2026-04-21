const express = require('express');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const os = require('os');
const { execFile } = require('child_process');
const { promisify } = require('util');

const execFileAsync = promisify(execFile);
const app = express();
const PORT = Number(process.env.PORT || 4311);

const HOME = os.homedir();
const APP_ROOT = __dirname;
const ENGINE_ROOT = path.join(APP_ROOT, 'engine');
const ENGINE_SCRIPT = path.join(ENGINE_ROOT, 'run_resume_engine.py');
const CLIENTS_DIR = path.join(APP_ROOT, 'data', 'clients');
const ENV_FILE = path.join(APP_ROOT, '.env');

let currentRun = null;

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const env = {};
  const content = fs.readFileSync(filePath, 'utf8');
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eqIndex = line.indexOf('=');
    if (eqIndex === -1) continue;
    const key = line.slice(0, eqIndex).trim();
    let value = line.slice(eqIndex + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

const fileEnv = loadEnvFile(ENV_FILE);
for (const [key, value] of Object.entries(fileEnv)) {
  if (!process.env[key]) process.env[key] = value;
}

app.use(express.json({ limit: '5mb' }));
app.use(express.static(path.join(APP_ROOT, 'public')));

function slugify(value) {
  return String(value || '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

async function exists(filePath) {
  try {
    await fsp.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function readJson(filePath) {
  return JSON.parse(await fsp.readFile(filePath, 'utf8'));
}

function providerState() {
  const openaiModel = (process.env.OPENAI_MODEL || 'gpt-4.1-mini').trim();
  const geminiModel = (process.env.GEMINI_MODEL || 'gemini-2.5-flash').trim();
  const openaiApiKey = (process.env.OPENAI_API_KEY || '').trim();
  const geminiApiKey = (process.env.GEMINI_API_KEY || '').trim();

  if (openaiApiKey) {
    return {
      configured: true,
      provider: 'openai',
      providerLabel: 'GPT',
      model: openaiModel,
      openaiApiKey,
      geminiApiKey,
      openaiModel,
      geminiModel,
    };
  }

  if (geminiApiKey) {
    return {
      configured: true,
      provider: 'gemini',
      providerLabel: 'Gemini',
      model: geminiModel,
      openaiApiKey,
      geminiApiKey,
      openaiModel,
      geminiModel,
    };
  }

  return {
    configured: false,
    provider: null,
    providerLabel: 'Unavailable',
    model: 'No API key found in .env',
    openaiApiKey,
    geminiApiKey,
    openaiModel,
    geminiModel,
  };
}

async function listClients() {
  if (!(await exists(CLIENTS_DIR))) {
    return [];
  }

  const entries = await fsp.readdir(CLIENTS_DIR, { withFileTypes: true });
  const clients = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const profileFile = path.join(CLIENTS_DIR, entry.name, 'master_profile.json');
    if (!(await exists(profileFile))) continue;
    try {
      const profile = await readJson(profileFile);
      const clientName = profile?.client?.name || entry.name;
      clients.push({
        id: slugify(clientName),
        name: clientName,
        profileFile,
        source: 'bundled'
      });
    } catch {
      // ignore unreadable profile
    }
  }

  return clients.sort((a, b) => a.name.localeCompare(b.name));
}

function extractRunDir(stdout) {
  const lines = String(stdout || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i];
    if (line.startsWith('/') && fs.existsSync(line)) {
      return line;
    }
  }

  throw new Error('Could not determine run directory from generator output.');
}

function sanitizeFilenamePart(value) {
  return String(value || '')
    .replace(/[\\/:*?"<>|]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildResumeFilename(run, ext = 'pdf') {
  const client = sanitizeFilenamePart(run?.metadata?.client_name || 'Candidate').replace(/\s+/g, '_');
  const position = sanitizeFilenamePart(run?.metadata?.position || 'Position').replace(/\s+/g, '_');
  return `${client}_${position}_Resume.${ext}`;
}

function currentArtifactUrls() {
  return {
    pdfUrl: '/current-run/resume.pdf',
    downloadPdfUrl: '/current-run/resume.download',
    resumeJsonUrl: '/current-run/resume.json',
    metadataUrl: '/current-run/metadata.json',
    rulesAuditUrl: '/current-run/rules_audit.json',
    layoutAuditUrl: '/current-run/layout_audit.json',
    vaNotesUrl: '/current-run/va_notes.md'
  };
}

async function loadRunBundle(runDir, tempRoot) {
  const metadata = await readJson(path.join(runDir, 'metadata.json'));
  const resume = await readJson(path.join(runDir, 'resume.json'));
  let rulesAudit = null;
  let layoutAudit = null;

  const rulesAuditPath = path.join(runDir, 'rules_audit.json');
  const layoutAuditPath = path.join(runDir, 'layout_audit.json');

  if (await exists(rulesAuditPath)) {
    rulesAudit = await readJson(rulesAuditPath);
  }
  if (await exists(layoutAuditPath)) {
    layoutAudit = await readJson(layoutAuditPath);
  }

  return {
    ...currentArtifactUrls(),
    runId: path.basename(runDir),
    runDir,
    tempRoot,
    metadata,
    resume,
    rulesAudit,
    layoutAudit,
  };
}

async function cleanupCurrentRun() {
  if (!currentRun?.tempRoot) return;
  const tempRoot = currentRun.tempRoot;
  currentRun = null;
  await fsp.rm(tempRoot, { recursive: true, force: true }).catch(() => {});
}

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, app: 'ccc-resume-studio-lite' });
});

app.get('/api/clients', async (_req, res) => {
  try {
    const clients = await listClients();
    res.json({ clients });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/provider', (_req, res) => {
  const state = providerState();
  if (!state.configured) {
    return res.status(400).json({
      configured: false,
      provider: null,
      providerLabel: 'Unavailable',
      model: 'No API key found in .env',
      error: 'No API key found. Set OPENAI_API_KEY or GEMINI_API_KEY in ccc-resume-studio-lite/.env.'
    });
  }

  return res.json({
    configured: true,
    provider: state.provider,
    providerLabel: state.providerLabel,
    model: state.model,
  });
});

app.get('/api/current-run', (_req, res) => {
  if (!currentRun) {
    return res.status(404).json({ error: 'No current run loaded.' });
  }
  res.json({ run: currentRun });
});

app.get('/current-run/:artifact', async (req, res) => {
  res.set({
    'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
    'Pragma': 'no-cache',
    'Expires': '0',
    'Surrogate-Control': 'no-store'
  });

  if (!currentRun) {
    return res.status(404).send('No current run loaded.');
  }

  const artifactMap = {
    'resume.pdf': 'resume.pdf',
    'resume.download': 'resume.pdf',
    'resume.json': 'resume.json',
    'metadata.json': 'metadata.json',
    'rules_audit.json': 'rules_audit.json',
    'layout_audit.json': 'layout_audit.json',
    'va_notes.md': 'va_notes.md',
  };

  const artifact = req.params.artifact;
  const mappedArtifact = artifactMap[artifact];
  if (!mappedArtifact) {
    return res.status(404).send('Unknown artifact.');
  }

  const artifactPath = path.join(currentRun.runDir, mappedArtifact);
  if (!(await exists(artifactPath))) {
    return res.status(404).send('Artifact not found.');
  }

  if (artifact === 'resume.download') {
    return res.download(artifactPath, buildResumeFilename(currentRun, 'pdf'));
  }

  res.sendFile(artifactPath);
});

app.post('/api/generate', async (req, res) => {
  const { clientName, company, position, jdText, llmAgent } = req.body || {};

  if (!clientName || !company || !position || !jdText) {
    return res.status(400).json({
      error: 'clientName, company, position, and jdText are required.'
    });
  }

  const state = providerState();
  if (!state.configured) {
    return res.status(400).json({
      error: 'No API key found. Set OPENAI_API_KEY or GEMINI_API_KEY in ccc-resume-studio-lite/.env.'
    });
  }

  let tempRoot = null;

  try {
    const clients = await listClients();
    const client = clients.find((item) => item.name === clientName);

    if (!client) {
      return res.status(404).json({ error: `Unknown client: ${clientName}` });
    }

    tempRoot = await fsp.mkdtemp(path.join(os.tmpdir(), 'ccc-resume-studio-lite-'));
    const tempInputsDir = path.join(tempRoot, 'inputs');
    const tempRunsDir = path.join(tempRoot, 'runs');
    await fsp.mkdir(tempInputsDir, { recursive: true });
    await fsp.mkdir(tempRunsDir, { recursive: true });

    const jobFile = path.join(tempInputsDir, `${slugify(clientName)}_${slugify(company)}_${slugify(position)}.json`);
    const jobPayload = {
      job_id: `lite-${slugify(company)}-${slugify(position)}-${Date.now()}`,
      Name: company,
      Status: 'ad_hoc_ui',
      URL: '',
      position,
      note: 'Created from CCC Resume Studio Lite UI.',
      jd_text: jdText,
      searched_at: new Date().toISOString(),
      source_query: 'ui-manual-input-lite'
    };
    await fsp.writeFile(jobFile, `${JSON.stringify(jobPayload, null, 2)}\n`, 'utf8');

    const args = [
      ENGINE_SCRIPT,
      '--client-name', client.name,
      '--profile-file', client.profileFile,
      '--job-file', jobFile,
      '--output-dir', tempRunsDir,
      '--llm-provider', state.provider,
      '--openai-model', state.openaiModel,
      '--gemini-model', state.geminiModel,
      '--llm-agent', llmAgent || 'samantha'
    ];

    const { stdout, stderr } = await execFileAsync('python3', args, {
      cwd: ENGINE_ROOT,
      maxBuffer: 10 * 1024 * 1024,
      timeout: 20 * 60 * 1000,
      env: {
        ...process.env,
        OPENAI_API_KEY: state.openaiApiKey,
        OPENAI_MODEL: state.openaiModel,
        GEMINI_API_KEY: state.geminiApiKey,
        GEMINI_MODEL: state.geminiModel
      }
    });

    const runDir = extractRunDir(stdout);
    const run = await loadRunBundle(runDir, tempRoot);

    await cleanupCurrentRun();
    currentRun = run;

    return res.json({
      ok: true,
      client,
      stdout,
      stderr,
      run
    });
  } catch (error) {
    if (tempRoot) {
      await fsp.rm(tempRoot, { recursive: true, force: true }).catch(() => {});
    }
    const stderr = error?.stderr ? String(error.stderr) : '';
    const stdout = error?.stdout ? String(error.stdout) : '';
    return res.status(500).json({
      error: error.message,
      stdout,
      stderr
    });
  }
});

app.get('*', (_req, res) => {
  res.sendFile(path.join(APP_ROOT, 'public', 'index.html'));
});

async function shutdown() {
  await cleanupCurrentRun();
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

app.listen(PORT, () => {
  console.log(`CCC Resume Studio Lite running at http://localhost:${PORT}`);
});
