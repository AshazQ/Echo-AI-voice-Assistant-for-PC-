import threading
import speech_recognition as sr
from PyQt6.QtCore import QThread, pyqtSignal
from core.assistant import identify_intent, process_command

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
                            response = process_command(command)
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

    def stop(self):
        """Stop the voice worker thread."""
        self._stop_event.set()

    def pause(self):
        """Pause voice recognition."""
        self._pause_event.clear()

    def resume(self):
        """Resume voice recognition."""
        self._pause_event.set()