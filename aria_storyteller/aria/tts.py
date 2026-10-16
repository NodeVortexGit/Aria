"""Local Piper speech synthesis using JapaneseTutor's Amy American English voice."""

import os
import re
import subprocess
import tempfile
import threading
import shutil
import sys
from pathlib import Path


def clean_for_tts(text: str) -> str:
    text = re.sub(r"\[Aria[^\]]*\]|\[[A-Z][^\]]*\]:|\[.*?\]", "", text)
    text = re.sub(r"\*\*(.+?)\*\*|\*(.+?)\*", lambda m: m.group(1) or m.group(2), text)
    return re.sub(r"\s+", " ", text).strip()


class AriaVoice:
    def __init__(self, output_dir="./audio/output", enabled=True):
        self.output_dir = output_dir
        self.enabled = enabled
        self.quality = os.getenv("PIPER_QUALITY", "medium").lower()
        self._lock = threading.Lock()
        os.makedirs(output_dir, exist_ok=True)

    def model_path(self):
        return os.getenv("PIPER_MODEL", "./models/en_US-amy-medium.onnx")

    @staticmethod
    def _piper_executable():
        return shutil.which("piper") or str(Path(sys.executable).resolve().parent / "piper")

    def synthesize(self, text: str) -> bytes:
        clean = clean_for_tts(text)
        model = self.model_path()
        if not clean or not Path(model).is_file():
            return b""
        with self._lock, tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav:
            path = wav.name
        try:
            subprocess.run([self._piper_executable(), "--model", model, "--output_file", path], input=clean[:5000],
                           text=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            return Path(path).read_bytes()
        except (OSError, subprocess.CalledProcessError):
            return b""
        finally:
            Path(path).unlink(missing_ok=True)

    def speak(self, text: str, blocking: bool = False):
        if not self.enabled:
            return
        def play():
            audio = self.synthesize(text)
            if not audio:
                return
            try:
                import soundfile as sf
                import sounddevice as sd
                import io
                samples, rate = sf.read(io.BytesIO(audio), dtype="float32")
                sd.play(samples, rate)
                if blocking:
                    sd.wait()
            except Exception:
                pass
        if blocking:
            play()
        else:
            threading.Thread(target=play, daemon=True).start()

    def speak_blocking(self, text: str):
        self.speak(text, blocking=True)

    def stop(self):
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def set_enabled(self, val: bool):
        self.enabled = bool(val)

    def set_quality(self, quality: str):
        # JapaneseTutor uses Amy medium; keep this preset consistent regardless
        # of any stale quality preference stored by an older frontend.
        self.quality = "medium"

    @staticmethod
    def is_available() -> bool:
        return bool(shutil.which("piper") or (Path(sys.executable).resolve().parent / "piper").is_file())
