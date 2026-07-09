#!/bin/bash
# LocalFlow starten — Doppelklick im Finder genügt.
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
  echo "Richte beim ersten Start die Umgebung ein (kann ein paar Minuten dauern)…"
  /opt/homebrew/bin/python3.12 -m venv .venv || python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

echo "Starte LocalFlow… (dieses Fenster offen lassen)"
exec .venv/bin/python -m localflow.main
