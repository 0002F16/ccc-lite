const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const crypto = require('crypto');

const APP_ROOT = path.resolve(__dirname, '..');
const ACCESS_MODEL_FILE = path.join(APP_ROOT, 'data', 'access', 'users.json');
const AUTH_DIR = path.join(APP_ROOT, 'app-data', 'auth');
const USERS_FILE = path.join(AUTH_DIR, 'users.json');
const PASSWORD_ITERATIONS = 210000;
const PASSWORD_KEYLEN = 32;
const PASSWORD_DIGEST = 'sha256';

function hashPassword(password, salt = crypto.randomBytes(16).toString('hex')) {
  const derivedKey = crypto.pbkdf2Sync(String(password), salt, PASSWORD_ITERATIONS, PASSWORD_KEYLEN, PASSWORD_DIGEST);
  return `pbkdf2$${PASSWORD_ITERATIONS}$${salt}$${derivedKey.toString('hex')}`;
}

async function readJson(filePath) {
  return JSON.parse(await fsp.readFile(filePath, 'utf8'));
}

async function writeJson(filePath, value) {
  await fsp.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

async function ensureUsersFile() {
  const accessModel = await readJson(ACCESS_MODEL_FILE);
  await fsp.mkdir(AUTH_DIR, { recursive: true });

  if (!fs.existsSync(USERS_FILE)) {
    await writeJson(USERS_FILE, {
      version: 1,
      users: (accessModel.users || []).map((user) => ({
        username: user.username,
        passwordHash: null,
        passwordUpdatedAt: null,
      })),
    });
  }

  return accessModel;
}

async function main() {
  const username = String(process.argv[2] || '').trim().toLowerCase();
  const password = String(process.env.NEW_PASSWORD || process.argv[3] || '');

  if (!username || !password) {
    console.error('Usage: NEW_PASSWORD="..." node scripts/set-password.js <admin|brian|guarang>');
    console.error('Fallback: node scripts/set-password.js <username> <password>');
    process.exit(1);
  }

  const accessModel = await ensureUsersFile();
  const allowedUsers = new Set((accessModel.users || []).map((user) => user.username));
  if (!allowedUsers.has(username)) {
    console.error(`Unknown user: ${username}`);
    process.exit(1);
  }

  const state = await readJson(USERS_FILE);
  const users = Array.isArray(state.users) ? state.users : [];
  const existing = users.find((user) => user.username === username);
  const passwordHash = hashPassword(password);

  if (existing) {
    existing.passwordHash = passwordHash;
    existing.passwordUpdatedAt = new Date().toISOString();
  } else {
    users.push({
      username,
      passwordHash,
      passwordUpdatedAt: new Date().toISOString(),
    });
  }

  await writeJson(USERS_FILE, {
    version: 1,
    users,
  });

  console.log(`Password updated for ${username}.`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
