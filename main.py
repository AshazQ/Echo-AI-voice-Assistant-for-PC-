import sys
import os
import threading
import time
import re
import asyncio
import datetime

import wmi
import speech_recognition as sr
import pywhatkit
import wikipedia
import webbrowser
import subprocess
import psutil
import pygame.mixer
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QStackedWidget, QScrollArea
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer

# Optional module imports with availability flags
try:
    import edge_tts

    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    import google.generativeai as genai

    try:
        from core.key import key_var

        genai.configure(api_key=key_var)
        GEMINI_AVAILABLE = True
    except ImportError:
        GEMINI_AVAILABLE = False
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL

    VOLUME_CONTROL_AVAILABLE = True
except ImportError:
    VOLUME_CONTROL_AVAILABLE = False

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


def filter_text(text: str) -> str:
    """Clean text for TTS by removing markdown and special characters."""
    text = re.sub(r'\*\*.*?\*\*|\*.*?\*|`.*?`', lambda m: m.group(0)[1:-1], text)
    text = re.sub(r'[\n\r]+', ' ', text)
    text = re.sub(r'[^a-zA-Z0-9.,!?\'" ]', '', text)
    return ' '.join(text.split())


async def text_to_speech(text: str, callback=None) -> None:
    """Convert text to speech using edge-tts."""
    global is_speaking
    if not TTS_AVAILABLE:
        if callback:
            callback(f"TTS: {text}")
        return

    try:
        clean_text = filter_text(text)
        voice = "en-US-JennyNeural"
        tts = edge_tts.Communicate(clean_text, voice, rate="+15%")
        audio_file = f"response_{int(time.time())}.mp3"
        await tts.save(audio_file)
        is_speaking = True
        interrupt_flag.clear()
        if callback:
            callback(" ")
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if interrupt_flag.is_set():
                pygame.mixer.music.stop()
                break
            await asyncio.sleep(0.1)
        is_speaking = False
        try:
            os.remove(audio_file)
        except:
            pass
    except Exception as e:
        if callback:
            callback(f"TTS Error: {text}")


def ask_gemini(prompt: str) -> str:
    """Query Gemini AI model with context-aware prompt."""
    if not GEMINI_AVAILABLE:
        return "Gemini AI is not available. Please install google-generativeai and add your API key."

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        system_prompt = """
            You are an advanced, context-aware AI assistant named Echo, designed to deliver precise, insightful, and efficient responses. Your primary goal is to provide clear, intelligent, and engaging answers while maintaining brevity and relevance. Follow these principles:
            - Adapt to Context & Mood: Align your tone with the user's mood and the nature of the conversation—whether casual, professional, or highly technical.
            - Be Concise, Yet Complete: Deliver well-structured responses that are neither too short nor unnecessarily verbose. Prioritize clarity and depth without over-explaining.
            - No Redundancy: Avoid repeating information or your name ("Echo") unless necessary for clarity or emphasis.
            - Ask Smart Questions: If a query lacks clarity, request precise details with a brief, targeted question.
            - Ensure Logical Flow: Keep responses interconnected, ensuring a seamless and engaging dialogue.
            - Encourage Exploration: When relevant, subtly suggest related ideas or next steps to enhance the user's understanding.
            - Prioritize Accuracy & Relevance: Always provide well-reasoned, factual, and contextually appropriate responses.
            Your mission: Deliver an exceptional user experience with every interaction. Avoid starting responses with "Echo" or self-referential phrases unless explicitly asked about your identity.
        """
        memory_context = "\n".join(context_memory)
        full_prompt = f"{system_prompt}\n{memory_context}\nUser: {prompt}"
        response = model.generate_content(full_prompt)
        formatted_response = response.text.strip() if response.text else "I couldn't process that."
        context_memory.append(f"User: {prompt}\nEcho: {formatted_response}")
        if len(context_memory) > MEMORY_LIMIT:
            context_memory.pop(0)
        return formatted_response
    except Exception as e:
        return f"I'm having trouble connecting to my AI service. Error: {str(e)}"


def get_day_date() -> str:
    """Return the current day and date."""
    return datetime.datetime.now().strftime("%A, %B %d, %Y")


def close_application(app_name: str) -> bool:
    """Close the specified application."""
    closed = False
    for proc in psutil.process_iter():
        try:
            if app_name.lower() in proc.name().lower():
                proc.terminate()
                closed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return closed


def set_volume(level: int) -> bool:
    """Set system volume to the specified level."""
    if not VOLUME_CONTROL_AVAILABLE:
        return False
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        volume.SetMasterVolumeLevelScalar(level / 100, None)
        return True
    except:
        return False


def set_brightness(level: int) -> bool:
    """Set screen brightness to the specified level."""
    try:
        c = wmi.WMI(namespace='wmi')
        methods = c.WmiMonitorBrightnessMethods()[0]
        methods.WmiSetBrightness(level, 0)
        return True
    except Exception:
        return False


def identify_intent(command: str) -> str:
    """Identify the intent of the user's command."""
    command_lower = command.lower()
    for intent, keywords in INTENT_CATEGORIES.items():
        if any(keyword in command_lower for keyword in keywords):
            return intent
    return "ai_chat"


def duckduckgo_search(query: str) -> str:
    """Perform a search using DuckDuckGo API."""
    url = f"http://api.duckduckgo.com/?q={query}&format=json&no_redirect=1"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("AbstractText"):
            return data["AbstractText"]
        elif data.get("RelatedTopics") and data["RelatedTopics"]:
            if data["RelatedTopics"][0].get("Text"):
                return data["RelatedTopics"][0]["Text"]
        return None
    except Exception:
        return None


class VoiceWorker(QThread):
    """Worker thread for handling voice recognition."""
    transcribed = pyqtSignal(str, str)
    response_ready = pyqtSignal(str)
    status = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.recognizer = sr.Recognizer()
        self.microphone = None

    def run(self):
        """Main loop for voice recognition."""
        self.status.emit("Initializing microphone...")
        try:
            self.microphone = sr.Microphone()
            with self.microphone as source:
                self.status.emit("Calibrating for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
            self.recognizer.phrase_threshold = 0.3
            self.status.emit("Ready - Say something to Echo...")

            while not self._stop_event.is_set():
                if not self._pause_event.is_set():
                    self.msleep(100)
                    continue
                try:
                    with self.microphone as source:
                        audio = self.recognizer.listen(
                            source,
                            timeout=1,
                            phrase_time_limit=8
                        )
                    try:
                        command = self.recognizer.recognize_google(audio).lower()
                        if command.strip():
                            intent = identify_intent(command)
                            self.transcribed.emit(command, intent)
                            response = self.process_command(command)
                            self.response_ready.emit(response)
                            self.status.emit("Listening...")
                    except sr.UnknownValueError:
                        self.status.emit("Could not understand. Try speaking more clearly.")
                        continue
                    except sr.RequestError as e:
                        self.error.emit(f"Speech recognition error: {e}")
                        continue
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    self.error.emit(f"Microphone error: {e}")
                    break
        except Exception as e:
            self.error.emit(f"Failed to initialize microphone: {e}")
        self.status.emit("Voice recognition stopped.")

    def process_command(self, command: str) -> str:
        """Process voice commands and return appropriate responses."""
        try:
            if "play" in command and any(word in command for word in ["song", "music", "on youtube", "youtube"]):
                song = command.replace("play", "").replace("song", "").replace("music", "").replace("on youtube",
                                                                                                    "").replace(
                    "youtube", "").strip()
                if song:
                    try:
                        pywhatkit.playonyt(song)
                        return f"Playing {song} on YouTube"
                    except:
                        return f"Sorry, I couldn't play {song}"
                return "What would you like me to play?"
            elif "time" in command:
                time_now = datetime.datetime.now().strftime('%I:%M %p')
                return f"The current time is {time_now}"
            elif "date" in command or "day" in command:
                return f"Today is {get_day_date()}"
            elif any(phrase in command for phrase in ["tell me about", "who is", "what is", "explain"]):
                subject = command
                for phrase in ["tell me about", "who is", "what is", "explain"]:
                    subject = subject.replace(phrase, "").strip()
                if subject:
                    try:
                        info = wikipedia.summary(subject, sentences=2)
                        return info
                    except wikipedia.exceptions.DisambiguationError:
                        return f"There are multiple results for {subject}. Can you be more specific?"
                    except wikipedia.exceptions.PageError:
                        return f"I couldn't find information about {subject}"
                return "What would you like to know about?"
            elif "open" in command:
                app_or_site = command.replace("open", "").strip()
                if app_or_site in APP_PATHS:
                    try:
                        subprocess.Popen(APP_PATHS[app_or_site])
                        return f"Opening {app_or_site}"
                    except:
                        return f"I couldn't open {app_or_site}"
                else:
                    try:
                        if "." in app_or_site or any(
                                site in app_or_site for site in ["google", "youtube", "facebook", "twitter"]):
                            if not app_or_site.startswith("http"):
                                app_or_site = f"https://{app_or_site}" if "." in app_or_site else f"https://www.{app_or_site}.com"
                            webbrowser.open(app_or_site)
                            return f"Opening {app_or_site} in browser"
                        else:
                            webbrowser.open(f"https://www.google.com/search?q={app_or_site}")
                            return f"Searching for {app_or_site}"
                    except:
                        return f"I couldn't open {app_or_site}"
            elif "close" in command:
                app = command.replace("close", "").strip()
                return f"Closed {app}" if close_application(app) else f"I couldn't find {app} to close"
            elif "search" in command or "look up" in command:
                query = command.replace("search", "").replace("look up", "").strip()
                if query:
                    result = duckduckgo_search(query)
                    if result:
                        return result[:200] + "..." if len(result) > 200 else result
                    else:
                        webbrowser.open(f"https://www.google.com/search?q={query}")
                        return f"I couldn't find a quick answer, so I opened a search for {query}"
                return "What would you like me to search for?"
            elif "volume" in command:
                try:
                    if "set volume" in command or "volume to" in command:
                        words = command.split()
                        for word in words:
                            if word.isdigit():
                                level = int(word)
                                if 0 <= level <= 100:
                                    return f"Volume set to {level}%" if set_volume(
                                        level) else "I couldn't change the volume"
                                return "Volume must be between 0 and 100"
                    elif "increase volume" in command or "volume up" in command:
                        return "Volume increased" if set_volume(75) else "I couldn't increase the volume"
                    elif "decrease volume" in command or "volume down" in command:
                        return "Volume decreased" if set_volume(25) else "I couldn't decrease the volume"
                    return "Please specify a volume level between 0 and 100"
                except:
                    return "I couldn't change the volume"
            elif "brightness" in command:
                try:
                    if "set brightness" in command or "brightness to" in command:
                        words = command.split()
                        for word in words:
                            if word.isdigit():
                                level = int(word)
                                if 0 <= level <= 100:
                                    return f"Brightness set to {level}%" if set_brightness(
                                        level) else "I couldn't change the brightness"
                                return "Brightness must be between 0 and 100"
                    elif "increase brightness" in command or "brightness up" in command:
                        return "Brightness increased" if set_brightness(80) else "I couldn't increase the brightness"
                    elif "decrease brightness" in command or "brightness down" in command:
                        return "Brightness decreased" if set_brightness(30) else "I couldn't decrease the brightness"
                    return "Please specify a brightness level between 0 and 100"
                except:
                    return "I couldn't change the brightness"
            elif "weather" in command:
                location = command.split(" in ")[-1].strip() if " in " in command else "current location"
                webbrowser.open(f"https://www.google.com/search?q=weather+{location}")
                return f"Opening weather information for {location}"
            else:
                return ask_gemini(command)
        except Exception as e:
            return f"Sorry, I encountered an error: {str(e)}"

    def stop(self):
        """Stop the voice worker thread."""
        self._stop_event.set()

    def pause(self):
        """Pause voice recognition."""
        self._pause_event.clear()

    def resume(self):
        """Resume voice recognition."""
        self._pause_event.set()


class VoiceScreen(QWidget):
    """Widget for voice interaction mode."""
    back_to_menu = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.worker = None
        self.paused = False
        self.scroll_area = None
        self.init_ui()

    def init_ui(self):
        """Initialize the UI for voice mode."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(49, 32, 49, 32)
        main_layout.setSpacing(0)

        # Scroll area for conversation
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.5);
            }
        """)

        self.conversation_content = QWidget()
        self.conversation_layout = QVBoxLayout(self.conversation_content)
        self.conversation_layout.setSpacing(16)
        self.conversation_layout.setContentsMargins(30, 20, 30, 20)
        self.conversation_layout.addStretch()
        self.conversation_content.setStyleSheet("background: transparent; border: none; border-radius: 15px;")
        self.scroll_area.setWidget(self.conversation_content)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # Bottom controls layout
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(20)
        bottom_layout.setContentsMargins(0, 20, 0, 0)
        bottom_layout.addStretch()

        def create_circle_button(label: str) -> QPushButton:
            """Create a circular button with consistent styling."""
            btn = QPushButton(label)
            btn.setFixedSize(80, 80)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #F7EA7D;
                    color: #222;
                    font-size: 18px;
                    font-weight: 600;
                    font-family: 'Segoe UI';
                    border: none;
                    border-radius: 40px;
                }
                QPushButton:hover { background-color: #FFF3A0; }
                QPushButton:pressed { background-color: #F0E76B; }
                QPushButton:disabled {
                    background-color: rgba(247, 234, 125, 0.5);
                    color: rgba(51, 51, 51, 0.5);
                }
            """)
            return btn

        # Buttons
        self.stop_btn = create_circle_button("■")
        self.stop_btn.clicked.connect(self.handle_stop)
        self.stop_btn.setEnabled(False)
        bottom_layout.addWidget(self.stop_btn)

        self.pause_btn = create_circle_button("II")
        self.pause_btn.clicked.connect(self.handle_pause)
        self.pause_btn.setEnabled(False)
        bottom_layout.addWidget(self.pause_btn)

        self.mic_btn = create_circle_button("🎤")
        self.mic_btn.clicked.connect(self.handle_start)
        bottom_layout.addWidget(self.mic_btn)

        main_layout.addLayout(bottom_layout)

        # Back to menu button
        back_btn = QPushButton("Back to Menu")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.15);
                color: white;
                font-size: 20px;
                font-family: 'Segoe UI';
                font-weight: 500;
                border: 2px solid white;
                border-radius: 27px;
                padding: 12px 36px;
                min-width: 200px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.25); }
            QPushButton:pressed { background-color: rgba(255, 255, 255, 0.35); }
        """)
        back_btn.clicked.connect(self.back_to_menu.emit)
        main_layout.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        QTimer.singleShot(100, self.add_welcome_message)

    def add_welcome_message(self):
        """Display the welcome message."""
        self.add_conversation_item("Welcome! Press 'Mic' to start voice conversation.", is_user=False)

    def add_conversation_item(self, text: str, is_user: bool = True):
        """Add a conversation item to the UI."""
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(0)

        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setFont(QFont("Segoe UI", 17))
        bubble.setMinimumHeight(36)
        bubble_style = """
            background: rgba(255, 255, 255, 0.3);
            color: #000;
            border-radius: 22px;
            padding: 14px 24px;
        """
        bubble.setStyleSheet(bubble_style)
        bubble.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter if is_user else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        item_layout.addStretch() if is_user else item_layout.addWidget(bubble)
        if is_user:
            item_layout.addWidget(bubble)
        else:
            item_layout.addStretch()

        self.conversation_layout.insertWidget(self.conversation_layout.count() - 1, item_widget)
        QTimer.singleShot(50, self.scroll_to_bottom)

    def scroll_to_bottom(self):
        """Scroll to the bottom of the conversation area."""
        if self.scroll_area and self.scroll_area.verticalScrollBar():
            scrollbar = self.scroll_area.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def handle_start(self):
        """Start the voice recognition worker."""
        if self.worker and self.worker.isRunning():
            return
        self.worker = VoiceWorker()
        self.worker.transcribed.connect(self.on_transcribed)
        self.worker.response_ready.connect(self.on_response)
        self.worker.status.connect(self.on_status)
        self.worker.error.connect(self.on_error)
        self.worker.start()
        self.mic_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.paused = False

    def handle_pause(self):
        """Pause or resume voice recognition."""
        if not self.worker:
            return
        if not self.paused:
            self.worker.pause()
            self.pause_btn.setText("▶")
            self.paused = True
        else:
            self.worker.resume()
            self.pause_btn.setText("II")
            self.paused = False

    def handle_stop(self):
        """Stop the voice recognition worker."""
        global interrupt_flag
        interrupt_flag.set()
        if self.worker:
            self.worker.stop()
            self.worker.wait(3000)
        self.mic_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("II")
        self.stop_btn.setEnabled(False)

    def on_transcribed(self, text: str, intent: str):
        """Handle transcribed voice input."""
        self.add_conversation_item(text, is_user=True)

    def on_response(self, response: str):
        """Handle response from voice worker."""
        self.add_conversation_item(response, is_user=False)
        asyncio.run_coroutine_threadsafe(text_to_speech(response), loop)

    def on_status(self, status: str):
        """Handle status updates (currently unused)."""
        pass

    def on_error(self, error: str):
        """Handle errors from voice worker."""
        self.add_conversation_item(f"Error: {error}", is_user=False)


class ChatScreen(QWidget):
    """Widget for text-based chat mode."""
    back_to_menu = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize the UI for chat mode."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)

        title = QLabel("Chat Mode - Text Conversation")
        title.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
        title.setStyleSheet("color: white; margin-bottom: 30px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.chat_area = QTextEdit()
        self.chat_area.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 0.1);
                color: white;
                font-size: 18px;
                font-family: 'Segoe UI';
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 15px;
                padding: 20px;
            }
        """)
        self.chat_area.setReadOnly(True)
        layout.addWidget(self.chat_area, stretch=1)

        input_layout = QHBoxLayout()
        self.input_field = QTextEdit()
        self.input_field.setMaximumHeight(100)
        self.input_field.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 0.9);
                color: #333;
                font-size: 16px;
                font-family: 'Segoe UI';
                border: none;
                border-radius: 10px;
                padding: 15px;
            }
        """)
        self.input_field.setPlaceholderText("Type your message here...")
        input_layout.addWidget(self.input_field)

        send_btn = QPushButton("Send")
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #F7EA7D;
                color: #333;
                font-size: 18px;
                font-family: 'Segoe UI';
                font-weight: 600;
                border: none;
                border-radius: 30px;
                padding: 15px 30px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #FFF3A0;
            }
        """)
        send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(send_btn)
        layout.addLayout(input_layout)

        back_btn = QPushButton("Back to Menu")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.15);
                color: white;
                font-size: 20px;
                font-family: 'Segoe UI';
                font-weight: 500;
                border: 2px solid white;
                border-radius: 27px;
                padding: 12px 36px;
                min-width: 200px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.25);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.35);
            }
        """)
        back_btn.clicked.connect(self.back_to_menu.emit)
        layout.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.chat_area.append("Welcome to Chat Mode! Type your questions below and I'll respond using AI.")

    def send_message(self):
        """Send a text message and display the response."""
        message = self.input_field.toPlainText().strip()
        if not message:
            return
        self.chat_area.append(f"\nYou: {message}")
        self.input_field.clear()
        response = ask_gemini(message)
        self.chat_area.append(f"\nEcho: {response}")
        cursor = self.chat_area.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.chat_area.setTextCursor(cursor)


class WelcomeScreen(QWidget):
    """Widget for the welcome screen."""
    chat_mode_clicked = pyqtSignal()
    voice_mode_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize the UI for the welcome screen."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(80, 60, 80, 60)
        main_layout.setSpacing(100)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(30)

        welcome_title = QLabel("Welcome to Echo, your personal voice assistant.")
        welcome_title.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        welcome_title.setStyleSheet("color: white; line-height: 1.2;")
        welcome_title.setWordWrap(True)
        left_layout.addWidget(welcome_title)

        features_layout = QVBoxLayout()
        features_layout.setSpacing(23)
        feature1 = QLabel("• Simplify tasks with hands-free voice\n  commands.")
        feature1.setFont(QFont("Segoe UI", 14))
        feature1.setStyleSheet("color: white; line-height: 1.3;")
        features_layout.addWidget(feature1)
        feature2 = QLabel("• Access information, control media, and\n  launch apps.")
        feature2.setFont(QFont("Segoe UI", 14))
        feature2.setStyleSheet("color: white; line-height: 1.3;")
        features_layout.addWidget(feature2)
        left_layout.addLayout(features_layout)
        left_layout.addStretch()
        main_layout.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(40)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        get_started_title = QLabel("Get Started....")
        get_started_title.setFont(QFont("Segoe UI", 48, QFont.Weight.Normal))
        get_started_title.setStyleSheet("color: white;")
        get_started_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(get_started_title)

        button_style = """
            QPushButton {
                background-color: #F7EA7D;
                color: #333;
                font-size: 32px;
                font-family: 'Segoe UI';
                font-weight: 500;
                border: none;
                border-radius: 50px;
                padding: 25px 50px;
                min-width: 100px;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #FFF3A0;
            }
            QPushButton:pressed {
                background-color: #F0E76B;
            }
        """

        self.chat_mode_btn = QPushButton("Chat Mode")
        self.chat_mode_btn.setStyleSheet(button_style)
        self.chat_mode_btn.clicked.connect(self.chat_mode_clicked.emit)
        right_layout.addWidget(self.chat_mode_btn)

        self.voice_mode_btn = QPushButton("Voice Mode")
        self.voice_mode_btn.setStyleSheet(button_style)
        self.voice_mode_btn.clicked.connect(self.voice_mode_clicked.emit)
        right_layout.addWidget(self.voice_mode_btn)
        right_layout.addStretch()
        main_layout.addWidget(right_widget)


class VoiceWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Echo - Advanced Voice Assistant")
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(
                    spread:pad, x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4B3A60,
                    stop:0.25 #7851A9, 
                    stop:0.75 #A48BCF,
                    stop:1 #A48BCF
                );
            }
        """)
        self.center_on_screen()
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        self.welcome_screen = WelcomeScreen()
        self.voice_screen = VoiceScreen()
        self.chat_screen = ChatScreen()
        self.stacked_widget.addWidget(self.welcome_screen)
        self.stacked_widget.addWidget(self.voice_screen)
        self.stacked_widget.addWidget(self.chat_screen)
        self.welcome_screen.voice_mode_clicked.connect(self.show_voice_screen)
        self.welcome_screen.chat_mode_clicked.connect(self.show_chat_screen)
        self.voice_screen.back_to_menu.connect(self.show_welcome_screen)
        self.chat_screen.back_to_menu.connect(self.show_welcome_screen)
        self.stacked_widget.setCurrentWidget(self.welcome_screen)

    def center_on_screen(self):
        """Center the window on the screen."""
        screen = QApplication.primaryScreen().availableGeometry()
        window_geometry = self.geometry()
        x = (screen.width() - window_geometry.width()) // 5
        y = (screen.height() - window_geometry.height()) // 5
        self.move(x, y)

    def show_welcome_screen(self):
        """Show the welcome screen."""
        self.stacked_widget.setCurrentWidget(self.welcome_screen)

    def show_voice_screen(self):
        """Show the voice mode screen."""
        self.stacked_widget.setCurrentWidget(self.voice_screen)

    def show_chat_screen(self):
        """Show the chat mode screen."""
        self.stacked_widget.setCurrentWidget(self.chat_screen)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = VoiceWindow()
    window.show()
    sys.exit(app.exec())
