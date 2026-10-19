#!/bin/bash
# Double-click to start Client Research Assistant in your browser (macOS).
cd "$(dirname "$0")" || exit 1

if [ ! -x .venv/bin/python ]; then
  echo "First run: setting things up. This takes a few minutes..."
  if ! python3 -m venv .venv; then
    echo "Python 3.11 or newer is needed: https://www.python.org/downloads/"
    read -r -p "Press Enter to close."
    exit 1
  fi
fi

echo "Checking dependencies..."
if ! .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt; then
  echo "Installing dependencies failed. Check your internet connection and try again."
  read -r -p "Press Enter to close."
  exit 1
fi

echo
echo "Starting... your browser will open at http://localhost:8501"
echo "Keep this window open while you use the app. Close it to stop."
(sleep 4 && open http://localhost:8501) &
.venv/bin/python -m streamlit run app.py
