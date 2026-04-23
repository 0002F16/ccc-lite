# CCC Resume Studio Lite

A lightweight, self-contained fork of the CCC resume studio.

## What it does

- ships with bundled client schemas for Ganbar, Anastasiya, Beste, Nikul, Amandeep, and Narmina
- uses its own local engine copy, rules, and renderer
- lets you pick a client, paste a job/company/role, and generate one resume
- shows the active provider from `.env`
- previews the current generated PDF
- exposes open/download links for the current run only

## What it does not do

- no saved run history
- no run ledger
- no persistent job snapshots
- no browsing past runs
- no project-folder artifact storage

The app generates into a temporary directory and keeps only the **current run** available while the server is running.

## Bundled data

- `data/clients/ganbar-shabanov/master_profile.json`
- `data/clients/anastasiya-karaneuskaya/master_profile.json`
- `data/clients/beste-keskiner/master_profile.json`
- `data/clients/nikul-padamani/master_profile.json`
- `data/clients/amandeep-kaur/master_profile.json`
- `data/clients/narmina-ibrahimova/master_profile.json`

## Self-contained engine assets

- `engine/run_resume_engine.py`
- `engine/check_resume_layout.py`
- `engine/rules/*`
- `engine/renderer/ccc_cv_generator_tuned.py`

## Run

```bash
cd ~/Documents/CCC/experiments/ccc-resume-studio-lite
cp .env.example .env
# fill in OPENAI_API_KEY and/or GEMINI_API_KEY
npm install
npm run dev
```

Open:

```text
http://localhost:4311
```

The bundled clients should appear as:
- Ganbar Shabanov
- Anastasiya Karaneuskaya
- Beste Keskiner
- Nikul Padamani
- Amandeep Kaur
- Narmina Ibrahimova

## Provider fallback

- if `OPENAI_API_KEY` exists → use OpenAI
- else if `GEMINI_API_KEY` exists → use Gemini
- else → show a configuration error

Default models:
- OpenAI: `gpt-4.1-mini`
- Gemini: `gemini-2.5-flash`
# ccc-resume-lite
