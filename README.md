# Aria Storyteller

Aria is a local interactive storytelling companion with persistent, story-separated ChromaDB memory, a browser chat interface, Piper speech, and Vosk voice input.

## Run Aria

The machine needs Python 3.11+, Ollama, and the imported local model named `aria` in Aria's dedicated Ollama store. This setup uses port `11435` and `$HOME/Models/Ollama-Aria`, separate from Ollama's default service.

```bash
cd ~/Aria/aria_storyteller
./install.sh
./aria-launcher.sh
```

The launcher starts the dedicated Ollama service if needed, checks that `aria` is installed, starts the web app, and opens `http://127.0.0.1:8000`. To make a desktop shortcut, run `./create-desktop-launcher.sh`.

If the model has not been imported yet, create a Modelfile that points at your local GGUF file:

```text
FROM /absolute/path/to/Aria-Qwen3-4B-F16.gguf
```

Then import it into Aria's isolated Ollama store:

```bash
OLLAMA_MODELS="$HOME/Models/Ollama-Aria" OLLAMA_HOST=127.0.0.1:11435 \
  ollama create aria -f /path/to/Modelfile
```

Aria uses the OpenAI-compatible API at `http://127.0.0.1:11435/v1`. Set `ARIA_MODEL` or `ARIA_LLM_URL` in `.env` to override these defaults. The separate store and port keep the default Ollama installation available to other apps.

## Chat and roleplay

- **To Aria**: talk with Aria directly. She can also start, continue, or discuss stories.
- **In the story**: your message becomes your character's speech and actions in the scene.
- **Roleplay**: toggle roleplay on, then optionally describe Aria's roleplay personality in the field that appears. The setting stays enabled until switched off; the personality applies to each turn while enabled. You can also include a clear persona in your message.
- **New story**: use the sidebar button or `/new [premise]`.

The interface includes microphone input (Vosk) and spoken replies (Piper). Aria's persistent memory uses ChromaDB and filters retrieval by story ID, keeping each story's memories separate in the same database.

## Install and configuration

`./install.sh` creates `.venv`, installs the Python dependencies, and downloads the Vosk English model and Piper voice files, including JapaneseTutor's Amy medium voice. Voice and memory data stay local. The app reads optional settings from `.env`:

```env
ARIA_MODEL=aria
ARIA_LLM_URL=http://127.0.0.1:11435/v1
PIPER_QUALITY=medium
VOSK_MODEL=./models/vosk-model-small-en-us-0.15
CHROMA_PATH=./chroma_db
AUDIO_OUTPUT_DIR=./audio/output
```

The web app is served only on `127.0.0.1` by default. Logs are written to `aria-web.log` and `aria-ollama.log`.
