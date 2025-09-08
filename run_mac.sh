#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Python venv
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "If DKBridge is not auto-found, set DK_BRIDGE_EXE to the built WheelerDKBridge binary."
echo "Example: export DK_BRIDGE_EXE=../WheelerHost-mac/build/Debug/WheelerDKBridge"

exec python wheeler_main.py

