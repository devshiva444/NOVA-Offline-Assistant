import json
import os
import pyaudio
import pyttsx3
import time
import numpy as np


# ===== CONFIG FROM ENV =====
USE_WHISPER = os.getenv("USE_WHISPER", "1") == "1"
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "tiny")
VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH", "models/vosk-model-small-en-us-0.15")

# =========================
# INIT TTS
# =========================
engine = pyttsx3.init()
engine.setProperty('rate', 170)

def speak(text):
    print(f"Assistant: {text}")
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print("TTS Error:", e)

# =========================
# INIT MIC
# =========================
mic = pyaudio.PyAudio()

# =========================
# LOAD WHISPER
# =========================
whisper_model = None
if USE_WHISPER:
    try:
        from faster_whisper import WhisperModel
        print(f"[INFO] Loading Whisper model: {WHISPER_MODEL_NAME}...")
        whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device="cpu",
            compute_type="int8"
        )
        print("[SUCCESS] Whisper Ready")
    except Exception as e:
        print("[WARNING] Whisper failed:", e)
        whisper_model = None

# =========================
# LOAD VOSK
# =========================
from vosk import Model, KaldiRecognizer
print("[INFO] Loading Vosk model...")
vosk_model = Model(VOSK_MODEL_PATH)
vosk_recognizer = KaldiRecognizer(vosk_model, 16000)

# =========================
# LISTEN FUNCTION (FIXED)
# =========================
def listen():
    stream = mic.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=4096
    )

    stream.start_stream()
    print("🎤 Listening...")

    frames = []
    silence_count = 0
    silence_threshold = 500  # noise filter

    start_time = time.time()

    while True:
        data = stream.read(4096, exception_on_overflow=False)
        frames.append(data)

        # volume detect
        audio_data = np.frombuffer(data, dtype=np.int16)
        volume = np.abs(audio_data).mean()

        if volume < silence_threshold:
            silence_count += 1
        else:
            silence_count = 0

        # stop if silence or timeout
        if silence_count > 10 or (time.time() - start_time > 6):
            break

    stream.stop_stream()
    stream.close()

    audio_bytes = b"".join(frames)

    # =========================
    # WHISPER FIRST
    # =========================
    if whisper_model:
        try:
            audio_np = np.frombuffer(audio_bytes, np.int16).astype("float32") / 32768.0
            segments, _ = whisper_model.transcribe(audio_np)

            text = "".join([seg.text for seg in segments]).strip()

            # 🔥 noise filter
            if len(text) < 3:
                return ""

            if text.lower() in ["you", "i", ".", "..."]:
                return ""

            print(f"You (Whisper): {text}")
            return text.lower()

        except Exception as e:
            print("Whisper Error:", e)

    # =========================
    # VOSK FALLBACK
    # =========================
    try:
        if vosk_recognizer.AcceptWaveform(audio_bytes):
            result = json.loads(vosk_recognizer.Result())
            text = result.get("text", "")

            if text:
                print(f"You (Vosk): {text}")
                return text.lower()

    except Exception as e:
        print("Vosk Error:", e)

    return ""

# =========================
# TEST MODE
# =========================
if __name__ == "__main__":
    print("🎤 Offline Voice System Ready (Whisper + Vosk)\n")

    while True:
        user = listen()

        if user:
            speak(f"Aapne kaha: {user}")
        else:
            print("❌ No voice detected")