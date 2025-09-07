from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QApplication
from PyQt6.QtCore import Qt
from ui.screens import WelcomeScreen, VoiceScreen, ChatScreen

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