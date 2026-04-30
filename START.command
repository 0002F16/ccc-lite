#!/bin/bash
set -e
cd "$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
  osascript -e 'display dialog "Node.js is not installed yet.\n\nPlease install Node.js first, then run this file again." buttons {"OK"} default button "OK"'
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  osascript -e 'display dialog "Python 3 is not installed yet.\n\nPlease install Python 3 first, then run this file again." buttons {"OK"} default button "OK"'
  exit 1
fi

if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp ".env.example" ".env"
    osascript -e 'display dialog "I created a .env file for you.\n\nOpen it and paste your OpenAI or Gemini API key before starting the app." buttons {"OK"} default button "OK"'
    open -a TextEdit ".env"
    exit 0
  else
    osascript -e 'display dialog "Missing .env file. Please add one before starting." buttons {"OK"} default button "OK"'
    exit 1
  fi
fi

python3 -m pip install -r requirements.txt

if [ ! -d "node_modules" ]; then
  npm install
fi

open "http://localhost:4311"
node server.js
