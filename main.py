from __future__ import annotations
from tkinter import filedialog, Scrollbar
import threading
import time
from datetime import datetime
import re
import customtkinter as ctk
from PIL import Image, ImageSequence
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from audio_utils import listen, speak, stop_tts, is_audio_playing
from automation import get_system_stats, open_application, close_application, play_on_youtube, lock_system
from memory import SQLiteMemory
from local_llm import ask_llm

# ----------------- SYSTEM STATE ----------------- #
conversation_history: list[dict[str, str]] = []
session_vars: dict[str, object] = {}
uploaded_context: str = ""
is_listening: bool = False
history_panel_visible: bool = False
is_processing: bool = False

stop_event = threading.Event()
needs_prefix = False
voice_mode = False
sentence_buffer = ""
load_dotenv()

# ----------------- UI THEME SETUP ----------------- #
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG_COLOR = "#05070f"
PANEL_BG = "#0a0e17"
CARD_BG = "#0b1320"
BORDER_COLOR = "#00e5ff"
TEXT_MAIN = "#e2e8f0"
TEXT_ACCENT = "#00e5ff"
TEXT_WARNING = "#ff3366"
TEXT_OK = "#00ff66"
TEXT_DIM = "#64748b"
TEXT_GOLD = "#ffcc00"

memory = SQLiteMemory()

# ----------------- APP ROOT ----------------- #
app = ctk.CTk()
app.geometry("1100x720")
app.title("NOVA AI CORE - Terminal")
app.configure(fg_color=BG_COLOR)

# ----------------- HELPERS ----------------- #
def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def _clamp_text(s: str, limit: int = 800) -> str:
    s = (s or "").strip()
    if len(s) > limit:
        return s[:limit] + "…"
    return s


def _log_debug(entry: str):
    try:
        with open("llama_debug.log", "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat()} - {entry}\n")
    except Exception:
        pass
    


# ----------------- LAYOUT ARCHITECTURE ----------------- #
sidebar_frame = ctk.CTkFrame(
    app,
    width=300,
    corner_radius=0,
    fg_color=PANEL_BG,
    border_width=1,
    border_color="#1e293b",
)
sidebar_frame.pack(side="left", fill="y", padx=0, pady=0)
sidebar_frame.pack_propagate(False)

main_frame = ctk.CTkFrame(app, corner_radius=0, fg_color="transparent")
main_frame.pack(side="right", fill="both", expand=True)

# ----------------- SIDEBAR HEADER ----------------- #
brand_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
brand_frame.pack(fill="x", padx=20, pady=(25, 10))

title_label = ctk.CTkLabel(
    brand_frame,
    text="N O V A // AI",
    font=("Orbitron", 24, "bold"),
    text_color=TEXT_ACCENT,
)
title_label.pack(anchor="w")

sub_label = ctk.CTkLabel(
    brand_frame,
    text="POWERED BY 89xENGINEERS",
    font=("Consolas", 9, "bold"),
    text_color=TEXT_DIM,
)
sub_label.pack(anchor="w", pady=(0, 20))

avatar_frame = ctk.CTkFrame(
    sidebar_frame,
    width=220,
    height=220,
    corner_radius=15,
    fg_color="#000000",
    border_width=2,
    border_color=BORDER_COLOR,
)
avatar_frame.pack(pady=10)
avatar_frame.pack_propagate(False)

avatar_label = None
avatar_frames = []
try:
    avatar_gif = Image.open("./graphics/Jarvis.gif")
    avatar_frames = [
        ctk.CTkImage(light_image=f.copy().resize((200, 200)), size=(200, 200))
        for f in ImageSequence.Iterator(avatar_gif)
    ]
    avatar_label = ctk.CTkLabel(avatar_frame, image=avatar_frames[0], text="")
    avatar_label.pack(expand=True)
except Exception:
    avatar_label = ctk.CTkLabel(
        avatar_frame,
        text="[ NOVA CORE ]",
        font=("Consolas", 18, "bold"),
        text_color=TEXT_ACCENT,
    )
    avatar_label.pack(expand=True)

status_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
status_frame.pack(fill="x", padx=20, pady=20)

status_title = ctk.CTkLabel(
    status_frame,
    text="SYSTEM STATUS",
    font=("Consolas", 11, "bold"),
    text_color=TEXT_DIM,
)
status_title.pack(anchor="w")

thinking_label = ctk.CTkLabel(
    status_frame,
    text="● IDLE / READY",
    font=("Consolas", 13, "bold"),
    text_color=TEXT_OK,
)
thinking_label.pack(anchor="w", pady=5)

# ----------------- MAIN WINDOW CONTROLS ----------------- #
controls_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
controls_frame.pack(fill="x", padx=20, pady=10)


def create_hud_button(parent, text, command, row, col):
    btn = ctk.CTkButton(
        parent,
        text=text,
        command=command,
        font=("Consolas", 12, "bold"),
        fg_color="#0b1320",
        hover_color="#00334e",
        border_color=BORDER_COLOR,
        border_width=1,
        text_color=TEXT_ACCENT,
        width=120,
        height=40,
    )
    btn.grid(row=row, column=col, padx=5, pady=5)
    return btn


# ----------------- OUTPUT / MESSAGE HANDLING ----------------- #
def add_message(sender: str, text: str):
    chat_display.configure(state="normal")
    time_str = _ts()
    chat_display.insert("end", f"[{time_str}] ", "Time")

    if sender == "You":
        chat_display.insert("end", "USER: ", "You")
        chat_display.insert("end", f"{text}\n\n", "You")
    elif sender == "System":
        chat_display.insert("end", "SYSTEM_ALERT: ", "System")
        chat_display.insert("end", f"{text}\n\n", "System")
    else:
        chat_display.insert("end", "NOVA: ", "NOVA")
        chat_display.insert("end", f"{text}\n\n", "NOVA")

    chat_display.configure(state="disabled")
    chat_display.see("end")


def on_update_partial(chunk: str):
    global needs_prefix, sentence_buffer, voice_mode
    try:
        chat_display.configure(state="normal")
        if needs_prefix:
            chat_display.insert("end", f"[{_ts()}] ", "Time")
            chat_display.insert("end", "NOVA: ", "NOVA")
            needs_prefix = False
        chat_display.insert("end", chunk, "NOVA")
        chat_display.configure(state="disabled")
        chat_display.see("end")

        # --- NEW REAL-TIME VOICE LOGIC ---
        if voice_mode and not stop_event.is_set():
            sentence_buffer += chunk
            if any(p in chunk for p in ['.', '!', '?', '\n']):
                import re
                parts = re.split(r'([.!?\n]+)', sentence_buffer)
                
                if len(parts) > 1:
                    complete_sentence = "".join(parts[:-1]).strip()
                    if complete_sentence:
                        clean_text = complete_sentence.replace('*', '').replace('#', '').replace('_', '')
                        if any(c.isalnum() for c in clean_text):
                            speak(clean_text)  
                    sentence_buffer = parts[-1]  

    except Exception:
        pass


def set_processing(flag: bool):
    global is_processing
    is_processing = flag
    if flag:
        thinking_label.configure(text="● PROCESSING...", text_color=TEXT_GOLD)
        avatar_frame.configure(border_color=TEXT_GOLD, border_width=3)
        send_btn.configure(
            text="STOP [◼]",
            fg_color=TEXT_WARNING,
            hover_color="#cc0044",
            command=stop_generation,
        )
        cont_btn.configure(state="disabled")
    else:
        thinking_label.configure(text="● IDLE / READY", text_color=TEXT_OK)
        avatar_frame.configure(border_color=BORDER_COLOR, border_width=2)
        send_btn.configure(
            text="EXECUTE [➤]",
            fg_color=TEXT_ACCENT,
            text_color="#000000",
            hover_color="#00b3cc",
            command=send_message,
        )
        cont_btn.configure(state="normal")


# ----------------- INPUT / FILE / HISTORY ----------------- #
def toggle_mic():
    global is_listening
    is_listening = not is_listening
    if is_listening:
        mic_btn.configure(fg_color=TEXT_ACCENT, text_color="#000000", text="MIC: ON [🎙]")
        threading.Thread(target=voice_input_loop, daemon=True).start()
    else:
        mic_btn.configure(fg_color="#0b1320", text_color=TEXT_ACCENT, text="MIC: OFF [🎤]")

def toggle_voice_mode():
    global voice_mode 
    voice_mode = not voice_mode

    if voice_mode:
        voice_btn.configure(text="VOICE: ON 🔊", fg_color="#00ffcc")
        add_message("System", "Voice mode activated")
        speak("Voice mode activated")
       
    else:
        voice_btn.configure(text="VOICE: OFF 🔇", fg_color="#0b1320")
        add_message("System", "Voice mode disabled")


def upload_document():
    global uploaded_context
    file_path = filedialog.askopenfilename(
        filetypes=[("Documents", "*.txt *.pdf"), ("Images", "*.png *.jpg *.jpeg")]
    )
    if not file_path:
        return
    try:
        if file_path.lower().endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                uploaded_context = f.read()[:1500]
        elif file_path.lower().endswith(".pdf"):
            reader = PdfReader(file_path)
            content = "\n".join([(p.extract_text() or "") for p in reader.pages])
            uploaded_context = content[:1500]
        else:
            uploaded_context = f"[File uploaded: {file_path}]"
        add_message("System", f"Loaded context from: {file_path.split('/')[-1]}")
    except Exception as e:
        add_message("System", f"File load error: {e}")


def clear_chat_history_ui():
    global conversation_history, uploaded_context
    try:
        conversation_history.clear()
        uploaded_context = ""
        chat_display.configure(state="normal")
        chat_display.delete("1.0", "end")
        chat_display.configure(state="disabled")
        try:
            if hasattr(memory, "conn"):
                cur = memory.conn.cursor()
                cur.execute("DELETE FROM memory WHERE user_id = ?", ("default_user",))
                memory.conn.commit()
        except Exception:
            pass
        add_message("System", "Terminal buffer and database wiped successfully.")
    except Exception as e:
        add_message("System", f"Clear error: {e}")


def toggle_history_panel():
    global history_panel_visible
    history_panel_visible = not history_panel_visible
    if history_panel_visible:
        history_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        load_chat_history()
    else:
        history_frame.pack_forget()


# ----------------- SAFE BUTTONS ----------------- #
mic_btn = create_hud_button(controls_frame, "MIC: OFF [🎤]", toggle_mic, 0, 0)
voice_btn = create_hud_button(controls_frame, "VOICE: OFF 🔇", toggle_voice_mode, 2, 0)
upload_btn = create_hud_button(controls_frame, "UPLOAD [📄]", upload_document, 0, 1)
mem_btn = create_hud_button(controls_frame, "MEMORY [🧠]", toggle_history_panel, 1, 0)
clear_btn = create_hud_button(controls_frame, "PURGE [🗑️]", clear_chat_history_ui, 1, 1)

# ----------------- CHAT DISPLAY ----------------- #
chat_container = ctk.CTkFrame(main_frame, fg_color="transparent")
chat_container.pack(fill="both", expand=True, padx=20, pady=(20, 10))

term_header = ctk.CTkFrame(chat_container, fg_color="transparent")
term_header.pack(anchor="w", fill="x", pady=(0, 5))
ctk.CTkLabel(
    term_header,
    text=">_ SECURE TERMINAL OUTPUT",
    font=("Consolas", 12, "bold"),
    text_color="#475569",
).pack(anchor="w")

chat_frame = ctk.CTkFrame(
    chat_container,
    corner_radius=10,
    fg_color="#0a0e17",
    border_width=1,
    border_color="#1e293b",
)
chat_frame.pack(fill="both", expand=True)

chat_display = ctk.CTkTextbox(
    chat_frame,
    font=("Segoe UI", 14),
    wrap="word",
    fg_color="transparent",
    text_color=TEXT_MAIN,
)
chat_display.pack(side="left", fill="both", expand=True, padx=15, pady=15)

scroll = Scrollbar(chat_frame, command=chat_display.yview)
chat_display.configure(yscrollcommand=scroll.set)
scroll.pack(side="right", fill="y", pady=15, padx=(0, 10))
chat_display.configure(state="disabled")

chat_display.tag_config("You", foreground="#ffffff")
chat_display.tag_config("NOVA", foreground=TEXT_ACCENT)
chat_display.tag_config("System", foreground=TEXT_WARNING)
chat_display.tag_config("Time", foreground="#475569")

# ----------------- INPUT AREA ----------------- #
input_container = ctk.CTkFrame(main_frame, fg_color="transparent")
input_container.pack(fill="x", padx=20, pady=(0, 20))

input_frame = ctk.CTkFrame(
    input_container,
    fg_color="#0a0e17",
    corner_radius=10,
    border_width=1,
    border_color="#1e293b",
)
input_frame.pack(fill="x", ipady=5)

message_entry = ctk.CTkEntry(
    input_frame,
    placeholder_text="Enter command protocol here...",
    font=("Consolas", 14),
    fg_color="transparent",
    border_width=0,
    text_color="#ffffff",
)
message_entry.pack(side="left", fill="x", expand=True, padx=15, pady=10)


# ----------------- HISTORY PANEL ----------------- #
history_frame = ctk.CTkFrame(
    main_frame,
    corner_radius=10,
    fg_color="#070a13",
    border_width=1,
    border_color=TEXT_WARNING,
)
history_display = ctk.CTkTextbox(
    history_frame,
    wrap="word",
    font=("Consolas", 12),
    fg_color="transparent",
    text_color="#94a3b8",
)
history_display.pack(fill="both", expand=True, padx=15, pady=15)
history_display.configure(state="disabled")


def load_chat_history():
    try:
        history_display.configure(state="normal")
        history_display.delete("1.0", "end")
        memories = []
        try:
            memories = memory.get_chat_history("default_user", 50)
        except Exception:
            try:
                cur = memory.conn.cursor()
                cur.execute(
                    "SELECT query, response, timestamp FROM memory WHERE user_id = ? ORDER BY rowid DESC LIMIT 50",
                    ("default_user",),
                )
                memories = cur.fetchall()
            except Exception:
                memories = []

        history_display.insert("end", "=== SECURE MEMORY ARCHIVE ===\n\n")
        if not memories:
            history_display.insert("end", "No memories found.\n")
        else:
            for m in memories:
                try:
                    q, r, t = m[0], m[1], (m[2] if len(m) > 2 else "")
                    history_display.insert(
                        "end",
                        f"[{t}] USER: {_clamp_text(q, 250)}\nNOVA: {_clamp_text(r, 350)}\n{'-' * 40}\n",
                    )
                except Exception:
                    pass
        history_display.configure(state="disabled")
        history_display.see("end")
    except Exception as e:
        add_message("System", f"History load error: {e}")


# ----------------- CORE LLM ROUTING ----------------- #
def _build_recent_conversation_block() -> str:
    recent_convo = ""
    for msg in conversation_history[-8:]:
        role = msg.get("role", "user")
        text = (msg.get("text", "") or "").strip()[:200]
        if text and len(text) > 3:
            recent_convo += f"{role.upper()}: {text}\n"
    return recent_convo


def stop_generation():
    stop_event.set()
    stop_tts() 
    add_message("System", "Generation halted by user override.")


def continue_last():
    if not conversation_history:
        add_message("NOVA", "No previous response to continue.")
        return
    followup = (
        "Please continue the previous answer. Continue where you left off and do not repeat the already given text."
    )
    conversation_history.append({"role": "user", "text": followup})
    threading.Thread(target=lambda: _continue_worker(followup, on_update_partial), daemon=True).start()


cont_btn = ctk.CTkButton(
    input_frame,
    text="CONTINUE [⟳]",
    width=100,
    command=continue_last,
    font=("Consolas", 12, "bold"),
    fg_color="transparent",
    border_width=1,
    border_color="#475569",
    hover_color="#1e293b",
)
cont_btn.pack(side="left", padx=(0, 10))

send_btn = ctk.CTkButton(
    input_frame,
    text="EXECUTE [➤]",
    width=120,
    command=None,
    font=("Consolas", 12, "bold"),
    fg_color=TEXT_ACCENT,
    text_color="#000000",
    hover_color="#00b3cc",
)
send_btn.pack(side="right", padx=(0, 15))


# ----------------- MAIN FLOW ----------------- #
def send_message():
    global is_processing
    if is_processing:
        return
    msg = message_entry.get().strip()
    if not msg:
        return
    add_message("You", msg)
    message_entry.delete(0, "end")
    threading.Thread(target=process_message, args=(msg,), daemon=True).start()


send_btn.configure(command=send_message)

def process_message(message: str):
    # NAYA: yahan sentence_buffer add kiya hai
    global uploaded_context, conversation_history, needs_prefix, session_vars, voice_mode, sentence_buffer
    try:
        stop_event.clear()
        set_processing(True)
        needs_prefix = True
        sentence_buffer = "" 

        msg_lower = (message or "").strip().lower()

        # ===== AUTOMATION HANDLERS =====
        
        # 1. System Status
        if "system status" in msg_lower or "battery" in msg_lower:
            response = get_system_stats()
            add_message("NOVA", response)
            conversation_history.append({"role": "user", "text": message})
            conversation_history.append({"role": "assistant", "text": response})
            if voice_mode:
                speak(response)
            return
            
        # 2. App Launcher (Dynamic)
        if msg_lower.startswith("open "):
            app_to_open = msg_lower.replace("open ", "")
            response = open_application(app_to_open)
            
            add_message("NOVA", response)
            conversation_history.append({"role": "user", "text": message})
            conversation_history.append({"role": "assistant", "text": response})
            if voice_mode:
                speak(response)
            return

        # BONUS: App Closer (Dynamic)
        if msg_lower.startswith("close "):
            app_to_close = msg_lower.replace("close ", "")
            response = close_application(app_to_close)
            
            add_message("NOVA", response)
            conversation_history.append({"role": "user", "text": message})
            conversation_history.append({"role": "assistant", "text": response})
            if voice_mode:
                speak(response)
            return

        # 3. YouTube Play
        if "play" in msg_lower and "youtube" in msg_lower:
            response = play_on_youtube(msg_lower)
            add_message("NOVA", response)
            if voice_mode:
                speak(response)
            return
            
        # 4. System Lock
        if "lock pc" in msg_lower or "lock system" in msg_lower:
            response = lock_system()
            add_message("NOVA", response)
            if voice_mode:
                speak(response)
            return
        
        # ===== NAME MEMORY =====
        if re.search(r"\b(what\s+is\s+my\s+name|who\s+am\s+i|my\s+name\s+is\s+what)\b", msg_lower, flags=re.IGNORECASE):
            try:
                stored_name = memory.get_user_name("default_user")
            except Exception:
                stored_name = None

            if stored_name:
                add_message("NOVA", f"Your name is {stored_name}.")
            else:
                add_message("NOVA", "I don't know your name yet. Please tell me your name.")

            conversation_history.append({"role": "user", "text": message})
            conversation_history.append({"role": "assistant", "text": stored_name or "(unknown)"})
            return

        # ===== SAVE NAME =====
        if not re.search(r"\bwhat\b", msg_lower):
            m = re.search(r"\bmy name is ([A-Za-z0-9_\-]+)\b", msg_lower, flags=re.IGNORECASE)
            if not m:
                m = re.search(r"\bi am ([A-Za-z0-9_\-]+)\b", msg_lower, flags=re.IGNORECASE)

            if m:
                name = m.group(1).strip()
                try:
                    memory.set_user_name("default_user", name)
                except Exception:
                    pass

                add_message("NOVA", f"Thik hai, {name}! I've noted that.")
                conversation_history.append({"role": "user", "text": message})
                conversation_history.append({"role": "assistant", "text": f"Remembered: {name}"})
                return

        # ===== VARIABLE SET =====
        m_var = re.match(r"^\s*([a-zA-Z]\w*)\s*=\s*([+-]?\d+(?:\.\d+)?)\s*$", message)
        if m_var:
            var = m_var.group(1)
            val = float(m_var.group(2)) if "." in m_var.group(2) else int(m_var.group(2))

            session_vars[var] = val
            add_message("NOVA", f"Set {var} = {val}")

            conversation_history.append({"role": "user", "text": message})
            conversation_history.append({"role": "assistant", "text": f"Set {var} = {val}"})
            return

        # ===== MATH SOLVER =====
        m_expr = re.search(
            r"([a-zA-Z]\w*(?:\s*[+\-*/]\s*[a-zA-Z]\w*)+)(?:\s*=\s*\?|\?)",
            message,
            flags=re.IGNORECASE,
        )
        if m_expr:
            expr_raw = m_expr.group(1).replace(" ", "")
            expr = expr_raw

            for v in list(session_vars.keys()):
                expr = re.sub(rf"\b{v}\b", str(session_vars[v]), expr)

            try:
                if re.match(r"^[0-9+\-*/(). ]+$", expr):
                    result = eval(expr)

                    add_message("NOVA", f"{expr_raw} = {result}")
                    conversation_history.append({"role": "user", "text": message})
                    conversation_history.append({"role": "assistant", "text": str(result)})
                    return
            except Exception:
                pass

        # ===== SEND TO LLM =====
        context_block = ""
        if uploaded_context:
            # Explicitly tell the LLM this is a document to read
            context_block = f"--- UPLOADED DOCUMENT CONTENT (Read this carefully) ---\n{uploaded_context}\n----------------------------------------------------\n\n"

        recent_convo = _build_recent_conversation_block()

        if recent_convo:
            prompt = f"{context_block}RECENT CONTEXT:\n{recent_convo}\nUser Question: {message}"
        else:
            prompt = f"{context_block}User Question: {message}"

        conversation_history.append({"role": "user", "text": message})

        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]

        response = ask_llm(
            prompt,
            memory,
            conversation_history,
            on_update=on_update_partial,
            stop_event=stop_event,
        )

        # 🔥 VOICE OUTPUT
        if voice_mode and sentence_buffer.strip() and not stop_event.is_set():
            clean_text = sentence_buffer.strip().replace('*', '').replace('#', '').replace('_', '')
            if any(c.isalnum() for c in clean_text):
                speak(clean_text)
            sentence_buffer = ""

        # ====================================================
        # NAYA FIX: Audio khatam hone tak STOP button ko roke rakhna
        # ====================================================
        if voice_mode:
            while is_audio_playing() and not stop_event.is_set():
                time.sleep(0.2)
                
        # ===== ERROR HANDLING =====
        if not response or response.startswith("Error:") or response.startswith("Connection"):
            if not response:
                response = "I'm having trouble responding. Please try again."
            add_message("System", response)
        elif needs_prefix:
            add_message("NOVA", response)

        # ===== UI CLEAN =====
        chat_display.configure(state="normal")
        chat_display.insert("end", "\n\n")
        chat_display.configure(state="disabled")

        conversation_history.append({"role": "assistant", "text": response})

        resp_clean = (response or "").strip()
        if resp_clean and len(resp_clean) > 5:
            try:
                memory.save_memory("default_user", message, resp_clean)
            except Exception:
                pass

    except Exception as e:
        add_message("System", f"Error: {e}")

    finally:
        set_processing(False)

def _continue_worker(followup_text: str, on_update_cb):
    global needs_prefix
    try:
        stop_event.clear()
        set_processing(True)
        needs_prefix = True
        response = ask_llm(
            followup_text,
            memory,
            conversation_history,
            on_update=on_update_cb,
            stop_event=stop_event,
        )

        if response and any(
            response.startswith(e)
            for e in ["Error:", "Server Error", "Connection Error", "LLM server error"]
        ):
            add_message("System", "Connection error. Please try again.")

        chat_display.configure(state="normal")
        chat_display.insert("end", "\n\n")
        chat_display.configure(state="disabled")
        conversation_history.append({"role": "assistant", "text": response})
        try:
            if response and len(response) > 5:
                memory.save_memory("default_user", "(continued)", response)
        except Exception:
            pass
    except Exception as e:
        add_message("System", f"Error: {e}")
    finally:
        set_processing(False)


# ----------------- VOICE ----------------- #
def voice_input_loop():
    global is_listening 

    while is_listening:
        try:
            cmd = listen()
            if not cmd:
                continue
            add_message("You", cmd)
            process_message(cmd)

        except Exception as e:
            add_message("System", f"Voice error: {e}")

        time.sleep(0.2)
message_entry.bind("<Return>", lambda e: send_message())

# ----------------- ANIMATIONS ----------------- #
def animate_avatar(idx: int = 0):
    if avatar_frames:
        try:
            avatar_label.configure(image=avatar_frames[idx])
        except Exception:
            pass
        app.after(80, animate_avatar, (idx + 1) % len(avatar_frames))
    else:
        # subtle pulse for fallback label
        try:
            current = avatar_frame.cget("border_color")
            next_color = TEXT_GOLD if current == BORDER_COLOR else BORDER_COLOR
            avatar_frame.configure(border_color=next_color)
        except Exception:
            pass
        app.after(700, animate_avatar, 0)


def animate_status_pulse():
    try:
        if is_processing:
            current = thinking_label.cget("text_color")
            thinking_label.configure(text_color=TEXT_WARNING if current != TEXT_WARNING else TEXT_GOLD)
            avatar_frame.configure(border_color=TEXT_GOLD if current != TEXT_GOLD else TEXT_WARNING)
        elif is_listening:
            current = thinking_label.cget("text_color")
            thinking_label.configure(text_color=TEXT_ACCENT if current != TEXT_ACCENT else TEXT_OK)
    except Exception:
        pass
    app.after(500, animate_status_pulse)


# ----------------- STARTUP ----------------- #
if __name__ == "__main__":
    add_message("System", "NOVA CORE SYSTEMS INITIALIZED. WAITING FOR PROTOCOL.")
    animate_avatar()
    animate_status_pulse()
    app.mainloop()







# woking ui
# from tkinter import filedialog
# import customtkinter as ctk
# import threading
# import time
# from datetime import datetime
# from PIL import Image, ImageSequence
# from dotenv import load_dotenv
# from PyPDF2 import PdfReader

# # Tumhare local imports
# from audio_utils import listen, speak
# from memory import SQLiteMemory
# from local_llm import ask_llm  

# # ----------------- SYSTEM STATE ----------------- #
# conversation_history = []
# session_vars = {}
# uploaded_context = ""
# is_listening = False
# history_panel_visible = False
# is_processing = False

# # NAYA: Global Stop Event kill-switch ke liye
# stop_event = threading.Event()
# needs_prefix = False # NAYA: Sahi prefix handle karne ke liye

# load_dotenv()

# # ----------------- UI THEME SETUP ----------------- #
# ctk.set_appearance_mode("dark")
# ctk.set_default_color_theme("blue")

# BG_COLOR = "#05070f"          
# PANEL_BG = "#0a0e17"          
# BORDER_COLOR = "#00e5ff"      
# TEXT_MAIN = "#e2e8f0"         
# TEXT_ACCENT = "#00e5ff"       
# TEXT_WARNING = "#ff3366"      

# memory = SQLiteMemory()

# # Initialize Main Window
# app = ctk.CTk()
# app.geometry("1100x720")
# app.title("NOVA AI CORE - Terminal")
# app.configure(fg_color=BG_COLOR)

# # ========================================================= #
# #                   LAYOUT ARCHITECTURE                     #
# # ========================================================= #

# sidebar_frame = ctk.CTkFrame(app, width=300, corner_radius=0, fg_color=PANEL_BG, border_width=1, border_color="#1e293b")
# sidebar_frame.pack(side="left", fill="y", padx=0, pady=0)
# sidebar_frame.pack_propagate(False) 

# main_frame = ctk.CTkFrame(app, corner_radius=0, fg_color="transparent")
# main_frame.pack(side="right", fill="both", expand=True)

# brand_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
# brand_frame.pack(fill="x", padx=20, pady=(25, 10))

# title_label = ctk.CTkLabel(brand_frame, text="N O V A // AI", font=("Orbitron", 24, "bold"), text_color=TEXT_ACCENT)
# title_label.pack(anchor="w")

# sub_label = ctk.CTkLabel(brand_frame, text="POWERED BY 89xENGINEERS", font=("Consolas", 9, "bold"), text_color="#64748b")
# sub_label.pack(anchor="w", pady=(0, 20))

# avatar_frame = ctk.CTkFrame(sidebar_frame, width=220, height=220, corner_radius=15, fg_color="#000000", border_width=2, border_color=BORDER_COLOR)
# avatar_frame.pack(pady=10)
# avatar_frame.pack_propagate(False)

# try:
#     avatar_gif = Image.open("./graphics/Jarvis.gif") 
#     avatar_frames = [ctk.CTkImage(light_image=f.copy().resize((200, 200)), size=(200, 200)) for f in ImageSequence.Iterator(avatar_gif)]
#     avatar_label = ctk.CTkLabel(avatar_frame, image=avatar_frames[0], text="")
#     avatar_label.pack(expand=True)
    
#     def animate_avatar(idx=0):
#         if not globals().get("stop_avatar", False):
#             avatar_label.configure(image=avatar_frames[idx])
#             app.after(80, animate_avatar, (idx+1) % len(avatar_frames))
#     animate_avatar()
# except Exception:
#     avatar_label = ctk.CTkLabel(avatar_frame, text="[ NOVA CORE ]", font=("Consolas", 18, "bold"), text_color=TEXT_ACCENT)
#     avatar_label.pack(expand=True)

# status_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
# status_frame.pack(fill="x", padx=20, pady=20)

# status_title = ctk.CTkLabel(status_frame, text="SYSTEM STATUS", font=("Consolas", 11, "bold"), text_color="#64748b")
# status_title.pack(anchor="w")

# thinking_label = ctk.CTkLabel(status_frame, text="● IDLE / READY", font=("Consolas", 13, "bold"), text_color="#00ff66")
# thinking_label.pack(anchor="w", pady=5)

# # NAYA CHANGE: set_processing ke andar hum EXECUTE button ko STOP button me convert karenge
# def set_processing(flag: bool):
#     global is_processing
#     is_processing = flag
#     if flag:
#         thinking_label.configure(text="● PROCESSING...", text_color="#ffcc00")
#         avatar_frame.configure(border_color="#ffcc00", border_width=3)
#         # Button becomes STOP
#         send_btn.configure(text="STOP [◼]", fg_color=TEXT_WARNING, hover_color="#cc0044", command=stop_generation)
#         cont_btn.configure(state="disabled")
#     else:
#         thinking_label.configure(text="● IDLE / READY", text_color="#00ff66")
#         avatar_frame.configure(border_color=BORDER_COLOR, border_width=2)
#         # Button reverts to EXECUTE
#         send_btn.configure(text="EXECUTE [➤]", fg_color=TEXT_ACCENT, text_color="#000000", hover_color="#00b3cc", command=send_message)
#         cont_btn.configure(state="normal")

# controls_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
# controls_frame.pack(fill="x", padx=20, pady=10)

# def create_hud_button(parent, text, command, row, col):
#     btn = ctk.CTkButton(
#         parent, text=text, command=command,
#         font=("Consolas", 12, "bold"),
#         fg_color="#0b1320", hover_color="#00334e",
#         border_color=BORDER_COLOR, border_width=1,
#         text_color=TEXT_ACCENT, width=120, height=40
#     )
#     btn.grid(row=row, column=col, padx=5, pady=5)
#     return btn

# def toggle_mic():
#     global is_listening
#     is_listening = not is_listening
#     if is_listening:
#         mic_btn.configure(fg_color=TEXT_ACCENT, text_color="#000000", text="MIC: ON [🎙]")
#         threading.Thread(target=voice_input_loop, daemon=True).start()
#     else:
#         mic_btn.configure(fg_color="#0b1320", text_color=TEXT_ACCENT, text="MIC: OFF [🎤]")

# def upload_document():
#     global uploaded_context
#     file_path = filedialog.askopenfilename(filetypes=[("Documents", "*.txt *.pdf"), ("Images", "*.png *.jpg *.jpeg")])
#     if not file_path:
#         return
#     try:
#         if file_path.lower().endswith(".txt"):
#             with open(file_path, "r", encoding="utf-8") as f:
#                 content = f.read()
#                 # FIXED: Truncate to 1500 chars to avoid context overflow
#                 uploaded_context = content[:1500]
#         elif file_path.lower().endswith(".pdf"):
#             reader = PdfReader(file_path)
#             content = "\n".join([p.extract_text() or "" for p in reader.pages])
#             # FIXED: Truncate to 1500 chars
#             uploaded_context = content[:1500]
#         else:
#             uploaded_context = f"[File uploaded: {file_path}]"
#         add_message("System", f"Loaded context from: {file_path.split('/')[-1]}")
#     except Exception as e:
#         add_message("System", f"File load error: {e}")

# def clear_chat_history_ui():
#     global conversation_history, uploaded_context
#     try:
#         conversation_history.clear()
#         uploaded_context = ""
#         chat_display.configure(state="normal")
#         chat_display.delete("1.0", "end")
#         chat_display.configure(state="disabled")
#         try:
#             if hasattr(memory, "conn"):
#                 cur = memory.conn.cursor()
#                 cur.execute("DELETE FROM memory WHERE user_id = ?", ("default_user",))
#                 memory.conn.commit()
#         except Exception:
#             pass
#         add_message("System", "Terminal buffer and database wiped successfully.")
#     except Exception as e:
#         add_message("System", f"Clear error: {e}")

# def toggle_history_panel():
#     global history_panel_visible
#     history_panel_visible = not history_panel_visible
#     if history_panel_visible:
#         history_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
#         load_chat_history()
#     else:
#         history_frame.pack_forget()

# mic_btn = create_hud_button(controls_frame, "MIC: OFF [🎤]", toggle_mic, 0, 0)
# upload_btn = create_hud_button(controls_frame, "UPLOAD [📄]", upload_document, 0, 1)
# mem_btn = create_hud_button(controls_frame, "MEMORY [🧠]", toggle_history_panel, 1, 0)
# clear_btn = create_hud_button(controls_frame, "PURGE [🗑️]", clear_chat_history_ui, 1, 1)

# chat_container = ctk.CTkFrame(main_frame, fg_color="transparent")
# chat_container.pack(fill="both", expand=True, padx=20, pady=(20, 10))

# term_header = ctk.CTkLabel(chat_container, text=">_ SECURE TERMINAL OUTPUT", font=("Consolas", 12, "bold"), text_color="#475569")
# term_header.pack(anchor="w", pady=(0, 5))

# chat_frame = ctk.CTkFrame(chat_container, corner_radius=10, fg_color="#0a0e17", border_width=1, border_color="#1e293b")
# chat_frame.pack(fill="both", expand=True)

# # FIXED: Use font that supports Hindi/Devanagari UTF-8 characters
# chat_display = ctk.CTkTextbox(chat_frame, font=("Segoe UI", 14), wrap="word", fg_color="transparent", text_color=TEXT_MAIN)
# chat_display.pack(side="left", fill="both", expand=True, padx=15, pady=15)

# from tkinter import Scrollbar
# scroll = Scrollbar(chat_frame, command=chat_display.yview)
# chat_display.configure(yscrollcommand=scroll.set)
# scroll.pack(side="right", fill="y", pady=15, padx=(0,10))

# chat_display.configure(state="disabled")

# # Color Tags
# chat_display.tag_config("You", foreground="#ffffff")
# chat_display.tag_config("NOVA", foreground=TEXT_ACCENT)
# chat_display.tag_config("System", foreground=TEXT_WARNING)
# chat_display.tag_config("Time", foreground="#475569")

# def add_message(sender, text):
#     chat_display.configure(state="normal")
#     time_str = datetime.now().strftime("%H:%M:%S")
#     chat_display.insert("end", f"[{time_str}] ", "Time")
    
#     if sender == "You":
#         chat_display.insert("end", "USER: ", "You")
#         chat_display.insert("end", f"{text}\n\n", "You")
#     elif sender == "System":
#         chat_display.insert("end", "SYSTEM_ALERT: ", "System")
#         chat_display.insert("end", f"{text}\n\n", "System")
#     else:
#         chat_display.insert("end", "NOVA: ", "NOVA")
#         chat_display.insert("end", f"{text}\n\n", "NOVA")
        
#     chat_display.configure(state="disabled")
#     chat_display.see("end")

# input_container = ctk.CTkFrame(main_frame, fg_color="transparent")
# input_container.pack(fill="x", padx=20, pady=(0, 20))

# input_frame = ctk.CTkFrame(input_container, fg_color="#0a0e17", corner_radius=10, border_width=1, border_color="#1e293b")
# input_frame.pack(fill="x", ipady=5)

# message_entry = ctk.CTkEntry(
#     input_frame, placeholder_text="Enter command protocol here...", 
#     font=("Consolas", 14), fg_color="transparent", border_width=0, text_color="#ffffff"
# )
# message_entry.pack(side="left", fill="x", expand=True, padx=15, pady=10)

# def send_message():
#     global is_processing
#     if is_processing:
#         return # NAYA: Processing ke waqt multiple enters ko block karega
        
#     msg = message_entry.get().strip()
#     if not msg:
#         return
#     add_message("You", msg)
#     message_entry.delete(0, "end")
#     threading.Thread(target=process_message, args=(msg,), daemon=True).start()

# # NAYA: Stop Generation Handler
# def stop_generation():
#     stop_event.set()
#     add_message("System", "Generation halted by user override.")

# def continue_last():
#     if not conversation_history:
#         add_message("NOVA", "No previous response to continue.")
#         return
#     followup = "Please continue the previous answer. Continue where you left off and do not repeat the already given text."
#     conversation_history.append({"role":"user", "text": followup})
#     threading.Thread(target=lambda: _continue_worker(followup, on_update_partial), daemon=True).start()

# cont_btn = ctk.CTkButton(
#     input_frame, text="CONTINUE [⟳]", width=100, command=continue_last,
#     font=("Consolas", 12, "bold"), fg_color="transparent", border_width=1, border_color="#475569", hover_color="#1e293b"
# )
# cont_btn.pack(side="left", padx=(0, 10))

# send_btn = ctk.CTkButton(
#     input_frame, text="EXECUTE [➤]", width=120, command=send_message,
#     font=("Consolas", 12, "bold"), fg_color=TEXT_ACCENT, text_color="#000000", hover_color="#00b3cc"
# )
# send_btn.pack(side="right", padx=(0, 15))


# history_frame = ctk.CTkFrame(main_frame, corner_radius=10, fg_color="#070a13", border_width=1, border_color=TEXT_WARNING)
# history_display = ctk.CTkTextbox(history_frame, wrap="word", font=("Consolas", 12), fg_color="transparent", text_color="#94a3b8")
# history_display.pack(fill="both", expand=True, padx=15, pady=15)
# history_display.configure(state="disabled")

# def load_chat_history():
#     try:
#         history_display.configure(state="normal")
#         history_display.delete("1.0", "end")
#         memories = []
#         try:
#             memories = memory.get_chat_history("default_user", 50)
#         except Exception:
#             try:
#                 cur = memory.conn.cursor()
#                 cur.execute("SELECT query, response, timestamp FROM memory WHERE user_id = ? ORDER BY rowid DESC LIMIT 50", ("default_user",))
#                 memories = cur.fetchall()
#             except Exception:
#                 memories = []
        
#         history_display.insert("end", "=== SECURE MEMORY ARCHIVE ===\n\n")
#         if not memories:
#             history_display.insert("end", "No memories found.\n")
#         else:
#             for m in memories:
#                 try:
#                     q, r, t = m[0], m[1], (m[2] if len(m) > 2 else "")
#                     history_display.insert("end", f"[{t}] USER: {q}\nNOVA: {r}\n{'-'*40}\n")
#                 except Exception:
#                     pass
#         history_display.configure(state="disabled")
#         history_display.see("end")
#     except Exception as e:
#         add_message("System", f"History load error: {e}")


# def on_update_partial(chunk: str):
#     global needs_prefix
#     try:
#         chat_display.configure(state="normal")
#         if needs_prefix:  
#             time_str = datetime.now().strftime("%H:%M:%S")
#             chat_display.insert("end", f"[{time_str}] ", "Time")
#             chat_display.insert("end", "NOVA: ", "NOVA")
#             needs_prefix = False
            
#         chat_display.insert("end", chunk, "NOVA")
#         chat_display.configure(state="disabled")
#         chat_display.see("end")
#     except Exception:
#         pass

# def process_message(message):
#     global uploaded_context, conversation_history, needs_prefix, session_vars
#     try:
#         stop_event.clear() # Reset state at start
#         set_processing(True)
#         needs_prefix = True
#         import re
#         msg_lower = (message or "").strip()
        
#         # ===== RETRIEVAL HANDLERS (check FIRST before extraction) =====
#         # CHECK: "what is my name?" or "who am i?"
#         if re.search(r"\b(what\s+is\s+my\s+name|who\s+am\s+i|my\s+name\s+is\s+what)\b", msg_lower, flags=re.IGNORECASE):
#             try:
#                 stored_name = memory.get_user_name("default_user")
#             except Exception:
#                 stored_name = None
#             if stored_name:
#                 add_message("NOVA", f"Your name is {stored_name}.")
#             else:
#                 add_message("NOVA", "I don't know your name yet. Please tell me your name.")
#             conversation_history.append({"role":"user","text":message})
#             conversation_history.append({"role":"assistant","text":stored_name or "(unknown)"})
#             set_processing(False)
#             return
        
#         # CHECK: "what is my friend name?" or "friend's name?"
#         if re.search(r"\b(what\s+is\s+my\s+friend|friend'?s?\s+name|my\s+friend\s+name\s+is\s+what)\b", msg_lower, flags=re.IGNORECASE):
#             friend_stored = session_vars.get("friend_name", None)
#             if friend_stored:
#                 add_message("NOVA", f"Your friend's name is {friend_stored}.")
#                 response_text = friend_stored
#             else:
#                 add_message("NOVA", "You haven't told me your friend's name yet.")
#                 response_text = "(unknown)"
#             conversation_history.append({"role":"user","text":message})
#             conversation_history.append({"role":"assistant","text":response_text})
#             set_processing(False)
#             return
        
#         # ===== EXTRACTION & ASSIGNMENT HANDLERS =====
#         # 1. USER NAME EXTRACTION: "my name is X" (but NOT "what is my name")
#         if not re.search(r"\bwhat\b", msg_lower):  # exclude question queries
#             m = re.search(r"\bmy name is ([A-Za-z0-9_\-]+)\b", msg_lower, flags=re.IGNORECASE)
#             if not m:
#                 m = re.search(r"\bi am ([A-Za-z0-9_\-]+)\b", msg_lower, flags=re.IGNORECASE)
#             if m:
#                 name = m.group(1).strip()
#                 try:
#                     memory.set_user_name("default_user", name)
#                 except Exception:
#                     pass
#                 add_message("NOVA", f"Thik hai, {name}! I've noted that.")
#                 conversation_history.append({"role":"user","text":message})
#                 conversation_history.append({"role":"assistant","text":f"Remembered: {name}"})
#                 set_processing(False)
#                 return
        
#         # 2. FRIEND NAME EXTRACTION: "my friend name is X" (but NOT "what is my friend name")
#         if not re.search(r"\bwhat\b", msg_lower):  # exclude question queries
#             m_friend = re.search(r"\bmy friend name is ([A-Za-z0-9_\-]+)\b", msg_lower, flags=re.IGNORECASE)
#             if not m_friend:
#                 m_friend = re.search(r"\b([A-Za-z0-9_\-]+)\s+is my friend\b", msg_lower, flags=re.IGNORECASE)
#             if m_friend:
#                 friend_name = m_friend.group(1).strip()
#                 session_vars["friend_name"] = friend_name
#                 add_message("NOVA", f"Got it! Your friend is {friend_name}. Noted!")
#                 conversation_history.append({"role":"user","text":message})
#                 conversation_history.append({"role":"assistant","text":f"Friend: {friend_name}"})
#                 set_processing(False)
#                 return
        
#         # 3. VARIABLE ASSIGNMENT: "a = 10"
#         m_var = re.match(r"^\s*([a-zA-Z]\w*)\s*=\s*([+-]?\d+(?:\.\d+)?)\s*$", message)
#         if m_var:
#             var = m_var.group(1)
#             val = float(m_var.group(2)) if '.' in m_var.group(2) else int(m_var.group(2))
#             session_vars[var] = val
#             add_message("NOVA", f"Set {var} = {val}")
#             conversation_history.append({"role":"user","text":message})
#             conversation_history.append({"role":"assistant","text":f"Set {var} = {val}"})
#             set_processing(False)
#             return
        
#         # 4. ARITHMETIC: "a + b = ?" or "a+b?"
#         m_expr = re.search(r"([a-zA-Z]\w*(?:\s*[+\-*/]\s*[a-zA-Z]\w*)+)(?:\s*=\s*\?|\?)", message, flags=re.IGNORECASE)
#         if m_expr:
#             expr_raw = m_expr.group(1).replace(' ', '')
#             expr = expr_raw
#             for v in list(session_vars.keys()):
#                 if v != "friend_name":
#                     expr = re.sub(rf"\b{v}\b", str(session_vars[v]), expr)
#             try:
#                 if re.match(r"^[0-9+\-*/(). ]+$", expr):
#                     result = eval(expr)
#                     add_message("NOVA", f"{expr_raw} = {result}")
#                     conversation_history.append({"role":"user","text":message})
#                     conversation_history.append({"role":"assistant","text":str(result)})
#                     set_processing(False)
#                     return
#             except Exception:
#                 pass

#         # ===== SEND TO LLM =====
#         context = uploaded_context or ""
#         recent_convo = ""
#         if conversation_history:
#             for msg in conversation_history[-8:]:
#                 role = msg.get("role", "user")
#                 text = (msg.get("text", "") or "").strip()[:200]
#                 if text and len(text) > 3:
#                     recent_convo += f"{role.upper()}: {text}\n"
        
#         if recent_convo:
#             prompt = f"{context}\n\nRECENT CONTEXT:\n{recent_convo}\nUser: {message}"
#         else:
#             prompt = f"{context}\n\nUser: {message}"
        
#         conversation_history.append({"role":"user","text":message})
#         if len(conversation_history) > 20:
#             conversation_history = conversation_history[-20:]

#         response = ask_llm(prompt, memory, conversation_history, on_update=on_update_partial, stop_event=stop_event)
        
#         # Ensure response is always displayed
#         if not response or response.startswith("Error:") or response.startswith("Connection"):
#             if not response:
#                 response = "I'm having trouble responding. Please try again."
#             add_message("System", response)
        
#         chat_display.configure(state="normal")
#         chat_display.insert("end", "\n\n")
#         chat_display.configure(state="disabled")
        
#         conversation_history.append({"role":"assistant","text": response})
#         resp_clean = (response or "").strip()
#         if resp_clean and len(resp_clean) > 5:
#             try:
#                 memory.save_memory("default_user", message, resp_clean)
#             except Exception:
#                 pass
#     except Exception as e:
#         add_message("System", f"Error: {e}")
#     finally:
#         set_processing(False)

# def _continue_worker(followup_text, on_update_cb):
#     global needs_prefix
#     try:
#         stop_event.clear() # Reset state
#         set_processing(True)
#         needs_prefix = True
#         response = ask_llm(followup_text, memory, conversation_history, on_update=on_update_cb, stop_event=stop_event)
        
#         if response and any(response.startswith(e) for e in ["Error:", "Server Error", "Connection Error", "LLM server error"]):
#             add_message("System", f"Connection error. Please try again.")
            
#         chat_display.configure(state="normal")
#         chat_display.insert("end", "\n\n")
#         chat_display.configure(state="disabled")
#         conversation_history.append({"role":"assistant","text": response})
#         try:
#             if response and len(response) > 5:
#                 memory.save_memory("default_user", "(continued)", response)
#         except Exception:
#             pass
#     except Exception as e:
#         add_message("System", f"Error: {e}")
#     finally:
#         set_processing(False)

# def voice_input_loop():
#     global is_listening
#     while is_listening:
#         cmd = listen()
#         if cmd:
#             add_message("You", cmd)
#             process_message(cmd)
#         time.sleep(0.2)

# message_entry.bind("<Return>", lambda e: send_message())

# if __name__ == "__main__":
#     add_message("System", "NOVA CORE SYSTEMS INITIALIZED. WAITING FOR PROTOCOL.")
#     app.mainloop()




# from tkinter import filedialog
# import customtkinter as ctk
# import threading
# import time
# from datetime import datetime
# from PIL import Image, ImageSequence
# from dotenv import load_dotenv
# from PyPDF2 import PdfReader

# # Tumhare local imports
# from audio_utils import listen, speak
# from memory import SQLiteMemory
# from local_llm import ask_llm  

# # ----------------- SYSTEM STATE ----------------- #
# conversation_history = []
# session_vars = {}
# uploaded_context = ""
# is_listening = False
# history_panel_visible = False
# is_processing = False

# # NAYA: Global Stop Event kill-switch ke liye
# stop_event = threading.Event()

# load_dotenv()

# # ----------------- UI THEME SETUP ----------------- #
# ctk.set_appearance_mode("dark")
# ctk.set_default_color_theme("blue")

# BG_COLOR = "#05070f"          
# PANEL_BG = "#0a0e17"          
# BORDER_COLOR = "#00e5ff"      
# TEXT_MAIN = "#e2e8f0"         
# TEXT_ACCENT = "#00e5ff"       
# TEXT_WARNING = "#ff3366"      

# memory = SQLiteMemory()

# # Initialize Main Window
# app = ctk.CTk()
# app.geometry("1100x720")
# app.title("NOVA AI CORE - Terminal")
# app.configure(fg_color=BG_COLOR)

# # ========================================================= #
# #                   LAYOUT ARCHITECTURE                     #
# # ========================================================= #

# sidebar_frame = ctk.CTkFrame(app, width=300, corner_radius=0, fg_color=PANEL_BG, border_width=1, border_color="#1e293b")
# sidebar_frame.pack(side="left", fill="y", padx=0, pady=0)
# sidebar_frame.pack_propagate(False) 

# main_frame = ctk.CTkFrame(app, corner_radius=0, fg_color="transparent")
# main_frame.pack(side="right", fill="both", expand=True)

# brand_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
# brand_frame.pack(fill="x", padx=20, pady=(25, 10))

# title_label = ctk.CTkLabel(brand_frame, text="N O V A // AI", font=("Orbitron", 24, "bold"), text_color=TEXT_ACCENT)
# title_label.pack(anchor="w")

# sub_label = ctk.CTkLabel(brand_frame, text="POWERED BY 89xENGINEERS", font=("Consolas", 9, "bold"), text_color="#64748b")
# sub_label.pack(anchor="w", pady=(0, 20))

# avatar_frame = ctk.CTkFrame(sidebar_frame, width=220, height=220, corner_radius=15, fg_color="#000000", border_width=2, border_color=BORDER_COLOR)
# avatar_frame.pack(pady=10)
# avatar_frame.pack_propagate(False)

# try:
#     avatar_gif = Image.open("./graphics/Jarvis.gif") 
#     avatar_frames = [ctk.CTkImage(light_image=f.copy().resize((200, 200)), size=(200, 200)) for f in ImageSequence.Iterator(avatar_gif)]
#     avatar_label = ctk.CTkLabel(avatar_frame, image=avatar_frames[0], text="")
#     avatar_label.pack(expand=True)
    
#     def animate_avatar(idx=0):
#         if not globals().get("stop_avatar", False):
#             avatar_label.configure(image=avatar_frames[idx])
#             app.after(80, animate_avatar, (idx+1) % len(avatar_frames))
#     animate_avatar()
# except Exception:
#     avatar_label = ctk.CTkLabel(avatar_frame, text="[ NOVA CORE ]", font=("Consolas", 18, "bold"), text_color=TEXT_ACCENT)
#     avatar_label.pack(expand=True)

# status_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
# status_frame.pack(fill="x", padx=20, pady=20)

# status_title = ctk.CTkLabel(status_frame, text="SYSTEM STATUS", font=("Consolas", 11, "bold"), text_color="#64748b")
# status_title.pack(anchor="w")

# thinking_label = ctk.CTkLabel(status_frame, text="● IDLE / READY", font=("Consolas", 13, "bold"), text_color="#00ff66")
# thinking_label.pack(anchor="w", pady=5)

# # NAYA CHANGE: set_processing ke andar hum EXECUTE button ko STOP button me convert karenge
# def set_processing(flag: bool):
#     global is_processing
#     is_processing = flag
#     if flag:
#         thinking_label.configure(text="● PROCESSING...", text_color="#ffcc00")
#         avatar_frame.configure(border_color="#ffcc00", border_width=3)
#         # Button becomes STOP
#         send_btn.configure(text="STOP [◼]", fg_color=TEXT_WARNING, hover_color="#cc0044", command=stop_generation)
#         cont_btn.configure(state="disabled")
#     else:
#         thinking_label.configure(text="● IDLE / READY", text_color="#00ff66")
#         avatar_frame.configure(border_color=BORDER_COLOR, border_width=2)
#         # Button reverts to EXECUTE
#         send_btn.configure(text="EXECUTE [➤]", fg_color=TEXT_ACCENT, text_color="#000000", hover_color="#00b3cc", command=send_message)
#         cont_btn.configure(state="normal")

# controls_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
# controls_frame.pack(fill="x", padx=20, pady=10)

# def create_hud_button(parent, text, command, row, col):
#     btn = ctk.CTkButton(
#         parent, text=text, command=command,
#         font=("Consolas", 12, "bold"),
#         fg_color="#0b1320", hover_color="#00334e",
#         border_color=BORDER_COLOR, border_width=1,
#         text_color=TEXT_ACCENT, width=120, height=40
#     )
#     btn.grid(row=row, column=col, padx=5, pady=5)
#     return btn

# def toggle_mic():
#     global is_listening
#     is_listening = not is_listening
#     if is_listening:
#         mic_btn.configure(fg_color=TEXT_ACCENT, text_color="#000000", text="MIC: ON [🎙]")
#         threading.Thread(target=voice_input_loop, daemon=True).start()
#     else:
#         mic_btn.configure(fg_color="#0b1320", text_color=TEXT_ACCENT, text="MIC: OFF [🎤]")

# def upload_document():
#     global uploaded_context
#     file_path = filedialog.askopenfilename(filetypes=[("Documents", "*.txt *.pdf"), ("Images", "*.png *.jpg *.jpeg")])
#     if not file_path:
#         return
#     try:
#         if file_path.lower().endswith(".txt"):
#             with open(file_path, "r", encoding="utf-8") as f:
#                 uploaded_context = f.read()
#         elif file_path.lower().endswith(".pdf"):
#             reader = PdfReader(file_path)
#             uploaded_context = "\n".join([p.extract_text() or "" for p in reader.pages])
#         else:
#             uploaded_context = f"[File uploaded: {file_path}]"
#         add_message("System", f"Loaded context from: {file_path.split('/')[-1]}")
#     except Exception as e:
#         add_message("System", f"File load error: {e}")

# def clear_chat_history_ui():
#     global conversation_history, uploaded_context
#     try:
#         conversation_history.clear()
#         uploaded_context = ""
#         chat_display.configure(state="normal")
#         chat_display.delete("1.0", "end")
#         chat_display.configure(state="disabled")
#         try:
#             if hasattr(memory, "conn"):
#                 cur = memory.conn.cursor()
#                 cur.execute("DELETE FROM memory WHERE user_id = ?", ("default_user",))
#                 memory.conn.commit()
#         except Exception:
#             pass
#         add_message("System", "Terminal buffer and database wiped successfully.")
#     except Exception as e:
#         add_message("System", f"Clear error: {e}")

# def toggle_history_panel():
#     global history_panel_visible
#     history_panel_visible = not history_panel_visible
#     if history_panel_visible:
#         history_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
#         load_chat_history()
#     else:
#         history_frame.pack_forget()

# mic_btn = create_hud_button(controls_frame, "MIC: OFF [🎤]", toggle_mic, 0, 0)
# upload_btn = create_hud_button(controls_frame, "UPLOAD [📄]", upload_document, 0, 1)
# mem_btn = create_hud_button(controls_frame, "MEMORY [🧠]", toggle_history_panel, 1, 0)
# clear_btn = create_hud_button(controls_frame, "PURGE [🗑️]", clear_chat_history_ui, 1, 1)

# chat_container = ctk.CTkFrame(main_frame, fg_color="transparent")
# chat_container.pack(fill="both", expand=True, padx=20, pady=(20, 10))

# term_header = ctk.CTkLabel(chat_container, text=">_ SECURE TERMINAL OUTPUT", font=("Consolas", 12, "bold"), text_color="#475569")
# term_header.pack(anchor="w", pady=(0, 5))

# chat_frame = ctk.CTkFrame(chat_container, corner_radius=10, fg_color="#0a0e17", border_width=1, border_color="#1e293b")
# chat_frame.pack(fill="both", expand=True)

# chat_display = ctk.CTkTextbox(chat_frame, font=("Consolas", 14), wrap="word", fg_color="transparent", text_color=TEXT_MAIN)
# chat_display.pack(side="left", fill="both", expand=True, padx=15, pady=15)

# from tkinter import Scrollbar
# scroll = Scrollbar(chat_frame, command=chat_display.yview)
# chat_display.configure(yscrollcommand=scroll.set)
# scroll.pack(side="right", fill="y", pady=15, padx=(0,10))

# chat_display.configure(state="disabled")

# # Color Tags
# chat_display.tag_config("You", foreground="#ffffff")
# chat_display.tag_config("NOVA", foreground=TEXT_ACCENT)
# chat_display.tag_config("System", foreground=TEXT_WARNING)
# chat_display.tag_config("Time", foreground="#475569")

# def add_message(sender, text):
#     chat_display.configure(state="normal")
#     time_str = datetime.now().strftime("%H:%M:%S")
#     chat_display.insert("end", f"[{time_str}] ", "Time")
    
#     if sender == "You":
#         chat_display.insert("end", "USER: ", "You")
#         chat_display.insert("end", f"{text}\n\n", "You")
#     elif sender == "System":
#         chat_display.insert("end", "SYSTEM_ALERT: ", "System")
#         chat_display.insert("end", f"{text}\n\n", "System")
#     else:
#         chat_display.insert("end", "NOVA: ", "NOVA")
#         chat_display.insert("end", f"{text}\n\n", "NOVA")
        
#     chat_display.configure(state="disabled")
#     chat_display.see("end")

# input_container = ctk.CTkFrame(main_frame, fg_color="transparent")
# input_container.pack(fill="x", padx=20, pady=(0, 20))

# input_frame = ctk.CTkFrame(input_container, fg_color="#0a0e17", corner_radius=10, border_width=1, border_color="#1e293b")
# input_frame.pack(fill="x", ipady=5)

# message_entry = ctk.CTkEntry(
#     input_frame, placeholder_text="Enter command protocol here...", 
#     font=("Consolas", 14), fg_color="transparent", border_width=0, text_color="#ffffff"
# )
# message_entry.pack(side="left", fill="x", expand=True, padx=15, pady=10)

# def send_message():
#     msg = message_entry.get().strip()
#     if not msg:
#         return
#     add_message("You", msg)
#     message_entry.delete(0, "end")
#     threading.Thread(target=process_message, args=(msg,), daemon=True).start()

# # NAYA: Stop Generation Handler
# def stop_generation():
#     stop_event.set()
#     add_message("System", "Generation halted by user override.")

# def continue_last():
#     if not conversation_history:
#         add_message("NOVA", "No previous response to continue.")
#         return
#     followup = "Please continue the previous answer. Continue where you left off and do not repeat the already given text."
#     conversation_history.append({"role":"user", "text": followup})
#     threading.Thread(target=lambda: _continue_worker(followup, on_update_partial), daemon=True).start()

# cont_btn = ctk.CTkButton(
#     input_frame, text="CONTINUE [⟳]", width=100, command=continue_last,
#     font=("Consolas", 12, "bold"), fg_color="transparent", border_width=1, border_color="#475569", hover_color="#1e293b"
# )
# cont_btn.pack(side="left", padx=(0, 10))

# send_btn = ctk.CTkButton(
#     input_frame, text="EXECUTE [➤]", width=120, command=send_message,
#     font=("Consolas", 12, "bold"), fg_color=TEXT_ACCENT, text_color="#000000", hover_color="#00b3cc"
# )
# send_btn.pack(side="right", padx=(0, 15))


# history_frame = ctk.CTkFrame(main_frame, corner_radius=10, fg_color="#070a13", border_width=1, border_color=TEXT_WARNING)
# history_display = ctk.CTkTextbox(history_frame, wrap="word", font=("Consolas", 12), fg_color="transparent", text_color="#94a3b8")
# history_display.pack(fill="both", expand=True, padx=15, pady=15)
# history_display.configure(state="disabled")

# def load_chat_history():
#     try:
#         history_display.configure(state="normal")
#         history_display.delete("1.0", "end")
#         memories = []
#         try:
#             memories = memory.get_chat_history("default_user", 50)
#         except Exception:
#             try:
#                 cur = memory.conn.cursor()
#                 cur.execute("SELECT query, response, timestamp FROM memory WHERE user_id = ? ORDER BY rowid DESC LIMIT 50", ("default_user",))
#                 memories = cur.fetchall()
#             except Exception:
#                 memories = []
        
#         history_display.insert("end", "=== SECURE MEMORY ARCHIVE ===\n\n")
#         if not memories:
#             history_display.insert("end", "No memories found.\n")
#         else:
#             for m in memories:
#                 try:
#                     q, r, t = m[0], m[1], (m[2] if len(m) > 2 else "")
#                     history_display.insert("end", f"[{t}] USER: {q}\nNOVA: {r}\n{'-'*40}\n")
#                 except Exception:
#                     pass
#         history_display.configure(state="disabled")
#         history_display.see("end")
#     except Exception as e:
#         add_message("System", f"History load error: {e}")


# def on_update_partial(chunk: str):
#     try:
#         chat_display.configure(state="normal")
#         if chat_display.get("end-3c", "end-2c") == "":  
#             time_str = datetime.now().strftime("%H:%M:%S")
#             chat_display.insert("end", f"[{time_str}] ", "Time")
#             chat_display.insert("end", "NOVA: ", "NOVA")
            
#         chat_display.insert("end", chunk, "NOVA")
#         chat_display.configure(state="disabled")
#         chat_display.see("end")
#     except Exception:
#         pass

# def process_message(message):
#     global uploaded_context, conversation_history
#     try:
#         stop_event.clear() # NAYA: Button reset event state
#         set_processing(True)
#         import re
#         msg_lower = (message or "").strip()
#         m = re.search(r"\bmy name is ([A-Za-z0-9_\-]+)\b", msg_lower, flags=re.IGNORECASE)
#         if not m:
#             m = re.search(r"\bi am ([A-Za-z0-9_\-]+)\b", msg_lower, flags=re.IGNORECASE)
#         if m:
#             name = m.group(1).strip()
#             try:
#                 memory.set_user_name("default_user", name)
#             except Exception:
#                 pass
#             add_message("NOVA", f"Acknowledged, {name}. Identity profile updated.")
#             conversation_history.append({"role":"user","text":message})
#             conversation_history.append({"role":"assistant","text":f"Remembered name: {name}"})
#             set_processing(False)
#             return

#         context = uploaded_context or ""
#         prompt = f"{context}\n\nUser: {message}"
#         conversation_history.append({"role":"user","text":message})
#         if len(conversation_history) > 20:
#             conversation_history = conversation_history[-20:]

#         # NAYA: stop_event variable pass kiya ask_llm ko
#         response = ask_llm(prompt, memory, conversation_history, on_update=on_update_partial, stop_event=stop_event)
        
#         chat_display.configure(state="normal")
#         chat_display.insert("end", "\n\n")
#         chat_display.configure(state="disabled")
        
#         conversation_history.append({"role":"assistant","text": response})
#         resp_clean = (response or "").strip()
#         if resp_clean and len(resp_clean) > 5:
#             try:
#                 memory.save_memory("default_user", message, resp_clean)
#             except Exception:
#                 pass
#     except Exception as e:
#         add_message("System", f"Core execution failure: {e}")
#     finally:
#         set_processing(False)

# def _continue_worker(followup_text, on_update_cb):
#     try:
#         stop_event.clear() # NAYA: Reset state
#         set_processing(True)
#         response = ask_llm(followup_text, memory, conversation_history, on_update=on_update_cb, stop_event=stop_event)
#         chat_display.configure(state="normal")
#         chat_display.insert("end", "\n\n")
#         chat_display.configure(state="disabled")
#         conversation_history.append({"role":"assistant","text": response})
#         try:
#             if response and len(response) > 5:
#                 memory.save_memory("default_user", "(continued)", response)
#         except Exception:
#             pass
#     except Exception as e:
#         add_message("System", f"Pipeline error: {e}")
#     finally:
#         set_processing(False)

# def voice_input_loop():
#     global is_listening
#     while is_listening:
#         cmd = listen()
#         if cmd:
#             add_message("You", cmd)
#             process_message(cmd)
#         time.sleep(0.2)

# message_entry.bind("<Return>", lambda e: send_message())

# if __name__ == "__main__":
#     add_message("System", "NOVA CORE SYSTEMS INITIALIZED. WAITING FOR PROTOCOL.")
#     app.mainloop()









# mast ui
# from tkinter import filedialog
# import customtkinter as ctk
# import threading
# import time
# from datetime import datetime
# from PIL import Image, ImageSequence
# from dotenv import load_dotenv
# from PyPDF2 import PdfReader

# # Tumhare local imports (Ensure they exist in your project)
# from audio_utils import listen, speak
# from memory import SQLiteMemory
# from local_llm import ask_llm  

# # ----------------- SYSTEM STATE ----------------- #
# conversation_history = []
# session_vars = {}
# uploaded_context = ""
# is_listening = False
# history_panel_visible = False
# is_processing = False

# load_dotenv()

# # ----------------- UI THEME SETUP ----------------- #
# ctk.set_appearance_mode("dark")
# ctk.set_default_color_theme("blue")

# # Custom Colors (Cyberpunk / Iron Man HUD style)
# BG_COLOR = "#05070f"          # Deep space dark
# PANEL_BG = "#0a0e17"          # Slightly lighter panel
# BORDER_COLOR = "#00e5ff"      # Neon Cyan
# TEXT_MAIN = "#e2e8f0"         # Off-white for readability
# TEXT_ACCENT = "#00e5ff"       # Neon cyan for highlights
# TEXT_WARNING = "#ff3366"      # Neon red/pink for errors/system

# memory = SQLiteMemory()

# # Initialize Main Window
# app = ctk.CTk()
# app.geometry("1100x720")
# app.title("NOVA AI CORE - Terminal")
# app.configure(fg_color=BG_COLOR)

# # ========================================================= #
# #                   LAYOUT ARCHITECTURE                     #
# # ========================================================= #

# # LEFT PANEL (SIDEBAR) - 300px width
# sidebar_frame = ctk.CTkFrame(app, width=300, corner_radius=0, fg_color=PANEL_BG, border_width=1, border_color="#1e293b")
# sidebar_frame.pack(side="left", fill="y", padx=0, pady=0)
# sidebar_frame.pack_propagate(False) # Stop it from shrinking

# # RIGHT PANEL (MAIN WORKSPACE)
# main_frame = ctk.CTkFrame(app, corner_radius=0, fg_color="transparent")
# main_frame.pack(side="right", fill="both", expand=True)

# # ========================================================= #
# #                   SIDEBAR CONTENT                         #
# # ========================================================= #

# # Brand / Title
# brand_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
# brand_frame.pack(fill="x", padx=20, pady=(25, 10))

# title_label = ctk.CTkLabel(brand_frame, text="N O V A // AI", font=("Orbitron", 24, "bold"), text_color=TEXT_ACCENT)
# title_label.pack(anchor="w")

# sub_label = ctk.CTkLabel(brand_frame, text="POWERED BY 89xENGINEERS", font=("Consolas", 9, "bold"), text_color="#64748b")
# sub_label.pack(anchor="w", pady=(0, 20))

# # Avatar Frame
# avatar_frame = ctk.CTkFrame(sidebar_frame, width=220, height=220, corner_radius=15, fg_color="#000000", border_width=2, border_color=BORDER_COLOR)
# avatar_frame.pack(pady=10)
# avatar_frame.pack_propagate(False)

# # Avatar Logic
# try:
#     avatar_gif = Image.open("./graphics/Jarvis.gif") # Tera GIF path
#     avatar_frames = [ctk.CTkImage(light_image=f.copy().resize((200, 200)), size=(200, 200)) for f in ImageSequence.Iterator(avatar_gif)]
#     avatar_label = ctk.CTkLabel(avatar_frame, image=avatar_frames[0], text="")
#     avatar_label.pack(expand=True)
    
#     def animate_avatar(idx=0):
#         if not globals().get("stop_avatar", False):
#             avatar_label.configure(image=avatar_frames[idx])
#             app.after(80, animate_avatar, (idx+1) % len(avatar_frames))
#     animate_avatar()
# except Exception:
#     avatar_label = ctk.CTkLabel(avatar_frame, text="[ NOVA CORE ]", font=("Consolas", 18, "bold"), text_color=TEXT_ACCENT)
#     avatar_label.pack(expand=True)

# # System Status
# status_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
# status_frame.pack(fill="x", padx=20, pady=20)

# status_title = ctk.CTkLabel(status_frame, text="SYSTEM STATUS", font=("Consolas", 11, "bold"), text_color="#64748b")
# status_title.pack(anchor="w")

# thinking_label = ctk.CTkLabel(status_frame, text="● IDLE / READY", font=("Consolas", 13, "bold"), text_color="#00ff66")
# thinking_label.pack(anchor="w", pady=5)

# def set_processing(flag: bool):
#     global is_processing
#     is_processing = flag
#     if flag:
#         thinking_label.configure(text="● PROCESSING...", text_color="#ffcc00")
#         avatar_frame.configure(border_color="#ffcc00", border_width=3)
#     else:
#         thinking_label.configure(text="● IDLE / READY", text_color="#00ff66")
#         avatar_frame.configure(border_color=BORDER_COLOR, border_width=2)

# # Control Buttons (Grid Layout)
# controls_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
# controls_frame.pack(fill="x", padx=20, pady=10)

# def create_hud_button(parent, text, command, row, col):
#     btn = ctk.CTkButton(
#         parent, text=text, command=command,
#         font=("Consolas", 12, "bold"),
#         fg_color="#0b1320", hover_color="#00334e",
#         border_color=BORDER_COLOR, border_width=1,
#         text_color=TEXT_ACCENT, width=120, height=40
#     )
#     btn.grid(row=row, column=col, padx=5, pady=5)
#     return btn

# def toggle_mic():
#     global is_listening
#     is_listening = not is_listening
#     if is_listening:
#         mic_btn.configure(fg_color=TEXT_ACCENT, text_color="#000000", text="MIC: ON [🎙]")
#         threading.Thread(target=voice_input_loop, daemon=True).start()
#     else:
#         mic_btn.configure(fg_color="#0b1320", text_color=TEXT_ACCENT, text="MIC: OFF [🎤]")

# def upload_document():
#     global uploaded_context
#     file_path = filedialog.askopenfilename(filetypes=[("Documents", "*.txt *.pdf"), ("Images", "*.png *.jpg *.jpeg")])
#     if not file_path:
#         return
#     try:
#         if file_path.lower().endswith(".txt"):
#             with open(file_path, "r", encoding="utf-8") as f:
#                 uploaded_context = f.read()
#         elif file_path.lower().endswith(".pdf"):
#             reader = PdfReader(file_path)
#             uploaded_context = "\n".join([p.extract_text() or "" for p in reader.pages])
#         else:
#             uploaded_context = f"[File uploaded: {file_path}]"
#         add_message("System", f"Loaded context from: {file_path.split('/')[-1]}")
#     except Exception as e:
#         add_message("System", f"File load error: {e}")

# def clear_chat_history_ui():
#     global conversation_history, uploaded_context
#     try:
#         conversation_history.clear()
#         uploaded_context = ""
#         chat_display.configure(state="normal")
#         chat_display.delete("1.0", "end")
#         chat_display.configure(state="disabled")
#         try:
#             if hasattr(memory, "conn"):
#                 cur = memory.conn.cursor()
#                 cur.execute("DELETE FROM memory WHERE user_id = ?", ("default_user",))
#                 memory.conn.commit()
#         except Exception:
#             pass
#         add_message("System", "Terminal buffer and database wiped successfully.")
#     except Exception as e:
#         add_message("System", f"Clear error: {e}")

# def toggle_history_panel():
#     global history_panel_visible
#     history_panel_visible = not history_panel_visible
#     if history_panel_visible:
#         history_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
#         load_chat_history()
#     else:
#         history_frame.pack_forget()

# mic_btn = create_hud_button(controls_frame, "MIC: OFF [🎤]", toggle_mic, 0, 0)
# upload_btn = create_hud_button(controls_frame, "UPLOAD [📄]", upload_document, 0, 1)
# mem_btn = create_hud_button(controls_frame, "MEMORY [🧠]", toggle_history_panel, 1, 0)
# clear_btn = create_hud_button(controls_frame, "PURGE [🗑️]", clear_chat_history_ui, 1, 1)


# # ========================================================= #
# #                   MAIN WORKSPACE                          #
# # ========================================================= #

# # Main Chat Terminal
# chat_container = ctk.CTkFrame(main_frame, fg_color="transparent")
# chat_container.pack(fill="both", expand=True, padx=20, pady=(20, 10))

# term_header = ctk.CTkLabel(chat_container, text=">_ SECURE TERMINAL OUTPUT", font=("Consolas", 12, "bold"), text_color="#475569")
# term_header.pack(anchor="w", pady=(0, 5))

# chat_frame = ctk.CTkFrame(chat_container, corner_radius=10, fg_color="#0a0e17", border_width=1, border_color="#1e293b")
# chat_frame.pack(fill="both", expand=True)

# chat_display = ctk.CTkTextbox(chat_frame, font=("Consolas", 14), wrap="word", fg_color="transparent", text_color=TEXT_MAIN)
# chat_display.pack(side="left", fill="both", expand=True, padx=15, pady=15)

# from tkinter import Scrollbar
# scroll = Scrollbar(chat_frame, command=chat_display.yview)
# chat_display.configure(yscrollcommand=scroll.set)
# scroll.pack(side="right", fill="y", pady=15, padx=(0,10))

# chat_display.configure(state="disabled")

# # Tags for coloring in terminal
# chat_display.tag_config("You", foreground="#ffffff")
# chat_display.tag_config("NOVA", foreground=TEXT_ACCENT)
# chat_display.tag_config("System", foreground=TEXT_WARNING)
# chat_display.tag_config("Time", foreground="#475569")

# def add_message(sender, text):
#     chat_display.configure(state="normal")
#     time_str = datetime.now().strftime("%H:%M:%S")
    
#     # Format exactly like a hacker terminal
#     chat_display.insert("end", f"[{time_str}] ", "Time")
    
#     if sender == "You":
#         chat_display.insert("end", "USER: ", "You")
#         chat_display.insert("end", f"{text}\n\n", "You")
#     elif sender == "System":
#         chat_display.insert("end", "SYSTEM_ALERT: ", "System")
#         chat_display.insert("end", f"{text}\n\n", "System")
#     else:
#         chat_display.insert("end", "NOVA: ", "NOVA")
#         chat_display.insert("end", f"{text}\n\n", "NOVA")
        
#     chat_display.configure(state="disabled")
#     chat_display.see("end")

# # Input Area
# input_container = ctk.CTkFrame(main_frame, fg_color="transparent")
# input_container.pack(fill="x", padx=20, pady=(0, 20))

# input_frame = ctk.CTkFrame(input_container, fg_color="#0a0e17", corner_radius=10, border_width=1, border_color="#1e293b")
# input_frame.pack(fill="x", ipady=5)

# message_entry = ctk.CTkEntry(
#     input_frame, placeholder_text="Enter command protocol here...", 
#     font=("Consolas", 14), fg_color="transparent", border_width=0, text_color="#ffffff"
# )
# message_entry.pack(side="left", fill="x", expand=True, padx=15, pady=10)

# def send_message():
#     msg = message_entry.get().strip()
#     if not msg:
#         return
#     add_message("You", msg)
#     message_entry.delete(0, "end")
#     threading.Thread(target=process_message, args=(msg,), daemon=True).start()

# def continue_last():
#     if not conversation_history:
#         add_message("NOVA", "No previous response to continue.")
#         return
#     followup = "Please continue the previous answer. Continue where you left off and do not repeat the already given text."
#     conversation_history.append({"role":"user", "text": followup})
#     threading.Thread(target=lambda: _continue_worker(followup, on_update_partial), daemon=True).start()

# # Pro-looking Action Buttons
# cont_btn = ctk.CTkButton(
#     input_frame, text="CONTINUE [⟳]", width=100, command=continue_last,
#     font=("Consolas", 12, "bold"), fg_color="transparent", border_width=1, border_color="#475569", hover_color="#1e293b"
# )
# cont_btn.pack(side="left", padx=(0, 10))

# send_btn = ctk.CTkButton(
#     input_frame, text="EXECUTE [➤]", width=120, command=send_message,
#     font=("Consolas", 12, "bold"), fg_color=TEXT_ACCENT, text_color="#000000", hover_color="#00b3cc"
# )
# send_btn.pack(side="right", padx=(0, 15))


# # ========================================================= #
# #                   HISTORY PANEL (Hidden)                  #
# # ========================================================= #

# history_frame = ctk.CTkFrame(main_frame, corner_radius=10, fg_color="#070a13", border_width=1, border_color=TEXT_WARNING)
# history_display = ctk.CTkTextbox(history_frame, wrap="word", font=("Consolas", 12), fg_color="transparent", text_color="#94a3b8")
# history_display.pack(fill="both", expand=True, padx=15, pady=15)
# history_display.configure(state="disabled")

# def load_chat_history():
#     try:
#         history_display.configure(state="normal")
#         history_display.delete("1.0", "end")
#         memories = []
#         try:
#             memories = memory.get_chat_history("default_user", 50)
#         except Exception:
#             try:
#                 cur = memory.conn.cursor()
#                 cur.execute("SELECT query, response, timestamp FROM memory WHERE user_id = ? ORDER BY rowid DESC LIMIT 50", ("default_user",))
#                 memories = cur.fetchall()
#             except Exception:
#                 memories = []
        
#         history_display.insert("end", "=== SECURE MEMORY ARCHIVE ===\n\n")
#         if not memories:
#             history_display.insert("end", "No memories found.\n")
#         else:
#             for m in memories:
#                 try:
#                     q, r, t = m[0], m[1], (m[2] if len(m) > 2 else "")
#                     history_display.insert("end", f"[{t}] USER: {q}\nNOVA: {r}\n{'-'*40}\n")
#                 except Exception:
#                     pass
#         history_display.configure(state="disabled")
#         history_display.see("end")
#     except Exception as e:
#         add_message("System", f"History load error: {e}")


# # ========================================================= #
# #                   LOGIC AND HANDLERS                      #
# # ========================================================= #

# def on_update_partial(chunk: str):
#     try:
#         chat_display.configure(state="normal")
#         # Check if we need to insert the prefix
#         if chat_display.get("end-3c", "end-2c") == "":  
#             time_str = datetime.now().strftime("%H:%M:%S")
#             chat_display.insert("end", f"[{time_str}] ", "Time")
#             chat_display.insert("end", "NOVA: ", "NOVA")
            
#         chat_display.insert("end", chunk, "NOVA")
#         chat_display.configure(state="disabled")
#         chat_display.see("end")
#     except Exception:
#         pass

# def process_message(message):
#     global uploaded_context, conversation_history
#     try:
#         set_processing(True)
#         import re
#         msg_lower = (message or "").strip()
#         m = re.search(r"\bmy name is ([A-Za-z0-9_\-]+)\b", msg_lower, flags=re.IGNORECASE)
#         if not m:
#             m = re.search(r"\bi am ([A-Za-z0-9_\-]+)\b", msg_lower, flags=re.IGNORECASE)
#         if m:
#             name = m.group(1).strip()
#             try:
#                 memory.set_user_name("default_user", name)
#             except Exception:
#                 pass
#             add_message("NOVA", f"Acknowledged, {name}. Identity profile updated.")
#             conversation_history.append({"role":"user","text":message})
#             conversation_history.append({"role":"assistant","text":f"Remembered name: {name}"})
#             set_processing(False)
#             return

#         context = uploaded_context or ""
#         prompt = f"{context}\n\nUser: {message}"
#         conversation_history.append({"role":"user","text":message})
#         if len(conversation_history) > 20:
#             conversation_history = conversation_history[-20:]

#         response = ask_llm(prompt, memory, conversation_history, on_update=on_update_partial)
        
#         chat_display.configure(state="normal")
#         chat_display.insert("end", "\n\n")
#         chat_display.configure(state="disabled")
        
#         conversation_history.append({"role":"assistant","text": response})
#         resp_clean = (response or "").strip()
#         if resp_clean and len(resp_clean) > 5:
#             try:
#                 memory.save_memory("default_user", message, resp_clean)
#             except Exception:
#                 pass
#     except Exception as e:
#         add_message("System", f"Core execution failure: {e}")
#     finally:
#         set_processing(False)

# def _continue_worker(followup_text, on_update_cb):
#     try:
#         set_processing(True)
#         response = ask_llm(followup_text, memory, conversation_history, on_update=on_update_cb)
#         chat_display.configure(state="normal")
#         chat_display.insert("end", "\n\n")
#         chat_display.configure(state="disabled")
#         conversation_history.append({"role":"assistant","text": response})
#         try:
#             if response and len(response) > 5:
#                 memory.save_memory("default_user", "(continued)", response)
#         except Exception:
#             pass
#     except Exception as e:
#         add_message("System", f"Pipeline error: {e}")
#     finally:
#         set_processing(False)

# def voice_input_loop():
#     global is_listening
#     while is_listening:
#         cmd = listen()
#         if cmd:
#             add_message("You", cmd)
#             process_message(cmd)
#         time.sleep(0.2)

# # Bind Enter Key
# message_entry.bind("<Return>", lambda e: send_message())

# # ========================================================= #
# #                   BOOT SEQUENCE                           #
# # ========================================================= #
# if __name__ == "__main__":
#     add_message("System", "NOVA CORE SYSTEMS INITIALIZED. WAITING FOR PROTOCOL.")
#     app.mainloop()




# from tkinter import filedialog
# import customtkinter as ctk
# import threading
# import time
# from audio_utils import listen, speak
# from memory import SQLiteMemory
# from PIL import Image, ImageSequence
# from dotenv import load_dotenv
# from PyPDF2 import PdfReader
# from local_llm import ask_llm   # existing local interface

# # simple state
# conversation_history = []
# session_vars = {}
# uploaded_context = ""
# is_listening = False
# history_panel_visible = False
# is_processing = False

# load_dotenv()

# ctk.set_appearance_mode("dark")
# ctk.set_default_color_theme("blue")

# memory = SQLiteMemory()

# app = ctk.CTk()
# app.geometry("420x760")
# app.title("NOVA AI")
# app.configure(fg_color="#0a0a12")

# # ----------------- Layout ----------------- #
# header_frame = ctk.CTkFrame(master=app, fg_color="transparent")
# header_frame.pack(fill="x", padx=12, pady=(12, 6))

# title_label = ctk.CTkLabel(header_frame, text="NOVA AI", font=("Helvetica", 16, "bold"), text_color="#00ffff")
# title_label.pack(side="left")

# controls_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
# controls_frame.pack(side="right")

# # control buttons: minimize (collapse chat), maximize (expand), memory, mic, upload, clear
# def toggle_chat_panel():
#     global chat_collapsed
#     chat_collapsed = not globals().get("chat_collapsed", False)
#     if chat_collapsed:
#         avatar_frame.pack_forget()
#         chat_frame.pack_forget()
#         input_frame.pack_forget()
#         app.geometry("260x180")
#         collapse_btn.configure(text="▸")
#     else:
#         avatar_frame.pack(pady=(8, 18))
#         chat_frame.pack(fill="both", expand=True, pady=10)
#         input_frame.pack(fill="x")
#         app.geometry("420x760")
#         collapse_btn.configure(text="▾")

# collapse_btn = ctk.CTkButton(controls_frame, text="▾", width=36, height=32, command=toggle_chat_panel)
# collapse_btn.pack(side="right", padx=6)

# def maximize_window():
#     try:
#         app.state("zoomed")
#     except Exception:
#         app.geometry("800x900")

# max_btn = ctk.CTkButton(controls_frame, text="⬜", width=36, height=32, command=maximize_window)
# max_btn.pack(side="right", padx=6)

# # memory / history toggle
# def toggle_history_panel():
#     global history_panel_visible
#     history_panel_visible = not history_panel_visible
#     if history_panel_visible:
#         history_frame.pack(fill="both", expand=True, padx=6, pady=6)
#         load_chat_history()
#     else:
#         history_frame.pack_forget()

# mem_btn = ctk.CTkButton(controls_frame, text="🧠", width=36, height=32, command=toggle_history_panel)
# mem_btn.pack(side="right", padx=6)

# # mic toggle
# def toggle_mic():
#     global is_listening
#     is_listening = not is_listening
#     mic_btn.configure(fg_color="#00ffff" if is_listening else "transparent", text_color="#000000" if is_listening else "#ffffff")
#     if is_listening:
#         threading.Thread(target=voice_input_loop, daemon=True).start()

# mic_btn = ctk.CTkButton(controls_frame, text="🎤", width=36, height=32, command=toggle_mic)
# mic_btn.pack(side="right", padx=6)

# # upload button
# def upload_document():
#     global uploaded_context
#     file_path = filedialog.askopenfilename(filetypes=[("Documents", "*.txt *.pdf"), ("Images", "*.png *.jpg *.jpeg")])
#     if not file_path:
#         return
#     try:
#         if file_path.lower().endswith(".txt"):
#             with open(file_path, "r", encoding="utf-8") as f:
#                 uploaded_context = f.read()
#         elif file_path.lower().endswith(".pdf"):
#             reader = PdfReader(file_path)
#             uploaded_context = "\n".join([p.extract_text() or "" for p in reader.pages])
#         else:
#             uploaded_context = f"[File uploaded: {file_path}]"
#         add_message("System", f"Loaded file: {file_path.split('/')[-1]}")
#     except Exception as e:
#         add_message("System", f"File load error: {e}")

# upload_btn = ctk.CTkButton(controls_frame, text="📄", width=36, height=32, command=upload_document)
# upload_btn.pack(side="right", padx=6)

# # clear chat
# def clear_chat_history_ui():
#     global conversation_history, uploaded_context
#     try:
#         conversation_history.clear()
#         uploaded_context = ""
#         chat_display.configure(state="normal")
#         chat_display.delete("1.0", "end")
#         chat_display.configure(state="disabled")
#         # try clear persistent memory if available
#         try:
#             if hasattr(memory, "conn"):
#                 cur = memory.conn.cursor()
#                 cur.execute("DELETE FROM memory WHERE user_id = ?", ("default_user",))
#                 memory.conn.commit()
#         except Exception:
#             pass
#         add_message("System", "Chat and memory cleared")
#     except Exception as e:
#         add_message("System", f"Clear error: {e}")

# clear_btn = ctk.CTkButton(controls_frame, text="🗑️", width=36, height=32, command=clear_chat_history_ui)
# clear_btn.pack(side="right", padx=6)

# # ----------------- Avatar / Thinking ----------------- #
# avatar_frame = ctk.CTkFrame(master=app, width=200, height=120, corner_radius=12, fg_color="transparent",
#                            border_width=2, border_color="#00ffff")
# avatar_frame.pack(pady=(8, 18))

# thinking_label = ctk.CTkLabel(avatar_frame, text="", text_color="#00ffff")
# thinking_label.pack(pady=6)

# try:
#     avatar_gif = Image.open("./graphics/Jarvis.gif")
#     avatar_frames = [ctk.CTkImage(light_image=f.copy().resize((140, 140)), size=(140, 140)) for f in ImageSequence.Iterator(avatar_gif)]
#     avatar_label = ctk.CTkLabel(avatar_frame, image=avatar_frames[0], text="")
#     avatar_label.pack()
#     def animate_avatar(idx=0):
#         if not globals().get("stop_avatar", False):
#             avatar_label.configure(image=avatar_frames[idx])
#             app.after(80, animate_avatar, (idx+1) % len(avatar_frames))
#     animate_avatar()
# except Exception:
#     avatar_label = ctk.CTkLabel(avatar_frame, text="NOVA", font=("Helvetica", 20, "bold"))
#     avatar_label.pack()

# def set_processing(flag: bool):
#     global is_processing
#     is_processing = flag
#     if flag:
#         thinking_label.configure(text="Thinking...")
#         avatar_frame.configure(border_width=6)
#     else:
#         thinking_label.configure(text="")
#         avatar_frame.configure(border_width=2)

# # ----------------- Chat ----------------- #
# chat_frame = ctk.CTkFrame(master=app, corner_radius=12, fg_color="#1a1a2a", border_width=1, border_color="#00ffff")
# chat_frame.pack(fill="both", expand=True, pady=10, padx=6)

# chat_display = ctk.CTkTextbox(chat_frame, font=("Helvetica", 14), wrap="word", fg_color="transparent", text_color="#ffffff")
# chat_display.pack(side="left", fill="both", expand=True, padx=(6,0), pady=6)

# # add scrollbar
# from tkinter import Scrollbar
# scroll = Scrollbar(chat_frame, command=chat_display.yview)
# chat_display.configure(yscrollcommand=scroll.set)
# scroll.pack(side="right", fill="y", pady=6, padx=(0,6))

# chat_display.configure(state="disabled")
# add_message_initial = True

# def add_message(sender, text):
#     chat_display.configure(state="normal")
#     prefix = "You: " if sender == "You" else ("NOVA: " if sender == "NOVA" else f"{sender}: ")
#     color = "#00ffff" if sender == "You" else "#ffffff"
#     tag = sender
#     try:
#         chat_display.tag_config(tag, foreground=color)
#     except Exception:
#         pass
#     chat_display.insert("end", f"{prefix}{text}\n\n", tag)
#     chat_display.configure(state="disabled")
#     chat_display.see("end")

# # ----------------- Input ----------------- #
# input_frame = ctk.CTkFrame(master=app, fg_color="transparent")
# input_frame.pack(fill="x", padx=6, pady=(0,10))

# message_entry = ctk.CTkEntry(input_frame, placeholder_text="Send a message...", width=240)
# message_entry.pack(side="left", fill="x", expand=True, padx=(6,6), pady=6)

# def send_message():
#     msg = message_entry.get().strip()
#     if not msg:
#         return
#     add_message("You", msg)
#     message_entry.delete(0, "end")
#     threading.Thread(target=process_message, args=(msg,), daemon=True).start()

# send_btn = ctk.CTkButton(input_frame, text="➤", width=52, command=send_message)
# send_btn.pack(side="left", padx=(0,6))

# # Continue and other helpers
# def continue_last():
#     if not conversation_history:
#         add_message("NOVA", "No previous response to continue.")
#         return
#     followup = "Please continue the previous answer. Continue where you left off and do not repeat the already given text."
#     conversation_history.append({"role":"user", "text": followup})
#     threading.Thread(target=lambda: _continue_worker(followup, on_update_partial), daemon=True).start()

# continue_btn = ctk.CTkButton(input_frame, text="⟳", width=52, command=continue_last)
# continue_btn.pack(side="left", padx=(0,6))

# # ----------------- History panel ----------------- #
# history_frame = ctk.CTkFrame(master=app, corner_radius=8, fg_color="#141416", border_width=1, border_color="#00ffff")
# history_display = ctk.CTkTextbox(history_frame, wrap="word", font=("Helvetica", 12), fg_color="transparent", text_color="#ffffff", width=300, height=360)
# history_display.pack(fill="both", expand=True, padx=8, pady=8)
# history_display.configure(state="disabled")

# def load_chat_history():
#     try:
#         history_display.configure(state="normal")
#         history_display.delete("1.0", "end")
#         memories = []
#         try:
#             memories = memory.get_chat_history("default_user", 50)
#         except Exception:
#             # fallback if memory offers other api
#             try:
#                 cur = memory.conn.cursor()
#                 cur.execute("SELECT query, response, timestamp FROM memory WHERE user_id = ? ORDER BY rowid DESC LIMIT 50", ("default_user",))
#                 memories = cur.fetchall()
#             except Exception:
#                 memories = []
#         if not memories:
#             history_display.insert("end", "No memories found.\n")
#         else:
#             for m in memories:
#                 try:
#                     q, r, t = m[0], m[1], (m[2] if len(m) > 2 else "")
#                     history_display.insert("end", f"[{t}] You: {q}\nNOVA: {r}\n\n")
#                 except Exception:
#                     pass
#         history_display.configure(state="disabled")
#         history_display.see("end")
#     except Exception as e:
#         add_message("System", f"History load error: {e}")

# # ----------------- LLM Integration ----------------- #
# def on_update_partial(chunk: str):
#     try:
#         chat_display.configure(state="normal")
#         if chat_display.get("end-3c", "end-2c") == "":  # rough first chunk detection not strict
#             chat_display.insert("end", "NOVA: ")
#         chat_display.insert("end", chunk)
#         chat_display.configure(state="disabled")
#         chat_display.see("end")
#     except Exception:
#         pass

# def process_message(message):
#     global uploaded_context, conversation_history
#     try:
#         set_processing(True)
#         # local handling (name, variables, arithmetic) (kept minimal)
#         import re
#         msg_lower = (message or "").strip()
#         m = re.search(r"\bmy name is ([A-Za-z0-9_\\-]+)\b", msg_lower, flags=re.IGNORECASE)
#         if not m:
#             m = re.search(r"\bi am ([A-Za-z0-9_\\-]+)\b", msg_lower, flags=re.IGNORECASE)
#         if m:
#             name = m.group(1).strip()
#             try:
#                 memory.set_user_name("default_user", name)
#             except Exception:
#                 pass
#             add_message("NOVA", f"Thik hai, {name} — yaad rakh liya.")
#             conversation_history.append({"role":"user","text":message})
#             conversation_history.append({"role":"assistant","text":f"Remembered name: {name}"})
#             set_processing(False)
#             return

#         # build prompt with uploaded context
#         context = uploaded_context or ""
#         prompt = f"{context}\n\nUser: {message}"
#         conversation_history.append({"role":"user","text":message})
#         if len(conversation_history) > 20:
#             conversation_history = conversation_history[-20:]

#         # ask local LLM (streaming)
#         response = ask_llm(prompt, memory, conversation_history, on_update=on_update_partial)
#         # ensure spacing
#         chat_display.configure(state="normal")
#         chat_display.insert("end", "\n\n")
#         chat_display.configure(state="disabled")
#         conversation_history.append({"role":"assistant","text": response})
#         # save memory
#         resp_clean = (response or "").strip()
#         if resp_clean and len(resp_clean) > 5:
#             try:
#                 memory.save_memory("default_user", message, resp_clean)
#             except Exception:
#                 pass
#     except Exception as e:
#         add_message("NOVA", f"Error: {e}")
#     finally:
#         set_processing(False)

# def _continue_worker(followup_text, on_update_cb):
#     try:
#         response = ask_llm(followup_text, memory, conversation_history, on_update=on_update_cb)
#         chat_display.configure(state="normal")
#         chat_display.insert("end", "\n\n")
#         chat_display.configure(state="disabled")
#         conversation_history.append({"role":"assistant","text": response})
#         try:
#             if response and len(response) > 5:
#                 memory.save_memory("default_user", "(continued)", response)
#         except Exception:
#             pass
#     except Exception as e:
#         add_message("NOVA", f"Error continuing: {e}")

# # ----------------- Voice loop ----------------- #
# def voice_input_loop():
#     global is_listening
#     while is_listening:
#         cmd = listen()
#         if cmd:
#             add_message("You", cmd)
#             process_message(cmd)
#         time.sleep(0.2)

# # ----------------- bindings ----------------- #
# message_entry.bind("<Return>", lambda e: send_message())

# # ----------------- start ----------------- #
# if __name__ == "__main__":
#     add_message("System", "NOVA: Ready")
#     app.mainloop()