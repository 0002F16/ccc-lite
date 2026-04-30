# CCC Resume Studio Lite — Accounts Fork

Forked from: `../ccc-resume-studio-lite`
Created for: future work on accounts / multi-user support / more people records

## Current status
- This fork is a clean sibling copy of the current Resume Studio Lite app.
- Heavy generated directories were intentionally not copied: `.git`, `node_modules`, `.venv`.
- Environment files from the source app were copied so the fork can be booted locally with the same baseline config.

## Suggested next steps later
1. Reinstall dependencies:
   - `npm install`
   - `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2. Define the accounts model:
   - single admin vs multiple staff accounts
   - auth method
   - per-person data isolation rules
3. Expand people/client data structure to support many records safely.
4. Add migration/backfill notes before editing live data.

## Intent
This fork exists to protect the current working app while making room for a bigger architecture change later.
