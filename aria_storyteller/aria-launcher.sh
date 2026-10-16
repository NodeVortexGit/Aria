#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"

if [[ ! -x .venv/bin/python ]]; then
  echo "Aria is not installed yet. Run ./install.sh first."
  exit 1
fi
. .venv/bin/activate
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Run Aria in its own Ollama store and port, leaving JapaneseTutor's default
# Ollama service and models untouched.
ARIA_OLLAMA_HOST="${ARIA_OLLAMA_HOST:-127.0.0.1:11435}"
ARIA_OLLAMA_MODELS="${ARIA_OLLAMA_MODELS:-$HOME/Models/Ollama-Aria}"
export ARIA_LLM_URL="${ARIA_LLM_URL:-http://${ARIA_OLLAMA_HOST}/v1}"
export ARIA_MODEL="${ARIA_MODEL:-aria}"
if ! curl -fsS "http://${ARIA_OLLAMA_HOST}/api/version" >/dev/null 2>&1; then
  if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama is required. Install it, then import Aria's GGUF model." >&2
    exit 1
  fi
  echo "Starting Aria's Ollama service on ${ARIA_OLLAMA_HOST} …"
  nohup setsid env OLLAMA_MODELS="$ARIA_OLLAMA_MODELS" OLLAMA_HOST="$ARIA_OLLAMA_HOST" ollama serve \
    >> aria-ollama.log 2>&1 < /dev/null &
  echo $! > aria-ollama.pid
fi
for _ in $(seq 1 60); do
  curl -fsS "http://${ARIA_OLLAMA_HOST}/api/version" >/dev/null 2>&1 && break
  sleep 1
done
if ! curl -fsS "http://${ARIA_OLLAMA_HOST}/api/version" >/dev/null 2>&1; then
  echo "Aria's Ollama service did not start. Check $PWD/aria-ollama.log" >&2
  exit 1
fi
if ! OLLAMA_HOST="$ARIA_OLLAMA_HOST" ollama show "$ARIA_MODEL" >/dev/null 2>&1; then
  echo "Model '$ARIA_MODEL' is not in Aria's Ollama store ($ARIA_OLLAMA_MODELS)." >&2
  echo "Import it with: OLLAMA_MODELS='$ARIA_OLLAMA_MODELS' OLLAMA_HOST='$ARIA_OLLAMA_HOST' ollama create aria -f ~/Modelfile.aria.gguf" >&2
  exit 1
fi

# Avoid pegging all laptop cores during model load and CPU inference.
export ARIA_CPU_THREADS="${ARIA_CPU_THREADS:-4}"
export OMP_NUM_THREADS="$ARIA_CPU_THREADS"
export MKL_NUM_THREADS="$ARIA_CPU_THREADS"
export TOKENIZERS_PARALLELISM=false

PORT="${ARIA_PORT:-8000}"
URL="http://127.0.0.1:${PORT}"
if curl -fsS "$URL/api/status" >/dev/null 2>&1; then
  echo "Aria is already running at $URL"
else
  echo "Starting Aria on $URL …"
  nohup setsid .venv/bin/uvicorn web_server:app --host 127.0.0.1 --port "$PORT" \
    >> aria-web.log 2>&1 < /dev/null &
  echo $! > aria-web.pid
fi

for _ in $(seq 1 300); do
  if curl -fsS "$URL/api/status" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "$URL/api/status" >/dev/null 2>&1; then
  echo "Aria did not start. Check the log: $PWD/aria-web.log" >&2
  exit 1
fi

STATUS="$(curl -fsS "$URL/api/status")"
MODEL_STATE="$(.venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); m=d.get("model_status",{}); print("ready" if m.get("ready") else ("error: " + str(m.get("error")) if m.get("error") else "loading in background"))' <<< "$STATUS")"
echo "Aria server is ready; model is $MODEL_STATE."
echo "Web page: $URL"
echo "Server log: $PWD/aria-web.log"
if command -v notify-send >/dev/null 2>&1; then
  notify-send "Aria is ready" "Model: $MODEL_STATE\n$URL" >/dev/null 2>&1 || true
fi

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 &
elif command -v firefox >/dev/null 2>&1; then
  firefox "$URL" >/dev/null 2>&1 &
else
  echo "Open $URL in your browser."
fi
