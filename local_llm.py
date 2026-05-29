import os
import shutil
import subprocess
import requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load runtime configuration from .env (if present)
load_dotenv()

# Configurable via .env
MODELS_DIR = os.environ.get("MODELS_DIR", "models")
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "sarvam-1-2b-instruct-q8_0.gguf")
LLM_CONTEXT = int(os.environ.get("LLM_CONTEXT", os.environ.get("LOCAL_LLM_CTX", "2048")))
LLM_THREADS = int(os.environ.get("LLM_THREADS", os.environ.get("LOCAL_LLM_THREADS", "4")))
LLM_PORT = int(os.environ.get("LLM_PORT", os.environ.get("LOCAL_LLM_PORT", "8080")))
LLAMA_BIN_DIR = os.environ.get("LLAMA_BIN_DIR", os.path.join("llama", "bin"))

MODEL_PATH = os.path.join(BASE_DIR, MODELS_DIR, LLM_MODEL_NAME)
LLAMA_PATH = os.path.join(BASE_DIR, LLAMA_BIN_DIR)
API_URL = os.environ.get("LOCAL_LLM_API", f"http://127.0.0.1:{LLM_PORT}")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
IDENTITY_FILE = os.path.join(PROMPTS_DIR, "identity.md")

def _log_debug(entry: str):
    try:
        with open(os.path.join(BASE_DIR, "llama_debug.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat()} - {entry}\n")
    except Exception:
        pass

def get_identity():
    """Reads the AI identity from identity.md. Fallback to default if missing."""
    if os.path.exists(IDENTITY_FILE):
        try:
            with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception as e:
            _log_debug(f"Error reading identity.md: {e}")
    
    # Default fallback if file is missing or empty
    # return "You are Nova, an advanced and highly capable AI assistant. Provide clear, direct, and concise answers."
    return "You are NOVA, a fully offline AI assistant created by Shivraj Selar, Vivek Kevat, and Kartik Kewat for Government Polytechnic College Raghogarh."
    

def build_prompt(user_input, memory, conversation_history):
    identity = get_identity()

    uname = None
    try:
        if memory:
            uname = memory.get_user_name("default_user")
    except Exception:
        uname = None

    convo_lines = []
    if conversation_history:
        for msg in (conversation_history or [])[-6:]:
            role = msg.get("role", "user")
            text = (msg.get("text", "") or "").strip()
            if not text or len(text) > 800:
                continue
            import re
            if re.search(r"\bmemory\b|saved memory|q:\s|a:\s|\<\|im_start\|\>", text, flags=re.IGNORECASE):
                continue
            text = " ".join(text.split())
            
            # Ensure roles align correctly
            role_name = "NOVA" if role.lower() == "assistant" else "User"
            convo_lines.append(f"{role_name}: {text}")

    conv_block = "\n".join(convo_lines)
    name_line = f"The user's name is: {uname}\n" if uname else ""

    prompt = f"{identity}\n{name_line}"
    if conv_block:
        prompt += f"\nRecent conversation:\n{conv_block}\n"

    # Fixed typo from \Nova: to \nNOVA:
    prompt += f"\nUser: {user_input}\nNOVA:"
    return prompt

def build_system_context(user_input, memory, conversation_history):
    uname = None
    try:
        if memory:
            uname = memory.get_user_name("default_user")
    except Exception:
        uname = None
    base = get_identity()
    base += "\nIMPORTANT RULE: If the user provides 'UPLOADED DOCUMENT CONTENT', you MUST read it and answer based ONLY on that text."
    if uname:
        base = f"{base}\nThe user's name is {uname}."
    return base

def _find_llama_executable():
    candidates = [
        os.path.join(LLAMA_PATH, "llama-server-cpu.exe"),
        os.path.join(LLAMA_PATH, "llama-server.exe"),
        os.path.join(LLAMA_PATH, "llama-cli.exe"),
        os.path.join(LLAMA_PATH, "llama.exe"),
    ]
    for name in ("llama-server-cpu.exe", "llama-server.exe", "llama-cli", "llama"):
        which = shutil.which(name)
        if which:
            return which
    return None

def ask_llm(user_input, memory=None, conversation_history=None, on_update=None, stop_event=None):
    prompt = build_prompt(user_input, memory, conversation_history)
    system_context = build_system_context(user_input, memory, conversation_history)

    try:
        timeout_http = int(os.environ.get("LOCAL_LLM_HTTP_TIMEOUT", "300")) 
        use_chat_api = os.environ.get("LOCAL_LLM_USE_CHAT_API", "1") in ("1", "true", "True")

        if use_chat_api:
            payload = {
                "model": os.environ.get("LLM_MODEL_NAME", ""),
                "messages": [
                    {"role": "system", "content": system_context},
                    {"role": "user", "content": user_input}
                ],
                "max_tokens": 512,
                "temperature": 0.1,  
                "top_p": 0.85,
                "frequency_penalty": 1.2, 
                "presence_penalty": 1.2, 
                "stop": ["User:", "Assistant:", "NOVA:", "<|im_end|>", "</s>", "\n\nUser:"] 
            }
            
            stream_enabled = os.environ.get("LOCAL_LLM_STREAM", "1") in ("1", "true", "True")
            url = API_URL.rstrip('/') + "/v1/chat/completions"
            
            if stream_enabled:
                payload["stream"] = True
                try:
                    resp = requests.post(url, json=payload, timeout=timeout_http, stream=True)
                except Exception as e:
                    _log_debug(f"HTTP stream error: {e}")
                    if on_update: on_update(f"\n[SERVER TIMEOUT/ERROR: Server peeche busy hai, please wait.]")
                    return f"Connection Error: {e}"

                if resp is not None and resp.status_code == 200:
                    final_text = ""
                    try:
                        for line in resp.iter_lines(decode_unicode=True):
                            if stop_event and stop_event.is_set():
                                resp.close()
                                if on_update: on_update("\n[STOPPED BY USER]")
                                break
                                
                            if not line:
                                continue
                            raw = line.decode('utf-8') if isinstance(line, bytes) else line
                            if raw.strip().startswith("data: "):
                                raw = raw.split("data: ", 1)[1]
                            if raw.strip() in ("[DONE]", "[done]"):
                                break
                            try:
                                obj = __import__('json').loads(raw)
                                chunk = obj.get('choices', [])[0].get('delta', {}).get('content', '') or ''
                                if chunk:
                                    final_text += chunk
                                    if on_update:
                                        on_update(chunk)
                            except Exception:
                                continue
                    finally:
                        return _post_process(final_text.strip(), user_input)
                else:
                    return f"LLM server error: {resp.status_code}"
            else:
                resp = requests.post(url, json=payload, timeout=timeout_http)
                if resp.status_code == 200:
                    j = resp.json()
                    text = j.get('choices', [])[0].get('message', {}).get('content', '').strip()
                    return _post_process(text, user_input)
                else:
                    return f"LLM server error: {resp.status_code}"

    except Exception as e:
        _log_debug(f"HTTP server error: {e}")
        return f"Error: {e}"

def _post_process(text: str, user_input: str) -> str:
    if not text: return "(no response)"
    import re
    for marker in ["<|im_start|>", "<|im_end|>", "<|start|>", "<|end|>", "[INST]", "[/INST]", "[START]", "[END]"]:
        text = text.replace(marker, "")
    lines = []
    for ln in text.splitlines():
        ln_strip = ln.strip()
        if not ln_strip: continue
        ln_lower = ln_strip.lower()
        if re.match(r'^(user|assistant|jarvis|nova|memory|q:|a:|loading|generation)\b', ln_lower): continue
        if re.search(r'\b(user|assistant|jarvis|nova)\s*:', ln_lower): continue
        lines.append(ln_strip)
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    result = cleaned or text.strip()
    return result if result else "(no response)"




# working
# import os
# import shutil
# import subprocess
# import requests
# from datetime import datetime
# from dotenv import load_dotenv

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# # Load runtime configuration from .env (if present)
# load_dotenv()

# # Configurable via .env
# MODELS_DIR = os.environ.get("MODELS_DIR", "models")
# LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "sarvam-1-2b-instruct-q8_0.gguf")
# LLM_CONTEXT = int(os.environ.get("LLM_CONTEXT", os.environ.get("LOCAL_LLM_CTX", "2048")))
# LLM_THREADS = int(os.environ.get("LLM_THREADS", os.environ.get("LOCAL_LLM_THREADS", "4")))
# LLM_PORT = int(os.environ.get("LLM_PORT", os.environ.get("LOCAL_LLM_PORT", "8080")))
# LLAMA_BIN_DIR = os.environ.get("LLAMA_BIN_DIR", os.path.join("llama", "bin"))

# MODEL_PATH = os.path.join(BASE_DIR, MODELS_DIR, LLM_MODEL_NAME)
# LLAMA_PATH = os.path.join(BASE_DIR, LLAMA_BIN_DIR)
# API_URL = os.environ.get("LOCAL_LLM_API", f"http://127.0.0.1:{LLM_PORT}")

# def _log_debug(entry: str):
#     try:
#         with open(os.path.join(BASE_DIR, "llama_debug.log"), "a", encoding="utf-8") as fh:
#             fh.write(f"{datetime.now().isoformat()} - {entry}\n")
#     except Exception:
#         pass

# def build_prompt(user_input, memory, conversation_history):
#     identity = "You are Jarvis AI, a concise helpful offline assistant."
#     instruction = "Answer briefly in Hinglish (1-3 sentences). For 'name' questions, answer directly. Do NOT ask back."

#     uname = None
#     try:
#         if memory:
#             uname = memory.get_user_name("default_user")
#     except Exception:
#         uname = None

#     convo_lines = []
#     if conversation_history:
#         for msg in (conversation_history or [])[-6:]:
#             role = msg.get("role", "user")
#             text = (msg.get("text", "") or "").strip()
#             if not text or len(text) > 800:
#                 continue
#             import re
#             if re.search(r"\bmemory\b|saved memory|q:\s|a:\s|\<\|im_start\|\>", text, flags=re.IGNORECASE):
#                 continue
#             text = " ".join(text.split())
#             convo_lines.append(f"{role.capitalize()}: {text}")

#     conv_block = "\n".join(convo_lines)
#     name_line = f"User name: {uname}\n" if uname else ""

#     prompt = identity + "\n" + instruction + "\n" + name_line
#     if conv_block:
#         prompt += "\nRecent conversation:\n" + conv_block + "\n"

#     prompt += f"\nUser: {user_input}\Nova:"
#     return prompt

# def build_system_context(user_input, memory, conversation_history):
#     uname = None
#     try:
#         if memory:
#             uname = memory.get_user_name("default_user")
#     except Exception:
#         uname = None

#     base = "You are Nova, a helpful AI. Answer in simple Hinglish. Keep it extremely concise and do not repeat yourself."
#     if uname:
#         base = f"{base} The user's name is {uname}."
#     return base

# def _find_llama_executable():
#     candidates = [
#         os.path.join(LLAMA_PATH, "llama-server-cpu.exe"),
#         os.path.join(LLAMA_PATH, "llama-server.exe"),
#         os.path.join(LLAMA_PATH, "llama-cli.exe"),
#         os.path.join(LLAMA_PATH, "llama.exe"),
#     ]
#     # fallback to PATH
#     for name in ("llama-server-cpu.exe", "llama-server.exe", "llama-cli", "llama"):
#         which = shutil.which(name)
#         if which:
#             return which

#     return None

# def ask_llm(user_input, memory=None, conversation_history=None, on_update=None, stop_event=None):
   
#     prompt = build_prompt(user_input, memory, conversation_history)
#     system_context = build_system_context(user_input, memory, conversation_history)

#     # 1) Try local HTTP server (fast if you run a llama server)
#     try:
#         timeout_http = int(os.environ.get("LOCAL_LLM_HTTP_TIMEOUT", "300")) # NAYA FIX: Timeout 20 se 300 seconds
#         use_chat_api = os.environ.get("LOCAL_LLM_USE_CHAT_API", "1") in ("1", "true", "True")

#         if use_chat_api:
#             # MISSING `payload = {` HAS BEEN FIXED HERE 👇
#             payload = {
#                 "model": os.environ.get("LLM_MODEL_NAME", ""),
#                 "messages": [
#                     {"role": "system", "content": system_context},
#                     {"role": "user", "content": user_input}
#                 ],
#                 "max_tokens": 512,
#                 "temperature": 0.2, # Low temp = less hallucination
#                 "top_p": 0.9,
#                 "frequency_penalty": 1.15, # Ye naya penalty isko ek baat baar-baar bolne se rokega
#                 "stop": ["User:", "Assistant:", "<|im_end|>", "</s>", "\n\nUser:"] # Strict Stops
#             }
            
#             stream_enabled = os.environ.get("LOCAL_LLM_STREAM", "1") in ("1", "true", "True")
#             url = API_URL.rstrip('/') + "/v1/chat/completions"
            
#             if stream_enabled:
#                 payload["stream"] = True
#                 try:
#                     resp = requests.post(url, json=payload, timeout=timeout_http, stream=True)
#                 except Exception as e:
#                     _log_debug(f"HTTP stream error: {e}")
#                     if on_update: on_update(f"\n[SERVER TIMEOUT/ERROR: Server peeche busy hai, please wait.]")
#                     return f"Connection Error: {e}"

#                 if resp is not None and resp.status_code == 200:
#                     final_text = ""
#                     try:
#                         for line in resp.iter_lines(decode_unicode=True):
#                             # NAYA FIX: Handle STOP Event Properly!
#                             if stop_event and stop_event.is_set():
#                                 resp.close()
#                                 if on_update: on_update("\n[STOPPED BY USER]")
#                                 break
                                
#                             if not line:
#                                 continue
#                             raw = line.decode('utf-8') if isinstance(line, bytes) else line
#                             if raw.strip().startswith("data: "):
#                                 raw = raw.split("data: ", 1)[1]
#                             if raw.strip() in ("[DONE]", "[done]"):
#                                 break
#                             try:
#                                 obj = __import__('json').loads(raw)
#                                 chunk = obj.get('choices', [])[0].get('delta', {}).get('content', '') or ''
#                                 if chunk:
#                                     final_text += chunk
#                                     if on_update:
#                                         on_update(chunk)
#                             except Exception:
#                                 continue
#                     finally:
#                         return _post_process(final_text.strip(), user_input)
#                 else:
#                     return f"LLM server error: {resp.status_code}"
#             else:
#                 # Non-streaming path fallback
#                 resp = requests.post(url, json=payload, timeout=timeout_http)
#                 if resp.status_code == 200:
#                     j = resp.json()
#                     text = j.get('choices', [])[0].get('message', {}).get('content', '').strip()
#                     return _post_process(text, user_input)
#                 else:
#                     return f"LLM server error: {resp.status_code}"

#     except Exception as e:
#         _log_debug(f"HTTP server error: {e}")
#         return f"Error: {e}"

# def _post_process(text: str, user_input: str) -> str:
#     if not text: return "(no response)"
#     import re
#     for marker in ["<|im_start|>", "<|im_end|>", "<|start|>", "<|end|>", "[INST]", "[/INST]", "[START]", "[END]"]:
#         text = text.replace(marker, "")
#     lines = []
#     for ln in text.splitlines():
#         ln_strip = ln.strip()
#         if not ln_strip: continue
#         ln_lower = ln_strip.lower()
#         if re.match(r'^(user|assistant|jarvis|nova|memory|q:|a:|loading|generation)\b', ln_lower): continue
#         if re.search(r'\b(user|assistant|jarvis|nova)\s*:', ln_lower): continue
#         lines.append(ln_strip)
#     cleaned = "\n".join(lines).strip()
#     cleaned = re.sub(r'\s+', ' ', cleaned).strip()
#     result = cleaned or text.strip()
#     return result if result else "(no response)"



# import os
# import shutil
# import subprocess
# import requests
# from datetime import datetime
# from dotenv import load_dotenv

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# # Load runtime configuration from .env (if present)
# load_dotenv()

# # Configurable via .env
# MODELS_DIR = os.environ.get("MODELS_DIR", "models")
# LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "sarvam-1-2b-instruct-q8_0.gguf")
# LLM_CONTEXT = int(os.environ.get("LLM_CONTEXT", os.environ.get("LOCAL_LLM_CTX", "2048")))
# LLM_THREADS = int(os.environ.get("LLM_THREADS", os.environ.get("LOCAL_LLM_THREADS", "4")))
# LLM_PORT = int(os.environ.get("LLM_PORT", os.environ.get("LOCAL_LLM_PORT", "8080")))
# LLAMA_BIN_DIR = os.environ.get("LLAMA_BIN_DIR", os.path.join("llama", "bin"))

# MODEL_PATH = os.path.join(BASE_DIR, MODELS_DIR, LLM_MODEL_NAME)
# LLAMA_PATH = os.path.join(BASE_DIR, LLAMA_BIN_DIR)
# API_URL = os.environ.get("LOCAL_LLM_API", f"http://127.0.0.1:{LLM_PORT}")

# def _log_debug(entry: str):
#     try:
#         with open(os.path.join(BASE_DIR, "llama_debug.log"), "a", encoding="utf-8") as fh:
#             fh.write(f"{datetime.now().isoformat()} - {entry}\n")
#     except Exception:
#         pass

# def build_prompt(user_input, memory, conversation_history):
#     identity = "You are Jarvis AI, a concise helpful offline assistant."
#     instruction = "Answer briefly in Hinglish (1-3 sentences). For 'name' questions, answer directly. Do NOT ask back."

#     uname = None
#     try:
#         if memory:
#             uname = memory.get_user_name("default_user")
#     except Exception:
#         uname = None

#     convo_lines = []
#     if conversation_history:
#         for msg in (conversation_history or [])[-6:]:
#             role = msg.get("role", "user")
#             text = (msg.get("text", "") or "").strip()
#             if not text or len(text) > 800:
#                 continue
#             import re
#             if re.search(r"\bmemory\b|saved memory|q:\s|a:\s|\<\|im_start\|\>", text, flags=re.IGNORECASE):
#                 continue
#             text = " ".join(text.split())
#             convo_lines.append(f"{role.capitalize()}: {text}")

#     conv_block = "\n".join(convo_lines)
#     name_line = f"User name: {uname}\n" if uname else ""

#     prompt = identity + "\n" + instruction + "\n" + name_line
#     if conv_block:
#         prompt += "\nRecent conversation:\n" + conv_block + "\n"

#     prompt += f"\nUser: {user_input}\nJarvis:"
#     return prompt

# def build_system_context(user_input, memory, conversation_history):
#     uname = None
#     try:
#         if memory:
#             uname = memory.get_user_name("default_user")
#     except Exception:
#         uname = None

#     base = "You are Jarvis, a helpful AI. Answer in simple Hinglish. Keep it extremely concise and do not repeat yourself."
#     if uname:
#         base = f"{base} The user's name is {uname}."
#     return base

# def _find_llama_executable():
#     candidates = [
#         os.path.join(LLAMA_PATH, "llama-server-cpu.exe"),
#         os.path.join(LLAMA_PATH, "llama-server.exe"),
#         os.path.join(LLAMA_PATH, "llama-cli.exe"),
#         os.path.join(LLAMA_PATH, "llama.exe"),
#     ]
#     for p in candidates:
#         if os.path.exists(p):
#             return p
#     for name in ("llama-server-cpu.exe", "llama-server.exe", "llama-cli", "llama"):
#         which = shutil.which(name)
#         if which:
#             return which
#     return None

# # NAYA CHANGE: stop_event parameter add kiya gaya hai
# def ask_llm(user_input, memory=None, conversation_history=None, on_update=None, stop_event=None):
#     lower = (user_input or "").lower()
#     forbidden = ["hack", "password", "steal", "crack", "exploit", "ddos", "illegal", "bypass", "phish"]
#     if any(tok in lower for tok in forbidden):
#         return "Mujhe maaf kijiye, main illegal kamo me madad nahi kar sakta."

#     prompt = build_prompt(user_input, memory, conversation_history)
#     system_context = build_system_context(user_input, memory, conversation_history)

#     try:
#         timeout_http = int(os.environ.get("LOCAL_LLM_HTTP_TIMEOUT", "20"))
#         use_chat_api = os.environ.get("LOCAL_LLM_USE_CHAT_API", "1") in ("1", "true", "True")

#         if use_chat_api:
#             payload = {
#                 "model": os.environ.get("LLM_MODEL_NAME", ""),
#                 "messages": [
#                     {"role": "system", "content": system_context},
#                     {"role": "user", "content": user_input}
#                 ],
#                 "max_tokens": 512,
#                 "temperature": 0.2, # Low temp = less hallucination
#                 "top_p": 0.9,
#                 "frequency_penalty": 1.15, # Ye naya penalty isko ek baat baar-baar bolne se rokega
#                 "stop": ["User:", "Assistant:", "<|im_end|>", "</s>", "\n\nUser:"] # Strict Stops
#             }
#             stream_enabled = os.environ.get("LOCAL_LLM_STREAM", "1") in ("1", "true", "True")
#             url = API_URL.rstrip('/') + "/v1/chat/completions"
#             if stream_enabled:
#                 payload["stream"] = True
#                 try:
#                     resp = requests.post(url, json=payload, timeout=timeout_http, stream=True)
#                 except Exception as e:
#                     return f"Server Error: {e}"

#                 if resp is not None and resp.status_code == 200:
#                     final_text = ""
#                     try:
#                         for line in resp.iter_lines(decode_unicode=True):
#                             # NAYA CHANGE: STOP BUTTON DABA TOH LOOP TOD DO!
#                             if stop_event and stop_event.is_set():
#                                 resp.close()
#                                 if on_update: on_update("\n[STOPPED BY USER]")
#                                 break

#                             if not line: continue
#                             raw = line.decode('utf-8') if isinstance(line, bytes) else line
#                             if raw.strip().startswith("data: "):
#                                 raw = raw.split("data: ", 1)[1]
#                             if raw.strip() in ("[DONE]", "[done]"):
#                                 break
#                             try:
#                                 obj = __import__('json').loads(raw)
#                                 chunk = obj.get('choices', [])[0].get('delta', {}).get('content', '') or ''
#                                 if chunk:
#                                     final_text += chunk
#                                     if on_update:
#                                         on_update(chunk)
#                             except Exception:
#                                 continue
#                     finally:
#                         return _post_process(final_text.strip(), user_input)
#                 else:
#                     return f"LLM server error: {resp.status_code}"

#     except Exception as e:
#         _log_debug(f"HTTP server error: {e}")
#         return f"Error: {e}"

# def _post_process(text: str, user_input: str) -> str:
#     if not text: return "(no response)"
#     import re
#     for marker in ["<|im_start|>", "<|im_end|>", "<|start|>", "<|end|>", "[INST]", "[/INST]", "[START]", "[END]"]:
#         text = text.replace(marker, "")
#     lines = []
#     for ln in text.splitlines():
#         ln_strip = ln.strip()
#         if not ln_strip: continue
#         ln_lower = ln_strip.lower()
#         if re.match(r'^(user|assistant|jarvis|nova|memory|q:|a:|loading|generation)\b', ln_lower): continue
#         if re.search(r'\b(user|assistant|jarvis|nova)\s*:', ln_lower): continue
#         lines.append(ln_strip)
#     cleaned = "\n".join(lines).strip()
#     cleaned = re.sub(r'\s+', ' ', cleaned).strip()
#     result = cleaned or text.strip()
#     return result if result else "(no response)"










# import os
# import shutil
# import subprocess
# import requests
# from datetime import datetime
# from dotenv import load_dotenv

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# # Load runtime configuration from .env (if present)
# load_dotenv()

# # Configurable via .env
# MODELS_DIR = os.environ.get("MODELS_DIR", "models")
# LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "sarvam-1-2b-instruct-q8_0.gguf")
# LLM_CONTEXT = int(os.environ.get("LLM_CONTEXT", os.environ.get("LOCAL_LLM_CTX", "2048")))
# LLM_THREADS = int(os.environ.get("LLM_THREADS", os.environ.get("LOCAL_LLM_THREADS", "4")))
# LLM_PORT = int(os.environ.get("LLM_PORT", os.environ.get("LOCAL_LLM_PORT", "8080")))
# LLAMA_BIN_DIR = os.environ.get("LLAMA_BIN_DIR", os.path.join("llama", "bin"))

# MODEL_PATH = os.path.join(BASE_DIR, MODELS_DIR, LLM_MODEL_NAME)
# LLAMA_PATH = os.path.join(BASE_DIR, LLAMA_BIN_DIR)
# # default HTTP API base URL (can be overridden by LOCAL_LLM_API)
# # Keep base URL only; endpoints appended where needed.
# API_URL = os.environ.get("LOCAL_LLM_API", f"http://127.0.0.1:{LLM_PORT}")


# def _log_debug(entry: str):
#     try:
#         with open(os.path.join(BASE_DIR, "llama_debug.log"), "a", encoding="utf-8") as fh:
#             fh.write(f"{datetime.now().isoformat()} - {entry}\n")
#     except Exception:
#         pass


# def build_prompt(user_input, memory, conversation_history):
#     """Build a compact prompt including recent sanitized conversation and known user name.

#     This is used for CLI/python-binding backends. Keep it short to avoid context overflow.
#     """
#     import re

#     identity = "You are Jarvis AI, a concise helpful offline assistant."
#     instruction = "Answer briefly in Hinglish (1-3 sentences). For 'name' questions, answer directly. Do NOT ask back."

#     # include known user name from memory if available
#     uname = None
#     try:
#         if memory:
#             uname = memory.get_user_name("default_user")
#     except Exception:
#         uname = None

#     convo_lines = []
#     if conversation_history:
#         # take last 6 messages
#         for msg in (conversation_history or [])[-6:]:
#             role = msg.get("role", "user")
#             text = (msg.get("text", "") or "").strip()
#             if not text:
#                 continue
#             # skip overly long memory dumps or explicit 'memory' markers
#             if len(text) > 800:
#                 continue
#             if re.search(r"\bmemory\b|saved memory|q:\s|a:\s|\<\|im_start\|\>", text, flags=re.IGNORECASE):
#                 continue
#             # collapse newlines
#             text = " ".join(text.split())
#             convo_lines.append(f"{role.capitalize()}: {text}")

#     conv_block = "\n".join(convo_lines)

#     name_line = f"User name: {uname}\n" if uname else ""

#     prompt = identity + "\n" + instruction + "\n" + name_line
#     if conv_block:
#         prompt += "\nRecent conversation:\n" + conv_block + "\n"

#     prompt += f"\nUser: {user_input}\nJarvis:"
#     return prompt


# def build_system_context(user_input, memory, conversation_history):
#     """System context for chat API. Include known user name so the model can personalise replies."""
#     uname = None
#     try:
#         if memory:
#             uname = memory.get_user_name("default_user")
#     except Exception:
#         uname = None

#     base = "You are Jarvis, a helpful offline AI. Answer in simple Hinglish (1-3 sentences). For 'what is your name' or 'what is my name', answer directly. Do NOT make up stories or ask back."
#     if uname:
#         base = f"{base} The user's name is {uname}. Remember and use it when helpful."
#     return base


# def _find_llama_executable():
#     # LLAMA_PATH now points to the bin directory; look for common server/binary names
#     candidates = [
#         os.path.join(LLAMA_PATH, "llama-server-cpu.exe"),
#         os.path.join(LLAMA_PATH, "llama-server.exe"),
#         os.path.join(LLAMA_PATH, "llama-cli.exe"),
#         os.path.join(LLAMA_PATH, "llama.exe"),
#         os.path.join(LLAMA_PATH, "llama-cli"),
#         os.path.join(LLAMA_PATH, "llama")
#     ]

#     for p in candidates:
#         if os.path.exists(p):
#             return p

#     # fallback to PATH
#     for name in ("llama-server-cpu.exe", "llama-server.exe", "llama-cli", "llama"):
#         which = shutil.which(name)
#         if which:
#             return which

#     return None


# def ask_llm(user_input, memory=None, conversation_history=None, on_update=None):
#     # Safety filter: refuse to assist with illegal, hacking, or privacy-invading requests
#     lower = (user_input or "").lower()
#     forbidden = ["hack", "password", "steal", "crack", "exploit", "ddos", "illegal", "bypass", "phish"]
#     if any(tok in lower for tok in forbidden):
#         return ("Mujhe maaf kijiye, main aise illegal ya harmful kaamon mein madad nahin kar sakta. "
#                 "Kuch aur poochiye — main short aur helpful Hinglish mein jawab dunga.")

#     prompt = build_prompt(user_input, memory, conversation_history)
#     system_context = build_system_context(user_input, memory, conversation_history)

#     # 1) Try local HTTP server (fast if you run a llama server)
#     try:
#         timeout_http = int(os.environ.get("LOCAL_LLM_HTTP_TIMEOUT", "20"))
#         use_chat_api = os.environ.get("LOCAL_LLM_USE_CHAT_API", "1") in ("1", "true", "True")

#         if use_chat_api:
#             # Use chat completion endpoint with messages for clearer behavior
#             payload = {
#                 "model": os.environ.get("LLM_MODEL_NAME", ""),
#                 "messages": [
#                     {"role": "system", "content": system_context},
#                     {"role": "user", "content": user_input}
#                 ],
#                 "max_tokens": int(os.environ.get("LOCAL_LLM_MAX_OUTPUT", "150")),
#                 "temperature": float(os.environ.get("LOCAL_LLM_TEMP", "0.1")),
#                 "top_p": float(os.environ.get("LOCAL_LLM_TOPP", "0.7")),
#                 "stop": ["User:", "Assistant:"]
#             }
#             stream_enabled = os.environ.get("LOCAL_LLM_STREAM", "1") in ("1", "true", "True")
#             url = API_URL.rstrip('/') + "/v1/chat/completions"
#             if stream_enabled:
#                 payload["stream"] = True
#                 try:
#                     resp = requests.post(url, json=payload, timeout=timeout_http, stream=True)
#                 except Exception as e:
#                     _log_debug(f"HTTP stream error: {e}")
#                     resp = None

#                 if resp is not None and resp.status_code == 200:
#                     final_text = ""
#                     try:
#                         for line in resp.iter_lines(decode_unicode=True):
#                             if not line:
#                                 continue
#                             raw = line.decode('utf-8') if isinstance(line, bytes) else line
#                             if raw.strip().startswith("data: "):
#                                 raw = raw.split("data: ", 1)[1]
#                             if raw.strip() in ("[DONE]", "[done]"):
#                                 break
#                             try:
#                                 obj = None
#                                 try:
#                                     obj = __import__('json').loads(raw)
#                                 except Exception:
#                                     obj = None
#                                 chunk = ""
#                                 if obj:
#                                     try:
#                                         chunk = obj.get('choices', [])[0].get('delta', {}).get('content', '') or ''
#                                     except Exception:
#                                         chunk = ''
#                                 else:
#                                     chunk = raw
#                                 if chunk:
#                                     final_text += chunk
#                                     if on_update:
#                                         try:
#                                             on_update(chunk)
#                                         except Exception:
#                                             pass
#                             except Exception:
#                                 continue
#                     finally:
#                         text = final_text.strip()
#                         return _post_process(text, user_input)
#                 else:
#                     if resp is not None:
#                         body = resp.text or ''
#                         _log_debug(f"HTTP server returned status {resp.status_code}: {body}")
#                         if resp.status_code == 400 and "exceeds the available context size" in (body or ""):
#                             return ("LLM server rejected the request because the prompt is larger than the server's context (e.g. 512). "
#                                     "Restart the llama server with a larger context (example: `llama-server-cpu.exe -m <model> -c 2048`) "
#                                     "or reduce the uploaded document / conversation history.")
#                         return f"LLM server error: {resp.status_code}"
#                     else:
#                         pass

#             # non-streaming path
#             resp = requests.post(url, json=payload, timeout=timeout_http)
#             if resp.status_code == 200:
#                 j = resp.json()
#                 text = ""
#                 try:
#                     text = j.get('choices', [])[0].get('message', {}).get('content', '')
#                 except Exception:
#                     text = j.get('content', '') or ''
#                 text = (text or '').strip()
#                 return _post_process(text, user_input)
#             else:
#                 body = resp.text or ''
#                 _log_debug(f"HTTP server returned status {resp.status_code}: {body}")
#                 if resp.status_code == 400 and "exceeds the available context size" in (body or ""):
#                     return ("LLM server rejected the request because the prompt is larger than the server's context (e.g. 512). "
#                             "Restart the llama server with a larger context (example: `llama-server-cpu.exe -m <model> -c 2048`) "
#                             "or reduce the uploaded document / conversation history.")
#                 return f"LLM server error: {resp.status_code}"
#         else:
#             resp = requests.post(
#                 API_URL,
#                 json={
#                     "prompt": prompt,
#                     "n_predict": int(os.environ.get("LOCAL_LLM_N", "150")),
#                     "temperature": float(os.environ.get("LOCAL_LLM_TEMP", "0.1")),
#                     "top_p": float(os.environ.get("LOCAL_LLM_TOPP", "0.7")),
#                     "stop": ["User:", "user:", "Assistant:", "assistant:"]
#                 },
#                 timeout=timeout_http,
#             )
#             if resp.status_code == 200:
#                 text = resp.json().get("content", "").strip()
#                 return _post_process(text, user_input)
#             else:
#                 body = resp.text or ''
#                 _log_debug(f"HTTP server returned status {resp.status_code}: {body}")
#                 if resp.status_code == 400 and "exceeds the available context size" in (body or ""):
#                     return ("LLM server rejected the request because the prompt is larger than the server's context (e.g. 512). "
#                             "Restart the llama server with a larger context (example: `llama-server-cpu.exe -m <model> -c 2048`) "
#                             "or reduce the uploaded document / conversation history.")
#                 return f"LLM server error: {resp.status_code}"
#     except Exception as e:
#         _log_debug(f"HTTP server error: {e}")

#     # 2) Fallback to native llama CLI if available
#     exe = _find_llama_executable()
#     if exe and os.path.exists(MODEL_PATH):
#         for prompt_flag in ("-p", "--prompt"):
#             args = [
#                 exe,
#                 "-m", MODEL_PATH,
#                 prompt_flag, prompt,
#                 "-n", os.environ.get("LOCAL_LLM_N", "64"),
#                 "--temp", os.environ.get("LOCAL_LLM_TEMP", "0.2"),
#                 "--repeat_penalty", os.environ.get("LOCAL_LLM_REPEAT", "1.05"),
#                 "-c", str(LLM_CONTEXT),
#                 "-t", str(LLM_THREADS)
#             ]
#             timeout_seconds = int(os.environ.get("LOCAL_LLM_TIMEOUT", "180"))
#             try:
#                 result = subprocess.run(
#                     args,
#                     capture_output=True,
#                     text=True,
#                     encoding="utf-8",
#                     timeout=timeout_seconds,
#                 )
#             except subprocess.TimeoutExpired:
#                 _log_debug(f"CLI timeout after {timeout_seconds}s. Args: {args}")
#                 return f"LLM call timed out ({timeout_seconds}s)"

#             out = (result.stdout or "").strip()
#             err = (result.stderr or "").strip()
#             if err:
#                 _log_debug(f"CLI run stderr: {err}\nArgs: {args}\nReturncode: {getattr(result,'returncode',None)}")
#             if out:
#                 if "Jarvis:" in out:
#                     out = out.split("Jarvis:")[-1].strip()
#                 return _post_process(out, user_input)
#             if err and "unrecognized" in err.lower():
#                 continue
#             if err:
#                 return f"LLM process error: {err}"

#     # 3) Final fallback: python binding llama_cpp
#     try:
#         import llama_cpp as _llama_cpp  # type: ignore
#         Llama = _llama_cpp.Llama
#         llm = Llama(model_path=MODEL_PATH)
#         gen = llm.create_completion(prompt=prompt, max_tokens=int(os.environ.get("LOCAL_LLM_N","150")), temperature=float(os.environ.get("LOCAL_LLM_TEMP","0.1")), stop=["User:", "Assistant:"])
#         text = gen.get('choices', [{}])[0].get('text', '').strip()
#         if "Jarvis:" in text:
#             text = text.split("Jarvis:")[-1].strip()
#         return _post_process(text, user_input)
#     except Exception as e:
#         _log_debug(f"Python binding error: {e}")
#         return f"No working LLM backend: {e}"


# def _post_process(text: str, user_input: str) -> str:
#     """Clean up model artifacts but keep the full answer (no aggressive truncation).

#     We remove role markers and simple labels, but otherwise return the full text so
#     the UI can decide to show or continue streaming the rest on demand.
#     """
#     if not text:
#         return "(no response)"

#     import re

#     # Remove common markers
#     for marker in ["<|im_start|>", "<|im_end|>", "<|start|>", "<|end|>", "[INST]", "[/INST]", "[START]", "[END]"]:
#         text = text.replace(marker, "")

#     # Remove lines that look like role dumps or repeated labels
#     lines = []
#     for ln in text.splitlines():
#         ln_strip = ln.strip()
#         if not ln_strip:
#             continue
#         ln_lower = ln_strip.lower()
#         if re.match(r'^(user|assistant|jarvis|nova|memory|q:|a:|loading|generation)\b', ln_lower):
#             continue
#         if re.search(r'\b(user|assistant|jarvis|nova)\s*:', ln_lower):
#             continue
#         lines.append(ln_strip)

#     cleaned = "\n".join(lines).strip()

#     # Normalize whitespace but keep the full content length
#     cleaned = re.sub(r'\s+', ' ', cleaned).strip()

#     # If cleaned is empty, fallback to original trimmed text
#     result = cleaned or text.strip()

#     return result if result else "(no response)"


# def validate_model():
#     if not os.path.exists(MODEL_PATH):
#         return False, f"Model file not found at {MODEL_PATH}"
#     exe = _find_llama_executable()
#     if exe:
#         return True, f"Found Llama executable: {exe}"
#     try:
#         import llama_cpp as _  # type: ignore
#         return True, "Found python binding 'llama_cpp'"
#     except Exception:
#         return False, "No Llama executable found and 'llama_cpp' not installed. Or HTTP server not running."
