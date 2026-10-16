#!/usr/bin/env python3
"""Aria local web app backed by the dedicated Ollama service."""

import io
import json
import os
import wave
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from vosk import Model as VoskModel, KaldiRecognizer

from aria.core import AriaSession
MODEL_ID = os.getenv("ARIA_MODEL", "aria")
ARIA_LLM_URL = os.getenv("ARIA_LLM_URL", "http://127.0.0.1:11435/v1").rstrip("/")
OLLAMA_URL = ARIA_LLM_URL[:-3] if ARIA_LLM_URL.endswith("/v1") else ARIA_LLM_URL

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
app = FastAPI(title="Aria")
session = None
vosk_model = None


class ChatInput(BaseModel):
    message: str
    roleplay: bool = False
    roleplay_persona: str = ""


class QualityInput(BaseModel):
    quality: str


class StorySelection(BaseModel):
    story_id: str


class StoryRename(BaseModel):
    story_id: str
    title: str


@app.on_event("startup")
def startup():
    global session
    session = AriaSession()


def ollama_model_status():
    try:
        request = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(request, timeout=2) as response:
            models = json.load(response).get("models", [])
        available = any(
            item.get("name", "").split(":", 1)[0] == MODEL_ID.split(":", 1)[0]
            or item.get("model") == MODEL_ID
            for item in models
        )
        return {"ready": available, "loading": False,
                "error": None if available else f"Model {MODEL_ID} is not installed in Aria's Ollama store"}
    except Exception as exc:
        return {"ready": False, "loading": False,
                "error": f"Aria's Ollama service is unavailable at {OLLAMA_URL}: {exc}"}


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/status")
def status():
    story = session.memory.get_active_story() if session else None
    return {"ready": session is not None, "model": MODEL_ID, "model_status": ollama_model_status(),
            "story": story.get("title") if story else None,
            "voice": session.tts.quality if session else "medium",
            "piper": Path(session.tts.model_path()).is_file() if session else False,
            "vosk": Path(os.getenv("VOSK_MODEL", "./models/vosk-model-small-en-us-0.15")).is_dir()}


@app.get("/api/history")
def history(story_id: str | None = None):
    story = next((item for item in session.memory.list_stories() if item["id"] == story_id), None) if story_id else session.memory.get_active_story()
    if not story:
        return {"messages": []}
    story_id = story["story_id"]
    dialogue = session.memory.get_recent_dialogue(story_id, n=16)
    messages = [{"role": "user" if item["speaker"] == "player" else "assistant",
                 "content": item["content"]} for item in dialogue]
    openings = session.memory.story_events.get(
        where={"$and": [{"story_id": story_id}, {"type": "opening"}]}
    )
    if openings.get("documents"):
        messages.insert(0, {"role": "assistant", "content": openings["documents"][0]})
    return {"story": story.get("title", "Untitled story"), "messages": messages}


@app.get("/api/stories")
def stories():
    return {"stories": session.memory.list_stories(), "active_story_id": session.current_story_id}


@app.post("/api/stories/activate")
def activate_story(body: StorySelection):
    if not session.activate_story(body.story_id):
        raise HTTPException(404, "That story could not be found.")
    return {"story": session.get_story_title(), "story_id": session.current_story_id}


@app.post("/api/stories/rename")
def rename_story(body: StoryRename):
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Story name cannot be empty.")
    if len(title) > 100:
        raise HTTPException(400, "Story names must be 100 characters or fewer.")
    if not session.memory.rename_story(body.story_id, title):
        raise HTTPException(404, "That story could not be found.")
    return {"story": title}


@app.delete("/api/stories/{story_id}")
def delete_story(story_id: str):
    if not session.delete_story(story_id):
        raise HTTPException(404, "That story could not be found.")
    return {"stories": session.memory.list_stories(), "active_story_id": session.current_story_id}


@app.post("/api/chat")
def chat(body: ChatInput):
    try:
        if body.message.strip().startswith("/new"):
            result = session.send(body.message)
            content = result[1]
            if content.startswith("__NEW_STORY__"):
                content = content[len("__NEW_STORY__"):].strip()
            return {"reply": content, "story": session.get_story_title(), "command": False}
        mode, reply = session.send(body.message, body.roleplay, body.roleplay_persona)
        return {"reply": reply, "story": session.get_story_title(), "command": mode == "command"}
    except Exception as exc:
        raise HTTPException(503, f"Aria could not respond: {exc}")


@app.post("/api/voice")
def voice(body: ChatInput):
    if not session.tts.enabled:
        return Response(status_code=204)
    if body.message.strip().startswith("/"):
        return Response(status_code=204)
    data = session.synthesize(body.message)
    if not data:
        raise HTTPException(503, "Piper voice model is missing. Run ./install.sh.")
    return Response(data, media_type="audio/wav")


@app.post("/api/voice-quality")
def voice_quality(body: QualityInput):
    if body.quality != "medium":
        raise HTTPException(400, "Aria is using the JapaneseTutor Amy medium voice")
    session.set_voice_quality(body.quality)
    return {"quality": body.quality}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    global vosk_model
    model_path = Path(os.getenv("VOSK_MODEL", "./models/vosk-model-small-en-us-0.15"))
    if not model_path.is_dir():
        raise HTTPException(503, "Vosk model is missing. Run ./install.sh.")
    if vosk_model is None:
        vosk_model = VoskModel(str(model_path))
    import subprocess
    raw = await audio.read()
    try:
        converted = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"], input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
        with wave.open(io.BytesIO(converted), "rb") as wav:
            recognizer = KaldiRecognizer(vosk_model, wav.getframerate())
            recognizer.SetWords(False)
            chunks = []
            while True:
                chunk = wav.readframes(4000)
                if not chunk:
                    break
                recognizer.AcceptWaveform(chunk)
            chunks.append(json.loads(recognizer.FinalResult()).get("text", ""))
            return {"text": " ".join(chunks).strip()}
    except Exception as exc:
        raise HTTPException(400, f"Could not transcribe audio: {exc}")


app.mount("/assets", StaticFiles(directory=ROOT / "web" / "assets"), name="assets")
