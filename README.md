# CCC Resume Studio Lite

A lightweight, self-contained fork of the CCC resume studio with local login and per-user client access control.

## What it does

- ships with bundled client schemas for Ganbar, Anastasiya, Beste, Nikul, Amandeep, Narmina, and Amal
- uses its own local engine copy, rules, and renderer
- requires login before any app/API access
- supports three built-in internal accounts: `admin`, `brian`, `guarang`
- lets you pick an allowed client, paste a job/company/role, and generate one resume
- shows the active provider from `.env`
- previews the current generated PDF
- keeps a persistent local session in the browser until logout or expiry

## What it does not do

- no self-service sign-up
- no saved run history
- no run ledger
- no persistent job snapshots
- no browsing past runs
- no project-folder artifact storage

The app generates into a temporary directory and keeps only the **current run** available while the server is running.

## Auth model

- `admin`: access to all bundled clients
- `brian`: valid login, no assigned clients yet
- `guarang`: valid login, no assigned clients yet
- tracked access rules live in `data/access/users.json`
- hashed passwords and session state live in `app-data/auth/` and are intentionally gitignored

## First-time setup

```bash
cd ~/Documents/CCC/experiments/ccc-resume-studio-lite-accounts-fork
cp .env.example .env
# fill in OPENAI_API_KEY and/or GEMINI_API_KEY
```

Set initial passwords in either of these ways:

1. One-time bootstrap through `.env` before the first start:

```bash
ADMIN_PASSWORD='replace-me'
BRIAN_PASSWORD='replace-me'
GUARANG_PASSWORD='replace-me'
```

2. Or set/update them directly at any time with the helper:

```bash
NEW_PASSWORD='replace-me' npm run set-password -- admin
NEW_PASSWORD='replace-me' npm run set-password -- brian
NEW_PASSWORD='replace-me' npm run set-password -- guarang
```

Notes:

- `app-data/auth/users.json` is created automatically and stores only PBKDF2 password hashes.
- `app-data/auth/session-secret` is generated automatically unless `SESSION_SECRET` is provided.
- `SESSION_COOKIE_SECURE=auto` works for local `http://localhost`; set it to `true` when serving behind HTTPS.

## Run

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:4311
```

## Access-control changes

- To assign Brian or Guarang to real client work later, add slug ids under `clientIds` in `data/access/users.json`.
- Client ids are the same slug values returned by `/api/clients`, for example `ganbar-shabanov` style ids.

## Provider fallback

- if `OPENAI_API_KEY` exists -> use OpenAI
- else if `GEMINI_API_KEY` exists -> use Gemini
- else -> show a configuration error

Default models:

- OpenAI: `gpt-4.1-mini`
- Gemini: `gemini-2.5-flash`
