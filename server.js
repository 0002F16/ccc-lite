const express = require('express');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const { execFile } = require('child_process');
const { promisify } = require('util');

const execFileAsync = promisify(execFile);
const app = express();
const PORT = Number(process.env.PORT || 4311);

const APP_ROOT = __dirname;
const ENGINE_ROOT = path.join(APP_ROOT, 'engine');
const ENGINE_SCRIPT = path.join(ENGINE_ROOT, 'run_resume_engine.py');
const CLIENTS_DIR = path.join(APP_ROOT, 'data', 'clients');
const ACCESS_MODEL_FILE = path.join(APP_ROOT, 'data', 'access', 'users.json');
const APP_DATA_DIR = path.join(APP_ROOT, 'app-data');
const AUTH_DIR = path.join(APP_DATA_DIR, 'auth');
const USERS_FILE = path.join(AUTH_DIR, 'users.json');
const SESSIONS_FILE = path.join(AUTH_DIR, 'sessions.json');
const SESSION_SECRET_FILE = path.join(AUTH_DIR, 'session-secret');
const ENV_FILE = path.join(APP_ROOT, '.env');
const REQUIREMENTS_FILE = path.join(APP_ROOT, 'requirements.txt');
const PYTHON_VENV_DIR = path.join(APP_ROOT, '.venv');
const PYTHON_VENV_BIN_DIR = process.platform === 'win32'
  ? path.join(PYTHON_VENV_DIR, 'Scripts')
  : path.join(PYTHON_VENV_DIR, 'bin');
const PYTHON_RUNTIME = process.platform === 'win32'
  ? path.join(PYTHON_VENV_BIN_DIR, 'python.exe')
  : path.join(PYTHON_VENV_BIN_DIR, 'python3');
const SESSION_COOKIE_NAME = 'ccc_resume_session';
const SESSION_MAX_AGE_MS = Number(process.env.SESSION_MAX_AGE_DAYS || 30) * 24 * 60 * 60 * 1000;
const PASSWORD_ITERATIONS = 210000;
const PASSWORD_KEYLEN = 32;
const PASSWORD_DIGEST = 'sha256';
const FALLBACK_PASSWORD_HASH = (() => {
  const salt = '00000000000000000000000000000000';
  const derivedKey = crypto.pbkdf2Sync('ccc-resume-studio-lite-fallback', salt, PASSWORD_ITERATIONS, PASSWORD_KEYLEN, PASSWORD_DIGEST);
  return `pbkdf2$${PASSWORD_ITERATIONS}$${salt}$${derivedKey.toString('hex')}`;
})();

let currentRun = null;
let pythonBootstrapPromise = null;
let authBootstrapPromise = null;
let sessionSecret = null;

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

async function writeJson(filePath, value) {
  await fsp.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

function pythonPathEnv() {
  const current = process.env.PATH || '';
  return `${PYTHON_VENV_BIN_DIR}${path.delimiter}${current}`;
}

function cookieSecureMode() {
  return String(process.env.SESSION_COOKIE_SECURE || 'auto').trim().toLowerCase();
}

function isSecureRequest(req) {
  if (req.secure) return true;
  const forwardedProto = String(req.headers['x-forwarded-proto'] || '').split(',')[0].trim().toLowerCase();
  return forwardedProto === 'https';
}

function shouldUseSecureCookie(req) {
  const mode = cookieSecureMode();
  if (mode === 'true' || mode === 'always') return true;
  if (mode === 'false' || mode === 'never') return false;
  return isSecureRequest(req);
}

function serializeCookie(name, value, options = {}) {
  const parts = [`${name}=${value}`];
  if (options.maxAge !== undefined) {
    parts.push(`Max-Age=${Math.max(0, Math.floor(options.maxAge))}`);
  }
  if (options.expires) {
    parts.push(`Expires=${options.expires.toUTCString()}`);
  }
  parts.push(`Path=${options.path || '/'}`);
  if (options.httpOnly) parts.push('HttpOnly');
  if (options.sameSite) parts.push(`SameSite=${options.sameSite}`);
  if (options.secure) parts.push('Secure');
  return parts.join('; ');
}

function setSessionCookie(req, res, sessionValue, expiresAt) {
  res.setHeader('Set-Cookie', serializeCookie(SESSION_COOKIE_NAME, sessionValue, {
    httpOnly: true,
    sameSite: 'Lax',
    secure: shouldUseSecureCookie(req),
    path: '/',
    maxAge: Math.max(0, Math.floor((expiresAt - Date.now()) / 1000)),
    expires: new Date(expiresAt),
  }));
}

function clearSessionCookie(req, res) {
  res.setHeader('Set-Cookie', serializeCookie(SESSION_COOKIE_NAME, '', {
    httpOnly: true,
    sameSite: 'Lax',
    secure: shouldUseSecureCookie(req),
    path: '/',
    maxAge: 0,
    expires: new Date(0),
  }));
}

function parseCookies(req) {
  const header = req.headers.cookie || '';
  const cookies = {};
  for (const chunk of header.split(';')) {
    const trimmed = chunk.trim();
    if (!trimmed) continue;
    const eqIndex = trimmed.indexOf('=');
    if (eqIndex === -1) continue;
    const key = trimmed.slice(0, eqIndex).trim();
    const value = trimmed.slice(eqIndex + 1).trim();
    cookies[key] = decodeURIComponent(value);
  }
  return cookies;
}

function safeCompareString(left, right) {
  const leftBuffer = Buffer.from(String(left || ''), 'utf8');
  const rightBuffer = Buffer.from(String(right || ''), 'utf8');
  if (leftBuffer.length !== rightBuffer.length) return false;
  return crypto.timingSafeEqual(leftBuffer, rightBuffer);
}

function hashPassword(password, salt = crypto.randomBytes(16).toString('hex')) {
  const derivedKey = crypto.pbkdf2Sync(String(password), salt, PASSWORD_ITERATIONS, PASSWORD_KEYLEN, PASSWORD_DIGEST);
  return `pbkdf2$${PASSWORD_ITERATIONS}$${salt}$${derivedKey.toString('hex')}`;
}

function verifyPassword(password, passwordHash) {
  if (!passwordHash) return false;
  const parts = String(passwordHash).split('$');
  if (parts.length !== 4 || parts[0] !== 'pbkdf2') return false;
  const iterations = Number(parts[1]);
  const salt = parts[2];
  const expectedHex = parts[3];
  if (!iterations || !salt || !expectedHex) return false;
  const actual = crypto.pbkdf2Sync(String(password), salt, iterations, PASSWORD_KEYLEN, PASSWORD_DIGEST).toString('hex');
  return safeCompareString(actual, expectedHex);
}

function signSessionId(secret, sessionId) {
  return crypto.createHmac('sha256', secret).update(sessionId).digest('base64url');
}

function encodeSessionCookie(secret, sessionId) {
  return `${sessionId}.${signSessionId(secret, sessionId)}`;
}

function decodeSessionCookie(secret, cookieValue) {
  const token = String(cookieValue || '');
  const dotIndex = token.indexOf('.');
  if (dotIndex === -1) return null;
  const sessionId = token.slice(0, dotIndex);
  const signature = token.slice(dotIndex + 1);
  if (!/^[a-f0-9]{64}$/.test(sessionId)) return null;
  const expectedSignature = signSessionId(secret, sessionId);
  if (!safeCompareString(signature, expectedSignature)) return null;
  return sessionId;
}

async function ensureJsonFile(filePath, defaultValue) {
  if (await exists(filePath)) return;
  await writeJson(filePath, defaultValue);
}

function toUsersMap(state) {
  const map = new Map();
  for (const user of state.users || []) {
    map.set(user.username, user);
  }
  return map;
}

function envPasswordForUser(username) {
  const key = `${String(username || '').toUpperCase()}_PASSWORD`;
  return String(process.env[key] || '').trim();
}

async function loadAccessModel() {
  const raw = await readJson(ACCESS_MODEL_FILE);
  const users = Array.isArray(raw.users) ? raw.users : [];
  return {
    users,
    byUsername: new Map(users.map((user) => [user.username, user])),
  };
}

async function bootstrapUsersStateIfNeeded(accessModel) {
  const nowIso = new Date().toISOString();

  if (!(await exists(USERS_FILE))) {
    const users = accessModel.users.map((accessUser) => {
      const password = envPasswordForUser(accessUser.username);
      return {
        username: accessUser.username,
        passwordHash: password ? hashPassword(password) : null,
        passwordUpdatedAt: password ? nowIso : null,
      };
    });

    await writeJson(USERS_FILE, {
      version: 1,
      users,
    });
    return;
  }

  const state = await readJson(USERS_FILE).catch(() => ({ version: 1, users: [] }));
  const userMap = toUsersMap(state);
  let changed = false;

  for (const accessUser of accessModel.users) {
    const existing = userMap.get(accessUser.username);
    const envPassword = envPasswordForUser(accessUser.username);

    if (!existing) {
      state.users.push({
        username: accessUser.username,
        passwordHash: envPassword ? hashPassword(envPassword) : null,
        passwordUpdatedAt: envPassword ? nowIso : null,
      });
      changed = true;
      continue;
    }

    if (!existing.passwordHash && envPassword) {
      existing.passwordHash = hashPassword(envPassword);
      existing.passwordUpdatedAt = nowIso;
      changed = true;
    }
  }

  if (changed) {
    await writeJson(USERS_FILE, {
      version: 1,
      users: state.users,
    });
  }
}

async function ensureAuthBootstrap() {
  if (authBootstrapPromise) return authBootstrapPromise;

  authBootstrapPromise = (async () => {
    const accessModel = await loadAccessModel();
    await fsp.mkdir(AUTH_DIR, { recursive: true });
    await ensureJsonFile(SESSIONS_FILE, { version: 1, sessions: {} });
    await bootstrapUsersStateIfNeeded(accessModel);

    if (process.env.SESSION_SECRET) {
      sessionSecret = process.env.SESSION_SECRET.trim();
    } else if (await exists(SESSION_SECRET_FILE)) {
      sessionSecret = (await fsp.readFile(SESSION_SECRET_FILE, 'utf8')).trim();
    } else {
      sessionSecret = crypto.randomBytes(32).toString('base64url');
      await fsp.writeFile(SESSION_SECRET_FILE, `${sessionSecret}\n`, 'utf8');
    }

    if (!sessionSecret) {
      throw new Error('Session secret could not be initialized.');
    }
  })().catch((error) => {
    authBootstrapPromise = null;
    throw error;
  });

  return authBootstrapPromise;
}

async function loadUsersState() {
  await ensureAuthBootstrap();
  const state = await readJson(USERS_FILE);
  if (!Array.isArray(state.users)) {
    return { version: 1, users: [] };
  }
  return state;
}

async function loadSessionsState() {
  await ensureAuthBootstrap();
  const state = await readJson(SESSIONS_FILE);
  if (!state.sessions || typeof state.sessions !== 'object') {
    return { version: 1, sessions: {} };
  }
  return state;
}

async function saveSessionsState(state) {
  await ensureAuthBootstrap();
  await writeJson(SESSIONS_FILE, state);
}

async function cleanupSessionsState(state, accessModel) {
  const now = Date.now();
  let changed = false;
  for (const [sessionId, session] of Object.entries(state.sessions || {})) {
    const user = accessModel.byUsername.get(session?.username);
    const isExpired = !session?.expiresAt || Number.isNaN(Date.parse(session.expiresAt)) || Date.parse(session.expiresAt) <= now;
    if (!user || isExpired) {
      delete state.sessions[sessionId];
      changed = true;
    }
  }
  if (changed) {
    await saveSessionsState(state);
  }
  return state;
}

async function bootstrapPythonRuntime() {
  if (pythonBootstrapPromise) return pythonBootstrapPromise;

  pythonBootstrapPromise = (async () => {
    if (!(await exists(REQUIREMENTS_FILE))) {
      throw new Error('Missing requirements.txt for Python runtime bootstrap.');
    }

    if (!(await exists(PYTHON_RUNTIME))) {
      await execFileAsync('python3', ['-m', 'venv', PYTHON_VENV_DIR], {
        cwd: APP_ROOT,
        maxBuffer: 10 * 1024 * 1024,
      });
    }

    await execFileAsync(PYTHON_RUNTIME, ['-m', 'pip', 'install', '--upgrade', 'pip'], {
      cwd: APP_ROOT,
      maxBuffer: 10 * 1024 * 1024,
      env: {
        ...process.env,
        PATH: pythonPathEnv(),
      },
    });

    await execFileAsync(PYTHON_RUNTIME, ['-m', 'pip', 'install', '-r', REQUIREMENTS_FILE], {
      cwd: APP_ROOT,
      maxBuffer: 20 * 1024 * 1024,
      env: {
        ...process.env,
        PATH: pythonPathEnv(),
      },
    });
  })().catch((error) => {
    pythonBootstrapPromise = null;
    throw error;
  });

  return pythonBootstrapPromise;
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
        source: 'bundled',
      });
    } catch {
      // ignore unreadable profile
    }
  }

  return clients.sort((a, b) => a.name.localeCompare(b.name));
}

function filterClientsForAccess(clients, access) {
  if (!access) return [];
  if (access.scope === 'all-clients') return clients;
  const allowed = new Set(access.clientIds || []);
  return clients.filter((client) => allowed.has(client.id));
}

function buildAuthUser(accessUser, clients) {
  const assignedClients = filterClientsForAccess(clients, accessUser);
  return {
    username: accessUser.username,
    displayName: accessUser.displayName || accessUser.username,
    role: accessUser.role || 'user',
    access: {
      scope: accessUser.scope,
      clientIds: accessUser.clientIds || [],
      assignedCount: assignedClients.length,
      allClients: accessUser.scope === 'all-clients',
      hasAssignedClients: assignedClients.length > 0,
      placeholderMessage: accessUser.placeholderMessage || '',
    },
  };
}

function canAccessClient(accessUser, clientId) {
  if (!accessUser) return false;
  if (accessUser.scope === 'all-clients') return true;
  return (accessUser.clientIds || []).includes(clientId);
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
    vaNotesUrl: '/current-run/va_notes.md',
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

function canAccessCurrentRun(accessUser) {
  if (!currentRun || !accessUser) return false;
  return canAccessClient(accessUser, currentRun.clientId || slugify(currentRun?.metadata?.client_name));
}

function serveFile(filePath) {
  return (_req, res) => {
    res.sendFile(filePath);
  };
}

function respondUnauthorized(req, res) {
  if (req.originalUrl.startsWith('/api/')) {
    return res.status(401).json({ error: 'Authentication required.' });
  }
  return res.redirect('/login');
}

async function attachAuthenticatedUser(req, res, next) {
  try {
    await ensureAuthBootstrap();
    const cookies = parseCookies(req);
    const rawCookie = cookies[SESSION_COOKIE_NAME];
    if (!rawCookie) {
      req.authUser = null;
      return next();
    }

    const sessionId = decodeSessionCookie(sessionSecret, rawCookie);
    if (!sessionId) {
      clearSessionCookie(req, res);
      req.authUser = null;
      return next();
    }

    const [accessModel, sessionsState] = await Promise.all([loadAccessModel(), loadSessionsState()]);
    await cleanupSessionsState(sessionsState, accessModel);
    const session = sessionsState.sessions[sessionId];

    if (!session) {
      clearSessionCookie(req, res);
      req.authUser = null;
      return next();
    }

    const accessUser = accessModel.byUsername.get(session.username);
    if (!accessUser) {
      delete sessionsState.sessions[sessionId];
      await saveSessionsState(sessionsState);
      clearSessionCookie(req, res);
      req.authUser = null;
      return next();
    }

    const clients = await listClients();
    const refreshedExpiry = new Date(Date.now() + SESSION_MAX_AGE_MS).toISOString();
    sessionsState.sessions[sessionId] = {
      ...session,
      lastSeenAt: new Date().toISOString(),
      expiresAt: refreshedExpiry,
    };
    await saveSessionsState(sessionsState);
    setSessionCookie(req, res, encodeSessionCookie(sessionSecret, sessionId), Date.parse(refreshedExpiry));

    req.authUser = buildAuthUser(accessUser, clients);
    next();
  } catch (error) {
    next(error);
  }
}

function requireAuth(req, res, next) {
  if (!req.authUser) {
    return respondUnauthorized(req, res);
  }
  return next();
}

function redirectIfAuthenticated(req, res, next) {
  if (req.authUser) {
    return res.redirect('/');
  }
  return next();
}

app.use(attachAuthenticatedUser);

app.get('/styles.css', serveFile(path.join(APP_ROOT, 'public', 'styles.css')));
app.get('/login.js', serveFile(path.join(APP_ROOT, 'public', 'login.js')));
app.get('/login', redirectIfAuthenticated, serveFile(path.join(APP_ROOT, 'public', 'login.html')));

app.post('/api/auth/login', async (req, res) => {
  const username = String(req.body?.username || '').trim().toLowerCase();
  const password = String(req.body?.password || '');

  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password are required.' });
  }

  try {
    const [accessModel, usersState, sessionsState, clients] = await Promise.all([
      loadAccessModel(),
      loadUsersState(),
      loadSessionsState(),
      listClients(),
    ]);
    await cleanupSessionsState(sessionsState, accessModel);

    const accessUser = accessModel.byUsername.get(username);
    const userRecord = toUsersMap(usersState).get(username);

    const passwordOk = verifyPassword(password, userRecord?.passwordHash || FALLBACK_PASSWORD_HASH);
    if (!accessUser || !userRecord?.passwordHash || !passwordOk) {
      return res.status(401).json({ error: 'Invalid username or password.' });
    }

    const sessionId = crypto.randomBytes(32).toString('hex');
    const expiresAt = new Date(Date.now() + SESSION_MAX_AGE_MS).toISOString();
    sessionsState.sessions[sessionId] = {
      username,
      createdAt: new Date().toISOString(),
      lastSeenAt: new Date().toISOString(),
      expiresAt,
    };
    await saveSessionsState(sessionsState);
    setSessionCookie(req, res, encodeSessionCookie(sessionSecret, sessionId), Date.parse(expiresAt));

    return res.json({
      ok: true,
      user: buildAuthUser(accessUser, clients),
    });
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
});

app.post('/api/auth/logout', requireAuth, async (req, res) => {
  try {
    const cookies = parseCookies(req);
    const sessionId = decodeSessionCookie(sessionSecret, cookies[SESSION_COOKIE_NAME]);
    if (sessionId) {
      const sessionsState = await loadSessionsState();
      if (sessionsState.sessions[sessionId]) {
        delete sessionsState.sessions[sessionId];
        await saveSessionsState(sessionsState);
      }
    }
    clearSessionCookie(req, res);
    return res.json({ ok: true });
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
});

app.get('/api/auth/me', requireAuth, async (req, res) => {
  res.json({ user: req.authUser });
});

app.use('/api', requireAuth);

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, app: 'ccc-resume-studio-lite' });
});

app.get('/api/clients', async (req, res) => {
  try {
    const [accessModel, clients] = await Promise.all([loadAccessModel(), listClients()]);
    const accessUser = accessModel.byUsername.get(req.authUser.username);
    const visibleClients = filterClientsForAccess(clients, accessUser);
    res.json({
      clients: visibleClients,
      access: req.authUser.access,
    });
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
      error: 'No API key found. Set OPENAI_API_KEY or GEMINI_API_KEY in ccc-resume-studio-lite/.env.',
    });
  }

  return res.json({
    configured: true,
    provider: state.provider,
    providerLabel: state.providerLabel,
    model: state.model,
  });
});

app.get('/api/current-run', async (req, res) => {
  try {
    const accessModel = await loadAccessModel();
    const accessUser = accessModel.byUsername.get(req.authUser.username);
    if (!currentRun || !canAccessCurrentRun(accessUser)) {
      return res.status(404).json({ error: 'No current run loaded.' });
    }
    return res.json({ run: currentRun });
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
});

app.get('/current-run/:artifact', requireAuth, async (req, res) => {
  res.set({
    'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
    Pragma: 'no-cache',
    Expires: '0',
    'Surrogate-Control': 'no-store',
  });

  try {
    const accessModel = await loadAccessModel();
    const accessUser = accessModel.byUsername.get(req.authUser.username);
    if (!currentRun || !canAccessCurrentRun(accessUser)) {
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

    return res.sendFile(artifactPath);
  } catch (error) {
    return res.status(500).send(error.message);
  }
});

app.post('/api/generate', async (req, res) => {
  const {
    clientName,
    company,
    position,
    jdText,
    llmAgent,
    displayWorkAuthorization,
  } = req.body || {};

  if (!clientName || !company || !position || !jdText) {
    return res.status(400).json({
      error: 'clientName, company, position, and jdText are required.',
    });
  }

  const state = providerState();
  if (!state.configured) {
    return res.status(400).json({
      error: 'No API key found. Set OPENAI_API_KEY or GEMINI_API_KEY in ccc-resume-studio-lite/.env.',
    });
  }

  let tempRoot = null;

  try {
    const [accessModel, clients] = await Promise.all([loadAccessModel(), listClients()]);
    const accessUser = accessModel.byUsername.get(req.authUser.username);
    const client = clients.find((item) => item.name === clientName);

    if (!client) {
      return res.status(404).json({ error: `Unknown client: ${clientName}` });
    }

    if (!canAccessClient(accessUser, client.id)) {
      return res.status(403).json({ error: `Access denied for client: ${clientName}` });
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
      source_query: 'ui-manual-input-lite',
    };
    await fsp.writeFile(jobFile, `${JSON.stringify(jobPayload, null, 2)}\n`, 'utf8');

    await bootstrapPythonRuntime();

    const args = [
      ENGINE_SCRIPT,
      '--client-name', client.name,
      '--profile-file', client.profileFile,
      '--job-file', jobFile,
      '--output-dir', tempRunsDir,
      '--llm-provider', state.provider,
      '--openai-model', state.openaiModel,
      '--gemini-model', state.geminiModel,
      '--llm-agent', llmAgent || 'samantha',
    ];

    if (displayWorkAuthorization === false) {
      args.push('--hide-work-authorization');
    }

    const { stdout, stderr } = await execFileAsync(PYTHON_RUNTIME, args, {
      cwd: ENGINE_ROOT,
      maxBuffer: 10 * 1024 * 1024,
      timeout: 20 * 60 * 1000,
      env: {
        ...process.env,
        PATH: pythonPathEnv(),
        OPENAI_API_KEY: state.openaiApiKey,
        OPENAI_MODEL: state.openaiModel,
        GEMINI_API_KEY: state.geminiApiKey,
        GEMINI_MODEL: state.geminiModel,
      },
    });

    const runDir = extractRunDir(stdout);
    const run = await loadRunBundle(runDir, tempRoot);
    run.clientId = client.id;

    await cleanupCurrentRun();
    currentRun = run;

    return res.json({
      ok: true,
      client,
      stdout,
      stderr,
      run,
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
      stderr,
    });
  }
});

app.get('/app.js', requireAuth, serveFile(path.join(APP_ROOT, 'public', 'app.js')));
app.get('/', requireAuth, serveFile(path.join(APP_ROOT, 'public', 'index.html')));
app.get('*', requireAuth, serveFile(path.join(APP_ROOT, 'public', 'index.html')));

app.use((error, req, res, _next) => {
  console.error(error);
  if (req.originalUrl.startsWith('/api/')) {
    return res.status(500).json({ error: error.message });
  }
  return res.status(500).send(error.message);
});

async function shutdown() {
  await cleanupCurrentRun();
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

ensureAuthBootstrap()
  .then(() => {
    app.listen(PORT, () => {
      console.log(`CCC Resume Studio Lite running at http://localhost:${PORT}`);
    });
  })
  .catch((error) => {
    console.error(`Failed to start server: ${error.message}`);
    process.exit(1);
  });
