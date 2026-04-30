# CCC Resume Studio Lite — Easy Setup Guide

This folder contains a small resume-generation app.

## What this app does

It lets you:
- choose a client profile
- paste a job description
- generate a tailored resume PDF

## Important reality check

This package is **self-contained in terms of source code**, but it is **not fully standalone**.

To run it on a Mac, the computer still needs:
- **Node.js**
- **Python 3**
- an **OpenAI API key** or **Gemini API key**

The good news:
- you do **not** need Git
- you do **not** need to use Terminal much if someone sets it up once
- `START.command` is included to make startup easier

---

## Fastest way to run it

### Step 1 — Install Node.js
Go to:
- https://nodejs.org/

Download the **LTS** version and install it.

### Step 2 — Install Python 3
Go to:
- https://www.python.org/downloads/

Download the latest stable **Python 3** for Mac and install it.

### Step 3 — Add your AI API key
Inside this folder:
- find the file called `.env`
- if it does not exist yet, double-click `START.command` once and it will create it

Open `.env` in TextEdit and paste **one** of these:

### Option A — OpenAI
```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

### Option B — Gemini
```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Save the file.

### Step 4 — Start the app
Double-click:
- `START.command`

It should:
- check if Node and Python are installed
- install any missing app packages if needed
- open the app in your browser

The app runs at:
- http://localhost:4311

---

## If double-click does not work

Open Terminal, drag this folder into it, then run:

```bash
cd /path/to/ccc-resume-studio-lite
python3 -m pip install -r requirements.txt
npm install
node server.js
```

Then open:
- http://localhost:4311

---

## What to send someone else

If you are sharing this project, send them:
- the whole `ccc-resume-studio-lite` folder
- or the prepared zip file

They do **not** need Git.
They **do** still need Node.js and Python 3 installed on their Mac.

---

## Troubleshooting

### “node: command not found”
Node.js is not installed yet.
Install it from https://nodejs.org/

### “python3: command not found”
Python 3 is not installed yet.
Install it from https://www.python.org/downloads/

### “No API key found”
Open `.env` and paste your OpenAI or Gemini API key.

### “ModuleNotFoundError: reportlab”
Run:
```bash
python3 -m pip install -r requirements.txt
```

### The browser opens but generation fails
Usually one of these is missing:
- API key
- Python dependency
- internet access for the AI provider

---

## Bottom line

This is **easy to hand off**, but **not truly zero-install**.

If you want a real no-install version for non-technical users, the best next step would be one of these:
- turn it into a hosted web app
- build a packaged desktop app
- move the Python generation backend to a server
