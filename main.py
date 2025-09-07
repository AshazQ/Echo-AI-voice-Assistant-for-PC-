import sys
from PyQt6.QtWidgets import QApplication
from ui.window import VoiceWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = VoiceWindow()
    window.show()
    sys.exit(app.exec())
