from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QScrollArea
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from core.voice_worker import VoiceWorker
from core.assistant import text_to_speech, ask_gemini
import asyncio


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
        from core.config import interrupt_flag
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
        from core.config import loop
        self.add_conversation_item(response, is_user=False)

        def run_tts():
            future = asyncio.run_coroutine_threadsafe(text_to_speech(response), loop)
            try:
                future.result()  # Wait for the coroutine to complete
            except Exception as e:
                self.add_conversation_item(f"TTS Error: {str(e)}", is_user=False)

        QTimer.singleShot(0, run_tts)

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