# CCC Resume Studio Lite — Accounts Fork

Forked from: `../ccc-resume-studio-lite`
Created for: local account access and future multi-user client isolation

## Added in this fork

- File-backed auth and session handling in `server.js`
  - login route: `POST /api/auth/login`
  - logout route: `POST /api/auth/logout`
  - current-user route: `GET /api/auth/me`
  - HMAC-signed session cookie, httpOnly, SameSite=Lax, persistent server-side session store in `app-data/auth/sessions.json`
- Built-in access model in `data/access/users.json`
  - `admin` has `all-clients`
  - `brian` and `guarang` are valid accounts with empty `clientIds` placeholders for future assignment
- Password management helper in `scripts/set-password.js`
  - updates hashed passwords in `app-data/auth/users.json`
- New login page and authenticated app UI
  - `public/login.html`
  - `public/login.js`
  - `public/index.html`
  - `public/app.js`
  - `public/styles.css`

## Setup reminders

- Password hashes and session state are intentionally untracked under `app-data/auth/`.
- Initial passwords can be bootstrapped from `.env` with `ADMIN_PASSWORD`, `BRIAN_PASSWORD`, `GUARANG_PASSWORD`, or changed later with `npm run set-password -- <user>`.
- To give Brian or Guarang client access later, add client slug ids to their `clientIds` array in `data/access/users.json`.
