import os
import threading
import asyncio
import pygame.mixer
import logging

# Set up logging for debugging, using INFO level to reduce verbosity
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Optional module imports with availability flags
try:
    import edge_tts
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    logging.warning("edge_tts module not found. TTS will be disabled.")

try:
    import google.generativeai as genai
    try:
        from core.key import key_var
        # logging.info(f"Successfully imported key_var")  # Changed to INFO level
        genai.configure(api_key=key_var)
        GEMINI_AVAILABLE = True
    except ImportError as e:
        logging.error(f"Failed to import key_var from core.key: {str(e)}")
        GEMINI_AVAILABLE = False
except ImportError as e:
    logging.error(f"Failed to import google.generativeai: {str(e)}")
    GEMINI_AVAILABLE = False

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    VOLUME_CONTROL_AVAILABLE = True
except ImportError:
    VOLUME_CONTROL_AVAILABLE = False
    logging.warning("pycaw module not found. Volume control will be disabled.")

# Constants
MEMORY_LIMIT = 5
APP_PATHS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
}
INTENT_CATEGORIES = {
    "media_control": ["play", "music", "song", "youtube"],
    "time_date": ["time", "date", "day", "today"],
    "information": ["tell me about", "who is", "what is", "explain", "search", "look up"],
    "system_control": ["open", "close", "volume", "brightness"],
    "weather": ["weather", "temperature", "forecast"],
    "ai_chat": ["general conversation"]
}

# Global variables
pygame.mixer.init()
loop = asyncio.new_event_loop()
context_memory = []
is_speaking = False
interrupt_flag = threading.Event()

def run_asyncio_loop():
    """Run asyncio event loop in a separate thread."""
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=run_asyncio_loop, daemon=True).start()