import sys
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QPushButton, QLabel, QDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QTimer
from PyQt6.QtGui import QFont
import speech_recognition as sr
import pywhatkit
import datetime
import wikipedia
import webbrowser
import time
import edge_tts
import asyncio
import google.generativeai as genai
import subprocess
import threading
import psutil
import pygame.mixer
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
import wmi
from win10toast import ToastNotifier
import requests

from key import key_var

# Initialize pygame mixer
pygame.mixer.init()

# Gemini API Key configuration
API_KEY = key_var # User need to create another file for API key and assign it as a variable
genai.configure(api_key=API_KEY)

# Contextual memory (last 5 interactions)
context_memory = []
MEMORY_LIMIT = 5

# Reminder storage
reminders = []
notifier = ToastNotifier()

# Paths for opening specific applications
app_paths = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
}

# Global flags
is_speaking = False
interrupt_flag = threading.Event()
wake_word_detected = False
loop = asyncio.new_event_loop()

# Set asyncio loop in a separate thread
def run_asyncio_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=run_asyncio_loop, daemon=True).start()

# Filter unwanted formatting from text
def filter_text(text):
    text = re.sub(r'\*\*.*?\*\*|\*.*?\*|`.*?`', lambda m: m.group(0)[1:-1], text)
    text = re.sub(r'[\n\r]+', ' ', text)
    text = re.sub(r'[^a-zA-Z0-9.,!?\'" ]', '', text)
    text = ' '.join(text.split())
    return text

async def talk(text):
    global is_speaking
    clean_text = filter_text(text)
    voice = "en-US-JennyNeural"
    tts = edge_tts.Communicate(clean_text, voice, rate="+25%")
    audio_file = f"response_{int(time.time())}.mp3"
    print(f"Generating audio: {audio_file} with text: {clean_text}")
    await tts.save(audio_file)

    is_speaking = True
    interrupt_flag.clear()

    pygame.mixer.music.load(audio_file)
    pygame.mixer.music.play()
    print("Speaking...")

    while pygame.mixer.music.get_busy():
        if interrupt_flag.is_set():
            pygame.mixer.music.stop()
            print("Speech interrupted")
            break
        await asyncio.sleep(0.001)

    is_speaking = False
    print("Finished speaking")

def get_day_date():
    return datetime.datetime.now().strftime("%A, %B %d, %Y")

def ask_gemini(prompt):
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        system_prompt = """
You are an advanced, context-aware AI assistant named Echo, designed to deliver precise, insightful, and efficient responses. Your primary goal is to provide clear, intelligent, and engaging answers while maintaining brevity and relevance. Follow these principles:
- Adapt to Context & Mood: Align your tone with the user’s mood and the nature of the conversation—whether casual, professional, or highly technical.
- Be Concise, Yet Complete: Deliver well-structured responses that are neither too short nor unnecessarily verbose. Prioritize clarity and depth without over-explaining.
- No Redundancy: Avoid repeating information or your name ("Echo") unless necessary for clarity or emphasis.
- Ask Smart Questions: If a query lacks clarity, request precise details with a brief, targeted question.
- Ensure Logical Flow: Keep responses interconnected, ensuring a seamless and engaging dialogue.
- Encourage Exploration: When relevant, subtly suggest related ideas or next steps to enhance the user's understanding.
- Prioritize Accuracy & Relevance: Always provide well-reasoned, factual, and contextually appropriate responses.
Your mission: Deliver an exceptional user experience with every interaction. Avoid starting responses with "Echo" or self-referential phrases unless explicitly asked about your identity.
        """
        memory_context = "\n".join(context_memory)
        response = model.generate_content(f"{system_prompt}\n{memory_context}\nUser: {prompt}")
        formatted_response = response.text.strip() if response.text else "I couldn't process that."

        context_memory.append(f"User: {prompt}\nAssistant: {formatted_response}")
        if len(context_memory) > MEMORY_LIMIT:
            context_memory.pop(0)

        print(f"Assistant response: {formatted_response}")
        return formatted_response
    except Exception as e:
        print(f"Gemini error: {e}")
        return "I couldn't process that."

def close_application(app_name):
    closed = False
    for proc in psutil.process_iter():
        try:
            if app_name.lower() in proc.name().lower():
                proc.terminate()
                closed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return closed

def duckduckgo_search(query):
    url = "http://api.duckduckgo.com/?q=" + query + "&format=json&no_redirect=1"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("AbstractText"):
            return data["AbstractText"]
        elif data.get("RelatedTopics") and data["RelatedTopics"][0].get("Text"):
            return data["RelatedTopics"][0]["Text"]
        else:
            return None
    except Exception as e:
        print(f"DuckDuckGo search error: {e}")
        return None

def set_volume(level):
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = interface.QueryInterface(IAudioEndpointVolume)
    volume.SetMasterVolumeLevelScalar(level / 100, None)

def set_brightness(level):
    c = wmi.WMI(namespace='wmi')
    methods = c.WmiMonitorBrightnessMethods()[0]
    methods.WmiSetBrightness(level, 0)

def check_reminders():
    while True:
        now = time.time()
        for reminder in reminders[:]:
            if now >= reminder[1]:
                notifier.show_toast("Reminder", reminder[0], duration=10)
                asyncio.run_coroutine_threadsafe(talk(f"Reminder: {reminder[0]}"), loop)
                reminders.remove(reminder)
        time.sleep(1)

threading.Thread(target=check_reminders, daemon=True).start()

# Worker thread for voice recognition
class VoiceWorker(QThread):
    command_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def run(self):
        global wake_word_detected
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            self.status_signal.emit("Calibrating noise reduction...")
            recognizer.adjust_for_ambient_noise(source, duration=2)
            self.status_signal.emit("Listening...")
            while True:
                try:
                    audio = recognizer.listen(source, timeout=1, phrase_time_limit=5)
                    command = recognizer.recognize_google(audio).lower()
                    print(f"Recognized: {command}")

                    if "echo" in command and not wake_word_detected:
                        wake_word_detected = True
                        command = command.replace("echo", "").strip()
                        if is_speaking:
                            interrupt_flag.set()
                        self.command_signal.emit(command if command else "")
                    elif wake_word_detected:
                        if is_speaking:
                            interrupt_flag.set()
                        self.command_signal.emit(command)
                except sr.WaitTimeoutError:
                    continue
                except sr.UnknownValueError:
                    print("Could not understand audio")
                    continue
                except sr.RequestError as e:
                    self.status_signal.emit(f"Speech recognition error: {e}")
                    print(f"Speech recognition error: {e}")
                    continue

# Floating Status Widget
class StatusWidget(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Echo Status")
        self.setFixedSize(200, 150)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        # Style
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; border-radius: 10px; }
            QLabel { color: #ffffff; font-size: 12px; padding: 5px; }
        """)

        # Position on right side
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 210, screen.height() // 2)

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # Status label
        self.label = QLabel("Initializing...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFont(QFont("Helvetica", 12))
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        # Timer for auto-hide
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

        # Dragging support
        self.old_pos = None

    def show_status(self, text):
        self.label.setText(text)
        self.show()
        self.raise_()
        self.timer.start(5000)  # Hide after 5 seconds

    def mousePressEvent(self, event):
        self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

# Main GUI Window (Pill-shaped icon widget)
class EchoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Echo - AI Assistant")
        self.setFixedSize(150, 70)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        # Style for pill shape and unified button look
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; border-radius: 20px; }
            QPushButton { background-color: #4a4a4a; color: #ffffff; border: none; border-radius: 10px; 
                          padding: 4px; font-size: 16px; min-width: 32px; min-height: 32px; }
            QPushButton:hover { background-color: #5a5a5a; }
        """)

        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - 150) // 2, (screen.height() - 70) // 2)

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Buttons
        self.mic_button = QPushButton("🎤")
        self.mic_button.clicked.connect(self.start_voice_recognition)
        layout.addWidget(self.mic_button)

        self.settings_button = QPushButton("⚙")
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button)

        self.stop_button = QPushButton("■")
        self.stop_button.clicked.connect(self.stop_speech)
        layout.addWidget(self.stop_button)

        # Voice worker
        self.voice_worker = VoiceWorker()
        self.voice_worker.command_signal.connect(self.process_command)
        self.voice_worker.status_signal.connect(self.show_status)

        # Status widget
        self.status_widget = StatusWidget(self)
        self.status_widget.show_status("Say 'Echo' to start...")

        # Dragging support
        self.old_pos = None

    def start_voice_recognition(self):
        if not self.voice_worker.isRunning():
            self.voice_worker.start()
            self.mic_button.setStyleSheet("background-color: #ff5555; border-radius: 10px; font-size: 16px; min-width: 32px; min-height: 32px;")
            print("Voice recognition started")
        else:
            self.voice_worker.terminate()
            self.mic_button.setStyleSheet("background-color: #4a4a4a; border-radius: 10px; font-size: 16px; min-width: 32px; min-height: 32px;")
            self.status_widget.show_status("Stopped")
            print("Voice recognition stopped")

    def stop_speech(self):
        global interrupt_flag
        interrupt_flag.set()
        self.status_widget.show_status("Speech stopped")
        print("Stop button pressed")

    def show_status(self, status):
        self.status_widget.show_status(status)

    def process_command(self, command):
        self.status_widget.show_status(f"You: {command}")
        asyncio.run_coroutine_threadsafe(self.process_command_async(command), loop)

    def mousePressEvent(self, event):
        self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    async def process_command_async(self, command):
        global wake_word_detected
        if not command:
            return

        self.status_widget.show_status("Processing...")
        print(f"Processing command: {command}")
        if "play" in command:
            song = command.replace("play", "").strip()
            response = f"Playing {song} on YouTube"
            self.status_widget.show_status(response)
            await talk(response)
            pywhatkit.playonyt(song)
        elif "time" in command:
            time_now = datetime.datetime.now().strftime('%I:%M %p')
            response = f"The current time is {time_now}"
            self.status_widget.show_status(response)
            await talk(response)
        elif "date" in command or "day" in command:
            date = get_day_date()
            response = f"Today's date is {date}"
            self.status_widget.show_status(response)
            await talk(response)
        elif "tell me about" in command or "who is" in command or "what is" in command:
            subject = command.replace("tell me about", "").replace("who is", "").replace("what is", "").strip()
            try:
                info = wikipedia.summary(subject, sentences=2)
                self.status_widget.show_status(info)
                await talk(info)
            except wikipedia.exceptions.DisambiguationError:
                response = "There are multiple results. Can you be more specific?"
                self.status_widget.show_status(response)
                await talk(response)
            except wikipedia.exceptions.PageError:
                response = "I couldn't find anything on that topic."
                self.status_widget.show_status(response)
                await talk(response)
        elif "open" in command:
            app_or_site = command.replace("open", "").strip()
            if app_or_site in app_paths:
                response = f"Opening {app_or_site}"
                self.status_widget.show_status(response)
                await talk(response)
                subprocess.Popen(app_paths[app_or_site])
            else:
                response = f"Opening {app_or_site} on browser"
                self.status_widget.show_status(response)
                await talk(response)
                if "." in app_or_site:
                    webbrowser.open(f"https://{app_or_site}")
                else:
                    webbrowser.open(f"https://www.google.com/search?q={app_or_site}")
        elif "close" in command:
            app = command.replace("close", "").strip()
            if close_application(app):
                response = f"Closed all instances matching {app}"
                self.status_widget.show_status(response)
                await talk(response)
            else:
                response = f"Couldn't find any app matching {app} to close"
                self.status_widget.show_status(response)
                await talk(response)
        elif "search" in command:
            query = command.replace("search", "").strip()
            result = duckduckgo_search(query)
            if result:
                self.status_widget.show_status(result)
                await talk(result)
            else:
                response = f"No quick answer found. Opening {query} in browser."
                self.status_widget.show_status(response)
                await talk(response)
                webbrowser.open(f"https://www.google.com/search?q={query}")
        elif "set volume to" in command:
            try:
                level = int(command.split()[-1])
                if 0 <= level <= 100:
                    set_volume(level)
                    response = f"Volume set to {level}%"
                    self.status_widget.show_status(response)
                    await talk(response)
                else:
                    response = "Volume must be between 0 and 100"
                    self.status_widget.show_status(response)
                    await talk(response)
            except ValueError:
                response = "Please specify a valid volume level"
                self.status_widget.show_status(response)
                await talk(response)
        elif "set brightness to" in command:
            try:
                level = int(command.split()[-1])
                if 0 <= level <= 100:
                    set_brightness(level)
                    response = f"Brightness set to {level}%"
                    self.status_widget.show_status(response)
                    await talk(response)
                else:
                    response = "Brightness must be between 0 and 100"
                    self.status_widget.show_status(response)
                    await talk(response)
            except ValueError:
                response = "Please specify a valid brightness level"
                self.status_widget.show_status(response)
                await talk(response)
        elif "remind me" in command:
            try:
                message = command.replace("remind me to", "").split("in")[0].strip()
                time_str = command.split("in")[-1].strip()
                if "minute" in time_str:
                    seconds = int(time_str.split()[0]) * 60
                elif "hour" in time_str:
                    seconds = int(time_str.split()[0]) * 3600
                else:
                    response = "I can only set reminders in minutes or hours"
                    self.status_widget.show_status(response)
                    await talk(response)
                    return
                reminders.append((message, time.time() + seconds))
                response = f"Reminder set for {message} in {time_str}"
                self.status_widget.show_status(response)
                await talk(response)
            except (IndexError, ValueError):
                response = "Invalid format. Try 'Echo remind me to call John in 5 minutes'"
                self.status_widget.show_status(response)
                await talk(response)
        elif "exit" in command or "stop" in command:
            response = "Goodbye!"
            self.status_widget.show_status(response)
            await talk(response)
            sys.exit()
        else:
            response = ask_gemini(command)
            self.status_widget.show_status(response)
            await talk(response)

        self.status_widget.show_status("Listening...")

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

# Settings Dialog
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setStyleSheet("background-color: #2b2b2b; color: #ffffff;")
        layout = QHBoxLayout()

        voice_label = QLabel("Voice Selection (Coming Soon)")
        layout.addWidget(voice_label)

        wake_label = QLabel("Wake Word: Echo (Fixed for now)")
        layout.addWidget(wake_label)

        self.setLayout(layout)

# Main application
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EchoWindow()
    window.show()

    sys.exit(app.exec())
