import os
import subprocess
import psutil
import webbrowser
from AppOpener import open as open_app
from AppOpener import close as close_app 

def get_system_stats():
    # Tera purana code waisa hi rahega
    try:
        battery = psutil.sensors_battery()
        ram = psutil.virtual_memory()
        stat_text = f"System RAM usage is at {ram.percent} percent. "
        if battery:
            stat_text += f"Battery is at {battery.percent} percent."
            if battery.power_plugged:
                stat_text += " And the charger is connected."
        return stat_text
    except Exception as e:
        return "I am unable to access system status right now."

# NAYA DYNAMIC APP OPENER FUNCTION
def open_application(app_name):
    """PC me dynamically koi bhi app open karne ke liye"""
    app_name = app_name.lower().strip()
    
    try:
        # throw_error=True se agar app nahi mili toh error throw hoga jise hum except me pakdenge
        open_app(app_name, throw_error=True)
        return f"Opening {app_name}."
    except Exception:
        # Agar app PC me nahi hai
        return f"Sorry, I couldn't find any app named {app_name} installed on your system."

# BONUS: App close karne ka naya function
def close_application(app_name):
    """PC me dynamically koi bhi app band karne ke liye"""
    app_name = app_name.lower().strip()
    try:
        close_app(app_name, throw_error=True)
        return f"Closing {app_name}."
    except Exception:
        return f"I couldn't close {app_name}. It might not be running."

def play_on_youtube(query):
    # Tera purana code waisa hi rahega
    search_query = query.replace("play", "").replace("on youtube", "").strip()
    url = f"https://www.youtube.com/results?search_query={search_query}"
    webbrowser.open(url)
    return f"Playing {search_query} on YouTube."

def lock_system():
    # Tera purana code waisa hi rahega
    os.system("rundll32.exe user32.dll,LockWorkStation")
    return "System locked."