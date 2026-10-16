#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

mkdir -p models
fetch() {
  local url="$1" target="$2"
  if [[ ! -s "$target" ]]; then
    echo "Downloading $(basename "$target")..."
    curl -fL --retry 3 "$url" -o "$target.tmp"
    mv "$target.tmp" "$target"
  fi
}

PIPER_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac"
for quality in medium high; do
  fetch "$PIPER_BASE/$quality/en_US-lessac-$quality.onnx?download=true" "models/en_US-lessac-$quality.onnx"
  fetch "$PIPER_BASE/$quality/en_US-lessac-$quality.onnx.json?download=true" "models/en_US-lessac-$quality.onnx.json"
done

# JapaneseTutor's configured voice is Amy (American English, medium).
PIPER_AMY_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium"
fetch "$PIPER_AMY_BASE/en_US-amy-medium.onnx?download=true" "models/en_US-amy-medium.onnx"
fetch "$PIPER_AMY_BASE/en_US-amy-medium.onnx.json?download=true" "models/en_US-amy-medium.onnx.json"

VOSK_DIR="models/vosk-model-small-en-us-0.15"
if [[ ! -d "$VOSK_DIR" ]]; then
  archive="$(mktemp --suffix=.zip)"
  trap 'rm -f "$archive"' EXIT
  curl -fL --retry 3 "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip" -o "$archive"
  "$PYTHON_BIN" - "$archive" models <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    z.extractall(sys.argv[2])
PY
fi

echo
echo "Aria's web app and Piper/Vosk voice models are ready."
echo "Make sure Ollama has the 'aria' model imported in its dedicated Aria model store."
echo "Start with: ./aria-launcher.sh"
