import json
import os
import pyaudio
import pyttsx3
import time
import numpy as np
import pythoncom
import threading
import queue

# ===== CONFIG FROM ENV =====
USE_WHISPER = os.getenv("USE_WHISPER", "1") == "1"
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "tiny")
VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH", "models/vosk-model-small-en-us-0.15")

# =========================
# ASYNC TTS SYSTEM (WITH AUDIO STATUS)
# =========================
class TTSManager:
    def __init__(self):
        self.speech_queue = queue.Queue()
        self.is_running = True
        self.is_speaking = False  # NAYA: Track karega ki bol raha hai ya nahi
        self.worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
        self.worker_thread.start()

    def _speech_worker(self):
        pythoncom.CoInitialize()
        
        while self.is_running:
            try:
                text = self.speech_queue.get(timeout=0.1)
                
                if text == "__STOP_SIGNAL__":
                    self.is_speaking = False
                    continue
                    
                text = text.strip()
                if len(text) > 0 and any(c.isalnum() for c in text):
                    self.is_speaking = True  # Bolna shuru kiya
                    print(f"Speaking: {text}")
                    engine = pyttsx3.init()
                    engine.setProperty('rate', 170)
                    engine.say(text)
                    engine.runAndWait()
                    del engine  
                    self.is_speaking = False  # Bolna khatam kiya
                    
                self.speech_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.is_speaking = False
                print(f"TTS Engine Error: {e}")

    def speak(self, text):
        if text and str(text).strip():
            self.speech_queue.put(str(text))

    def stop_speaking(self):
        with self.speech_queue.mutex:
            self.speech_queue.queue.clear()
        self.speech_queue.put("__STOP_SIGNAL__")

    # NAYA: Check karne ke liye ki queue me text hai ya audio chal raha hai
    def is_busy(self):
        return self.is_speaking or not self.speech_queue.empty()

tts_manager = TTSManager()

def speak(text):
    tts_manager.speak(text)

def stop_tts():
    tts_manager.stop_speaking()

# NAYA FUNCTION: Jisko main.py use karega
def is_audio_playing():
    return tts_manager.is_busy()


# =========================
# INIT MIC & WHISPER & VOSK
# =========================
mic = pyaudio.PyAudio()

whisper_model = None
if USE_WHISPER:
    try:
        from faster_whisper import WhisperModel
        print(f"[INFO] Loading Whisper model: {WHISPER_MODEL_NAME}...")
        whisper_model = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
        print("[SUCCESS] Whisper Ready")
    except Exception as e:
        print("[WARNING] Whisper failed:", e)
        whisper_model = None

from vosk import Model, KaldiRecognizer
print("[INFO] Loading Vosk model...")
vosk_model = Model(VOSK_MODEL_PATH)
vosk_recognizer = KaldiRecognizer(vosk_model, 16000)

def listen():
    stream = mic.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=4096)
    stream.start_stream()
    print("🎤 Listening...")

    frames = []
    silence_count = 0
    silence_threshold = 500  
    start_time = time.time()

    while True:
        data = stream.read(4096, exception_on_overflow=False)
        frames.append(data)
        audio_data = np.frombuffer(data, dtype=np.int16)
        volume = np.abs(audio_data).mean()

        if volume < silence_threshold:
            silence_count += 1
        else:
            silence_count = 0

        if silence_count > 10 or (time.time() - start_time > 6):
            break

    stream.stop_stream()
    stream.close()
    audio_bytes = b"".join(frames)

    if whisper_model:
        try:
            audio_np = np.frombuffer(audio_bytes, np.int16).astype("float32") / 32768.0
            segments, _ = whisper_model.transcribe(audio_np)
            text = "".join([seg.text for seg in segments]).strip()
            if len(text) < 3 or text.lower() in ["you", "i", ".", "..."]:
                return ""
            print(f"You (Whisper): {text}")
            return text.lower()
        except Exception as e:
            print("Whisper Error:", e)

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


# import json
# import os
# import pyaudio
# import pyttsx3
# import time
# import numpy as np
# import pythoncom


# # ===== CONFIG FROM ENV =====
# USE_WHISPER = os.getenv("USE_WHISPER", "1") == "1"
# WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "tiny")
# VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH", "models/vosk-model-small-en-us-0.15")

# # =========================
# # INIT TTS
# # =========================
# def speak(text):
#     print(f"Assistant: {text}")
#     try:
#         # Initialize COM object for the current background thread
#         try:
#             pythoncom.CoInitialize()
#         except Exception:
#             pass
            
#         engine = pyttsx3.init()
#         engine.setProperty('rate', 170)
#         engine.say(text)
#         engine.runAndWait()
#     except Exception as e:
#         print("TTS Error:", e)

# # =========================
# # INIT MIC
# # =========================
# mic = pyaudio.PyAudio()

# # =========================
# # LOAD WHISPER
# # =========================
# whisper_model = None
# if USE_WHISPER:
#     try:
#         from faster_whisper import WhisperModel
#         print(f"[INFO] Loading Whisper model: {WHISPER_MODEL_NAME}...")
#         whisper_model = WhisperModel(
#             WHISPER_MODEL_NAME,
#             device="cpu",
#             compute_type="int8"
#         )
#         print("[SUCCESS] Whisper Ready")
#     except Exception as e:
#         print("[WARNING] Whisper failed:", e)
#         whisper_model = None

# # =========================
# # LOAD VOSK
# # =========================
# from vosk import Model, KaldiRecognizer
# print("[INFO] Loading Vosk model...")
# vosk_model = Model(VOSK_MODEL_PATH)
# vosk_recognizer = KaldiRecognizer(vosk_model, 16000)

# # =========================
# # LISTEN FUNCTION (FIXED)
# # =========================
# def listen():
#     stream = mic.open(
#         format=pyaudio.paInt16,
#         channels=1,
#         rate=16000,
#         input=True,
#         frames_per_buffer=4096
#     )

#     stream.start_stream()
#     print("🎤 Listening...")

#     frames = []
#     silence_count = 0
#     silence_threshold = 500  # noise filter

#     start_time = time.time()

#     while True:
#         data = stream.read(4096, exception_on_overflow=False)
#         frames.append(data)

#         # volume detect
#         audio_data = np.frombuffer(data, dtype=np.int16)
#         volume = np.abs(audio_data).mean()

#         if volume < silence_threshold:
#             silence_count += 1
#         else:
#             silence_count = 0

#         # stop if silence or timeout
#         if silence_count > 10 or (time.time() - start_time > 6):
#             break

#     stream.stop_stream()
#     stream.close()

#     audio_bytes = b"".join(frames)

#     # =========================
#     # WHISPER FIRST
#     # =========================
#     if whisper_model:
#         try:
#             audio_np = np.frombuffer(audio_bytes, np.int16).astype("float32") / 32768.0
#             segments, _ = whisper_model.transcribe(audio_np)

#             text = "".join([seg.text for seg in segments]).strip()

#             # 🔥 noise filter
#             if len(text) < 3:
#                 return ""

#             if text.lower() in ["you", "i", ".", "..."]:
#                 return ""

#             print(f"You (Whisper): {text}")
#             return text.lower()

#         except Exception as e:
#             print("Whisper Error:", e)

#     # =========================
#     # VOSK FALLBACK
#     # =========================
#     try:
#         if vosk_recognizer.AcceptWaveform(audio_bytes):
#             result = json.loads(vosk_recognizer.Result())
#             text = result.get("text", "")

#             if text:
#                 print(f"You (Vosk): {text}")
#                 return text.lower()

#     except Exception as e:
#         print("Vosk Error:", e)

#     return ""

# # =========================
# # TEST MODE
# # =========================
# if __name__ == "__main__":
#     print("🎤 Offline Voice System Ready (Whisper + Vosk)\n")

#     while True:
#         user = listen()

#         if user:
#             speak(f"You: {user}")
#         else:
#             print("❌ No voice detected")